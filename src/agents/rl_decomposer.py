"""
强化学习驱动的任务分解器

核心创新：
1. 不是模仿大模型分解，而是学习"怎么分解最优"
2. 状态：任务 + 系统负载
3. 动作：分解策略（数量、并行度、粒度）
4. 奖励：-时间 - λ*成本 + β*成功
5. 算法：PPO (Proximal Policy Optimization)
"""

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Tuple
from collections import deque
import random


@dataclass
class DecompositionAction:
    """分解动作"""
    num_subtasks: int  # 子任务数量（2-7）
    parallelism: float  # 并行度（0-1）
    granularity: str  # 粒度（coarse/medium/fine）


@dataclass
class SystemState:
    """系统状态"""
    queue_length: int
    gpu_utilization: float
    avg_task_time: float
    recent_success_rate: float


@dataclass
class Experience:
    """经验样本"""
    state: torch.Tensor
    action: DecompositionAction
    reward: float
    next_state: torch.Tensor
    done: bool
    log_prob: float
    value: float


class TaskEncoder(nn.Module):
    """任务编码器：将任务描述编码为向量"""

    def __init__(self, vocab_size: int = 10000, embed_dim: int = 128, hidden_dim: int = 256):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim)
        self.lstm = nn.LSTM(embed_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, 64)

    def forward(self, task_tokens: torch.Tensor):
        """
        Args:
            task_tokens: [batch, seq_len] 任务描述的 token IDs

        Returns:
            task_embedding: [batch, 64] 任务向量
        """
        embedded = self.embedding(task_tokens)  # [batch, seq_len, embed_dim]
        _, (hidden, _) = self.lstm(embedded)  # hidden: [1, batch, hidden_dim]
        task_vec = self.fc(hidden.squeeze(0))  # [batch, 64]
        return task_vec


class ActorNetwork(nn.Module):
    """Actor：决定分解策略"""

    def __init__(self, task_dim: int = 64, state_dim: int = 4):
        super().__init__()

        input_dim = task_dim + state_dim

        self.shared = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.ReLU(),
        )

        # 子任务数量（2-7，离散分布）
        self.num_subtasks_head = nn.Linear(128, 6)  # 6 种选择：2,3,4,5,6,7

        # 并行度（0-1，Beta 分布参数）
        self.parallelism_alpha = nn.Sequential(
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Softplus()  # 确保 > 0
        )
        self.parallelism_beta = nn.Sequential(
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Softplus()
        )

        # 粒度（coarse/medium/fine）
        self.granularity_head = nn.Linear(128, 3)

    def forward(self, task_vec: torch.Tensor, sys_state: torch.Tensor):
        """
        Args:
            task_vec: [batch, 64] 任务向量
            sys_state: [batch, 4] 系统状态（队列、GPU、平均时间、成功率）

        Returns:
            num_subtasks_logits, parallelism_params, granularity_logits
        """
        x = torch.cat([task_vec, sys_state], dim=-1)
        shared_features = self.shared(x)

        num_logits = self.num_subtasks_head(shared_features)

        para_alpha = self.parallelism_alpha(shared_features) + 1.0  # 至少为 1
        para_beta = self.parallelism_beta(shared_features) + 1.0

        gran_logits = self.granularity_head(shared_features)

        return num_logits, (para_alpha, para_beta), gran_logits

    def sample_action(self, task_vec, sys_state):
        """采样动作"""
        num_logits, (para_alpha, para_beta), gran_logits = self.forward(task_vec, sys_state)

        # 1. 子任务数量（Categorical）
        num_dist = torch.distributions.Categorical(logits=num_logits)
        num_action = num_dist.sample()  # 0-5 → 2-7
        num_log_prob = num_dist.log_prob(num_action)

        # 2. 并行度（Beta）
        para_dist = torch.distributions.Beta(para_alpha.squeeze(-1), para_beta.squeeze(-1))
        parallelism = para_dist.sample()
        para_log_prob = para_dist.log_prob(parallelism)

        # 3. 粒度（Categorical）
        gran_dist = torch.distributions.Categorical(logits=gran_logits)
        gran_action = gran_dist.sample()
        gran_log_prob = gran_dist.log_prob(gran_action)

        # 总 log_prob
        total_log_prob = num_log_prob + para_log_prob + gran_log_prob

        action = DecompositionAction(
            num_subtasks=int(num_action.item()) + 2,  # 2-7
            parallelism=float(parallelism.item()),
            granularity=['coarse', 'medium', 'fine'][gran_action.item()]
        )

        return action, total_log_prob


class CriticNetwork(nn.Module):
    """Critic：评估状态价值"""

    def __init__(self, task_dim: int = 64, state_dim: int = 4):
        super().__init__()

        self.net = nn.Sequential(
            nn.Linear(task_dim + state_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.ReLU(),
            nn.Linear(128, 1)
        )

    def forward(self, task_vec, sys_state):
        x = torch.cat([task_vec, sys_state], dim=-1)
        value = self.net(x)
        return value


class RewardCalculator:
    """奖励计算器：多目标奖励"""

    def __init__(
        self,
        lambda_cost: float = 0.5,  # 成本权重
        beta_success: float = 10.0,  # 成功奖励
    ):
        self.lambda_cost = lambda_cost
        self.beta_success = beta_success

    def compute_reward(
        self,
        execution_time: float,
        api_cost: float,
        success: bool,
        baseline_time: float = 10.0,
        baseline_cost: float = 0.5,
    ) -> float:
        """
        计算奖励

        Reward = -norm_time - λ * norm_cost + β * success

        归一化：让时间和成本在同一量级
        """
        # 归一化时间（相对 baseline）
        norm_time = execution_time / baseline_time

        # 归一化成本
        norm_cost = api_cost / baseline_cost

        # 成功奖励
        success_reward = self.beta_success if success else -self.beta_success

        reward = -norm_time - self.lambda_cost * norm_cost + success_reward

        return reward


class PPOTrainer:
    """PPO 训练器"""

    def __init__(
        self,
        task_encoder: TaskEncoder,
        actor: ActorNetwork,
        critic: CriticNetwork,
        lr_actor: float = 3e-4,
        lr_critic: float = 1e-3,
        gamma: float = 0.99,
        epsilon: float = 0.2,  # PPO clip 参数
        epochs: int = 10,
    ):
        self.task_encoder = task_encoder
        self.actor = actor
        self.critic = critic
        self.reward_calc = RewardCalculator()

        self.optimizer_actor = optim.Adam(
            list(task_encoder.parameters()) + list(actor.parameters()),
            lr=lr_actor
        )
        self.optimizer_critic = optim.Adam(critic.parameters(), lr=lr_critic)

        self.gamma = gamma
        self.epsilon = epsilon
        self.epochs = epochs

        self.buffer = deque(maxlen=2048)

    def store_experience(self, exp: Experience):
        """存储经验"""
        self.buffer.append(exp)

    def train_step(self):
        """训练一步（PPO）"""
        if len(self.buffer) < 64:
            return {}

        # 采样 batch
        batch = random.sample(self.buffer, min(64, len(self.buffer)))

        # 提取数据
        states = torch.stack([exp.state for exp in batch])
        task_vecs = states[:, :64]
        sys_states = states[:, 64:]

        old_log_probs = torch.tensor([exp.log_prob for exp in batch])
        rewards = torch.tensor([exp.reward for exp in batch])
        old_values = torch.tensor([exp.value for exp in batch])

        # 计算优势（GAE）
        advantages = rewards - old_values
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        # PPO 更新
        for _ in range(self.epochs):
            # 重新计算当前策略的 log_prob 和 value
            # （这里简化，实际需要重新 forward）
            values = self.critic(task_vecs, sys_states).squeeze(-1)

            # Actor loss（PPO clip）
            # ratio = exp(new_log_prob - old_log_prob)
            # 这里简化，实际需要重新采样动作

            # Critic loss
            value_loss = nn.MSELoss()(values, rewards)

            self.optimizer_critic.zero_grad()
            value_loss.backward()
            self.optimizer_critic.step()

        return {
            'value_loss': value_loss.item(),
            'mean_reward': rewards.mean().item(),
        }


class RLTaskDecomposer:
    """RL 任务分解器（主类）"""

    def __init__(self, device: str = 'cuda' if torch.cuda.is_available() else 'cpu'):
        self.device = device

        # 初始化网络
        self.task_encoder = TaskEncoder().to(device)
        self.actor = ActorNetwork().to(device)
        self.critic = CriticNetwork().to(device)

        # 训练器
        self.trainer = PPOTrainer(
            self.task_encoder,
            self.actor,
            self.critic
        )

        # Tokenizer（简化版，实际用 Hugging Face）
        self.vocab = self._build_vocab()

    def _build_vocab(self):
        """构建词表（简化）"""
        # 实际应该用 BPE tokenizer
        return {"<pad>": 0, "<unk>": 1}

    def tokenize(self, text: str) -> torch.Tensor:
        """文本 → token IDs（简化）"""
        # 实际用 transformers.AutoTokenizer
        words = text.lower().split()[:50]  # 截断
        ids = [self.vocab.get(w, 1) for w in words]
        ids += [0] * (50 - len(ids))  # padding
        return torch.tensor(ids, dtype=torch.long)

    def encode_system_state(self, sys_state: SystemState) -> torch.Tensor:
        """系统状态 → 向量"""
        return torch.tensor([
            sys_state.queue_length / 100.0,  # 归一化
            sys_state.gpu_utilization,
            sys_state.avg_task_time / 10.0,
            sys_state.recent_success_rate,
        ], dtype=torch.float32)

    def decompose(
        self,
        task_description: str,
        sys_state: SystemState,
    ) -> Tuple[DecompositionAction, float]:
        """
        分解任务

        Returns:
            action, log_prob
        """
        self.task_encoder.eval()
        self.actor.eval()

        with torch.no_grad():
            # 编码任务
            task_tokens = self.tokenize(task_description).unsqueeze(0).to(self.device)
            task_vec = self.task_encoder(task_tokens)

            # 编码系统状态
            sys_vec = self.encode_system_state(sys_state).unsqueeze(0).to(self.device)

            # 采样动作
            action, log_prob = self.actor.sample_action(task_vec, sys_vec)

        return action, log_prob.item()

    def train_from_trajectory(
        self,
        task_description: str,
        sys_state: SystemState,
        action: DecompositionAction,
        log_prob: float,
        execution_time: float,
        api_cost: float,
        success: bool,
    ):
        """从一条轨迹训练"""
        # 编码状态
        task_tokens = self.tokenize(task_description).unsqueeze(0).to(self.device)
        task_vec = self.task_encoder(task_tokens)
        sys_vec = self.encode_system_state(sys_state).unsqueeze(0).to(self.device)

        state = torch.cat([task_vec, sys_vec], dim=-1).squeeze(0)

        # 计算奖励
        reward = self.trainer.reward_calc.compute_reward(
            execution_time, api_cost, success
        )

        # 计算 value
        with torch.no_grad():
            value = self.critic(task_vec, sys_vec).item()

        # 存储经验
        exp = Experience(
            state=state,
            action=action,
            reward=reward,
            next_state=state,  # 简化（实际需要下一个状态）
            done=True,
            log_prob=log_prob,
            value=value,
        )
        self.trainer.store_experience(exp)

        # 训练
        stats = self.trainer.train_step()

        return reward, stats

    def save(self, path: str):
        """保存模型"""
        torch.save({
            'task_encoder': self.task_encoder.state_dict(),
            'actor': self.actor.state_dict(),
            'critic': self.critic.state_dict(),
        }, path)

    def load(self, path: str):
        """加载模型"""
        checkpoint = torch.load(path, map_location=self.device)
        self.task_encoder.load_state_dict(checkpoint['task_encoder'])
        self.actor.load_state_dict(checkpoint['actor'])
        self.critic.load_state_dict(checkpoint['critic'])


# 使用示例
if __name__ == "__main__":
    # 初始化
    decomposer = RLTaskDecomposer()

    # 任务和系统状态
    task = "设计一个支持 1M QPS 的分布式缓存系统"
    sys_state = SystemState(
        queue_length=5,
        gpu_utilization=0.7,
        avg_task_time=8.5,
        recent_success_rate=0.85,
    )

    # 分解
    action, log_prob = decomposer.decompose(task, sys_state)

    print(f"分解策略：")
    print(f"  子任务数量：{action.num_subtasks}")
    print(f"  并行度：{action.parallelism:.2f}")
    print(f"  粒度：{action.granularity}")
    print(f"  log_prob：{log_prob:.4f}")

    # 模拟执行后训练
    execution_time = 7.2
    api_cost = 0.35
    success = True

    reward, stats = decomposer.train_from_trajectory(
        task, sys_state, action, log_prob,
        execution_time, api_cost, success
    )

    print(f"\n训练反馈：")
    print(f"  奖励：{reward:.4f}")
    print(f"  统计：{stats}")
