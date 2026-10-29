"""
主动学习样本选择器

从收集的轨迹中，挑选最有价值的样本进行人工标注

策略：
1. 不确定性采样：模型最不确定的样本
2. 多样性采样：覆盖不同任务类型
3. 代表性采样：选择典型案例
"""

import numpy as np
from typing import List, Dict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from collections import defaultdict


class ActiveLearningSampler:
    """主动学习样本选择器"""

    def __init__(self):
        self.vectorizer = TfidfVectorizer(max_features=100)

    def select_samples(
        self,
        trajectories: List[Dict],
        budget: int = 50,
        strategy: str = "mixed",
    ) -> List[Dict]:
        """
        选择最有价值的样本

        Args:
            trajectories: 候选轨迹列表
            budget: 标注预算（样本数量）
            strategy: 选择策略
                - "uncertainty": 不确定性采样
                - "diversity": 多样性采样
                - "mixed": 混合策略（推荐）

        Returns:
            选中的样本列表
        """
        if len(trajectories) <= budget:
            return trajectories

        if strategy == "uncertainty":
            return self._uncertainty_sampling(trajectories, budget)
        elif strategy == "diversity":
            return self._diversity_sampling(trajectories, budget)
        else:  # mixed
            return self._mixed_sampling(trajectories, budget)

    def _uncertainty_sampling(
        self,
        trajectories: List[Dict],
        budget: int,
    ) -> List[Dict]:
        """
        不确定性采样：优先选择"模型最不确定"的样本

        代理指标：
        1. 子任务数量方差大（复杂度不确定）
        2. 执行时间 / 估计时间偏差大（耗时难预测）
        3. 工具调用序列长度异常
        """
        scores = []

        for traj in trajectories:
            score = 0.0

            # 1. 子任务数量
            num_subtasks = len(traj.get("subtasks", []))
            if num_subtasks > 5 or num_subtasks < 2:
                score += 1.0  # 异常数量

            # 2. 执行时间方差
            execution_time = traj.get("execution_time", 0)
            if execution_time > 30 or execution_time < 1:
                score += 1.0

            # 3. 工具调用数
            num_tool_calls = len(traj.get("tool_calls", []))
            if num_tool_calls > 10 or num_tool_calls < 2:
                score += 0.5

            # 4. 失败但不是完全失败（部分成功 → 边界案例）
            if not traj.get("success") and traj.get("final_result"):
                score += 2.0

            scores.append((score, traj))

        # 按分数排序
        scores.sort(key=lambda x: x[0], reverse=True)
        return [traj for _, traj in scores[:budget]]

    def _diversity_sampling(
        self,
        trajectories: List[Dict],
        budget: int,
    ) -> List[Dict]:
        """
        多样性采样：选择覆盖不同类型的样本

        策略：
        1. 对任务描述做聚类
        2. 从每个簇中选代表性样本
        """
        # 提取任务描述
        task_descriptions = [t.get("task_description", "") for t in trajectories]

        # TF-IDF 向量化
        try:
            vectors = self.vectorizer.fit_transform(task_descriptions)
        except:
            # 如果向量化失败，退回到随机采样
            indices = np.random.choice(len(trajectories), budget, replace=False)
            return [trajectories[i] for i in indices]

        # 聚类（簇数 = budget / 3，每簇选 3 个样本）
        num_clusters = max(1, budget // 3)
        kmeans = KMeans(n_clusters=num_clusters, random_state=42)
        labels = kmeans.fit_predict(vectors)

        # 从每个簇选样本
        selected = []
        clusters = defaultdict(list)
        for i, label in enumerate(labels):
            clusters[label].append((i, trajectories[i]))

        # 每个簇选 quota 个样本
        quota_per_cluster = budget // num_clusters

        for label, items in clusters.items():
            # 在簇内按执行时间排序（选中等复杂度）
            items.sort(key=lambda x: x[1].get("execution_time", 0))

            # 选中间的样本
            start = max(0, len(items) // 2 - quota_per_cluster // 2)
            end = start + quota_per_cluster

            selected.extend([traj for _, traj in items[start:end]])

        # 如果不够，随机补充
        if len(selected) < budget:
            remaining = [t for t in trajectories if t not in selected]
            needed = budget - len(selected)
            selected.extend(np.random.choice(remaining, min(needed, len(remaining)), replace=False))

        return selected[:budget]

    def _mixed_sampling(
        self,
        trajectories: List[Dict],
        budget: int,
    ) -> List[Dict]:
        """
        混合策略：结合不确定性和多样性

        - 50% 不确定性采样
        - 50% 多样性采样
        """
        budget_uncertainty = budget // 2
        budget_diversity = budget - budget_uncertainty

        # 不确定性采样
        uncertain_samples = self._uncertainty_sampling(trajectories, budget_uncertainty)

        # 从剩余样本中做多样性采样
        remaining = [t for t in trajectories if t not in uncertain_samples]
        diverse_samples = self._diversity_sampling(remaining, budget_diversity)

        return uncertain_samples + diverse_samples


def select_for_annotation(
    store,
    budget: int = 50,
    strategy: str = "mixed",
) -> List[Dict]:
    """
    选择待标注样本（便捷函数）

    Args:
        store: PostgresTrajectoryStore 实例
        budget: 标注预算
        strategy: 选择策略

    Returns:
        选中的轨迹列表
    """
    # 1. 计算优先级
    store.compute_annotation_priorities()

    # 2. 获取候选样本（取 budget * 3，再筛选）
    candidates = store.get_trajectories_for_annotation(limit=budget * 3)

    if len(candidates) <= budget:
        return candidates

    # 3. 主动学习选择
    sampler = ActiveLearningSampler()
    selected = sampler.select_samples(candidates, budget, strategy)

    return selected


if __name__ == "__main__":
    from src.monitoring.postgres_trajectory_store import PostgresTrajectoryStore

    # 测试
    store = PostgresTrajectoryStore()

    print("Selecting samples for annotation...")
    selected = select_for_annotation(store, budget=20, strategy="mixed")

    print(f"\n✅ Selected {len(selected)} samples:")
    for i, traj in enumerate(selected, 1):
        print(f"{i}. {traj['task_description'][:60]}... ({traj['mode']}, {traj['task_type']})")
