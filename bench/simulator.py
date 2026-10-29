"""
事件驱动调度模拟器

目标：
1. 模拟 agent 工作流的调度过程（不需要真实 LLM 推理）
2. 对比 FIFO / CriticalPath / ShortestFirst / Oracle 四种策略
3. 计算调度优化的理论上界

关键：
- 任务耗时用概率分布（对数正态，模拟 LLM 生成抖动）
- DAG 依赖关系（子任务间有依赖）
- 队列动力学（并发度限制）
- Oracle 策略：用未来信息（任务真实耗时）做最优决策
"""

import heapq
import random
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
from collections import defaultdict
import networkx as nx


@dataclass
class Task:
    """单个子任务"""
    task_id: str
    workflow_id: str  # 所属工作流
    estimated_time: float  # 估计耗时（调度器可见）
    actual_time: float  # 真实耗时（只有 oracle 可见）
    dependencies: List[str] = field(default_factory=list)  # 前置依赖

    # 运行时状态
    status: str = "pending"  # pending / ready / running / done
    submit_time: float = 0.0
    start_time: Optional[float] = None
    finish_time: Optional[float] = None

    def latency(self) -> Optional[float]:
        """任务延迟：完成时间 - 提交时间"""
        if self.finish_time is None:
            return None
        return self.finish_time - self.submit_time


@dataclass
class Event:
    """事件：任务完成或新任务到达"""
    time: float
    event_type: str  # "arrival" / "completion"
    task_id: Optional[str] = None

    def __lt__(self, other):
        return self.time < other.time


class WorkflowGenerator:
    """生成 agent 工作流（DAG）"""

    def __init__(self, seed: int = 42):
        random.seed(seed)
        np.random.seed(seed)

    def generate_workflow(
        self,
        workflow_id: str,
        submit_time: float,
        num_tasks: int = 5,
        parallelism: float = 0.3,  # 可并行任务比例
    ) -> List[Task]:
        """
        生成一个工作流（DAG）

        Args:
            workflow_id: 工作流 ID
            submit_time: 提交时间
            num_tasks: 子任务数量
            parallelism: 并行度（0=串行，1=全并行）

        Returns:
            任务列表（带依赖关系）
        """
        tasks = []

        for i in range(num_tasks):
            # 服务时间：对数正态分布（模拟 LLM 生成抖动）
            # μ=1.5, σ=0.8 → 中位数 ~4.5s，长尾到 20s+
            log_mean = 1.5
            log_std = 0.8
            actual_time = np.random.lognormal(log_mean, log_std)

            # 估计时间：真实时间 + 高斯噪声
            estimated_time = actual_time * np.random.normal(1.0, 0.2)
            estimated_time = max(0.5, estimated_time)  # 至少 0.5s

            # 依赖关系：随机选择前面的任务作为依赖
            dependencies = []
            if i > 0:
                # 串行任务：依赖上一个
                if random.random() > parallelism:
                    dependencies.append(f"{workflow_id}_task_{i-1}")
                # 并行任务：可能依赖更早的任务（形成 DAG）
                elif i > 1 and random.random() < 0.3:
                    dep_idx = random.randint(0, i-2)
                    dependencies.append(f"{workflow_id}_task_{dep_idx}")

            task = Task(
                task_id=f"{workflow_id}_task_{i}",
                workflow_id=workflow_id,
                estimated_time=estimated_time,
                actual_time=actual_time,
                dependencies=dependencies,
                submit_time=submit_time,
            )
            tasks.append(task)

        return tasks


class Scheduler:
    """调度器基类"""

    def priority(self, task: Task, queue_state: Dict) -> float:
        """
        计算任务优先级（分数越高越优先）

        Args:
            task: 待调度任务
            queue_state: 当前队列状态（包含所有任务信息）

        Returns:
            优先级分数
        """
        raise NotImplementedError


class FIFOScheduler(Scheduler):
    """先进先出"""

    def priority(self, task: Task, queue_state: Dict) -> float:
        return -task.submit_time  # 提交越早越优先


class ShortestFirstScheduler(Scheduler):
    """最短任务优先"""

    def priority(self, task: Task, queue_state: Dict) -> float:
        return -task.estimated_time  # 耗时越短越优先


class CriticalPathScheduler(Scheduler):
    """关键路径优先（考虑下游依赖深度）"""

    def __init__(self):
        self.depth_cache = {}

    def priority(self, task: Task, queue_state: Dict) -> float:
        """优先级 = 下游深度 × 估计耗时"""
        depth = self._compute_downstream_depth(task, queue_state)
        return depth * task.estimated_time

    def _compute_downstream_depth(self, task: Task, queue_state: Dict) -> int:
        """计算任务到叶子节点的最长路径（动态规划）"""
        if task.task_id in self.depth_cache:
            return self.depth_cache[task.task_id]

        all_tasks = queue_state["all_tasks"]

        # 找出依赖该任务的下游任务
        downstream = [
            t for t in all_tasks.values()
            if task.task_id in t.dependencies
        ]

        if not downstream:
            depth = 1  # 叶子节点
        else:
            depth = 1 + max(
                self._compute_downstream_depth(d, queue_state)
                for d in downstream
            )

        self.depth_cache[task.task_id] = depth
        return depth


class OracleScheduler(Scheduler):
    """Oracle 调度器（用真实耗时，只能离线模拟）"""

    def priority(self, task: Task, queue_state: Dict) -> float:
        """直接用真实耗时排序（最优解）"""
        # 最短真实耗时优先
        return -task.actual_time


class Simulator:
    """事件驱动模拟器"""

    def __init__(
        self,
        scheduler: Scheduler,
        num_workers: int = 4,  # 并发度
    ):
        self.scheduler = scheduler
        self.num_workers = num_workers

        # 运行时状态
        self.current_time = 0.0
        self.event_queue = []  # 优先队列（最小堆）
        self.all_tasks: Dict[str, Task] = {}  # 所有任务
        self.ready_queue: List[Task] = []  # 就绪队列
        self.running_tasks: List[Task] = []  # 正在运行的任务
        self.completed_tasks: List[Task] = []  # 已完成任务

        # 统计信息
        self.stats = {
            "total_tasks": 0,
            "total_workflows": 0,
            "task_latencies": [],
            "workflow_latencies": [],
        }

    def add_workflow(self, tasks: List[Task], arrival_time: float):
        """添加一个工作流"""
        heapq.heappush(
            self.event_queue,
            Event(time=arrival_time, event_type="arrival", task_id=None)
        )

        for task in tasks:
            task.submit_time = arrival_time
            self.all_tasks[task.task_id] = task

        self.stats["total_tasks"] += len(tasks)
        self.stats["total_workflows"] += 1

    def run(self):
        """运行模拟"""
        while self.event_queue or self.running_tasks:
            # 1. 处理下一个事件
            if self.event_queue:
                event = heapq.heappop(self.event_queue)
                self.current_time = event.time

                if event.event_type == "arrival":
                    self._handle_arrival()
                elif event.event_type == "completion":
                    self._handle_completion(event.task_id)

            # 2. 更新就绪队列（依赖已满足的任务）
            self._update_ready_queue()

            # 3. 调度新任务（如果有空闲 worker）
            self._schedule_tasks()

    def _handle_arrival(self):
        """处理任务到达事件"""
        # 所有 pending 任务变为 ready（如果依赖满足）
        pass  # 在 _update_ready_queue 中统一处理

    def _handle_completion(self, task_id: str):
        """处理任务完成事件"""
        task = self.all_tasks[task_id]
        task.status = "done"
        task.finish_time = self.current_time

        self.running_tasks.remove(task)
        self.completed_tasks.append(task)
        self.stats["task_latencies"].append(task.latency())

    def _update_ready_queue(self):
        """更新就绪队列：找出依赖已满足的任务"""
        for task in self.all_tasks.values():
            if task.status == "pending":
                # 检查是否到达
                if self.current_time < task.submit_time:
                    continue

                # 检查依赖是否满足
                deps_satisfied = all(
                    self.all_tasks[dep_id].status == "done"
                    for dep_id in task.dependencies
                )

                if deps_satisfied:
                    task.status = "ready"
                    self.ready_queue.append(task)

    def _schedule_tasks(self):
        """调度任务：从就绪队列选任务到空闲 worker"""
        while len(self.running_tasks) < self.num_workers and self.ready_queue:
            # 计算每个任务的优先级
            queue_state = {
                "all_tasks": self.all_tasks,
                "ready_queue": self.ready_queue,
                "running_tasks": self.running_tasks,
                "current_time": self.current_time,
            }

            priorities = [
                (self.scheduler.priority(task, queue_state), task)
                for task in self.ready_queue
            ]

            # 选最高优先级任务
            priorities.sort(key=lambda x: x[0], reverse=True)
            _, task = priorities[0]

            # 开始执行
            task.status = "running"
            task.start_time = self.current_time
            self.ready_queue.remove(task)
            self.running_tasks.append(task)

            # 插入完成事件
            completion_time = self.current_time + task.actual_time
            heapq.heappush(
                self.event_queue,
                Event(
                    time=completion_time,
                    event_type="completion",
                    task_id=task.task_id
                )
            )

    def get_results(self) -> Dict:
        """获取统计结果"""
        latencies = self.stats["task_latencies"]

        return {
            "mean_latency": np.mean(latencies),
            "p50_latency": np.percentile(latencies, 50),
            "p95_latency": np.percentile(latencies, 95),
            "p99_latency": np.percentile(latencies, 99),
            "max_latency": np.max(latencies),
            "total_tasks": len(latencies),
        }


def run_comparison(
    num_workflows: int = 50,
    num_workers: int = 4,
    arrival_rate: float = 0.1,  # 每秒到达数（泊松过程）
):
    """
    对比四种调度策略

    Args:
        num_workflows: 工作流数量
        num_workers: 并发度
        arrival_rate: 到达速率（λ）
    """
    print(f"=== Scheduling Simulation ===")
    print(f"Workflows: {num_workflows}, Workers: {num_workers}, λ={arrival_rate}/s\n")

    # 生成工作流
    generator = WorkflowGenerator(seed=42)
    workflows = []

    current_time = 0.0
    for i in range(num_workflows):
        # 泊松到达：指数分布间隔
        interarrival = np.random.exponential(1.0 / arrival_rate)
        current_time += interarrival

        tasks = generator.generate_workflow(
            workflow_id=f"wf_{i}",
            submit_time=current_time,
            num_tasks=random.randint(3, 7),  # 每个工作流 3-7 个任务
            parallelism=0.3,
        )
        workflows.append((current_time, tasks))

    # 对比四种策略
    schedulers = {
        "FIFO": FIFOScheduler(),
        "ShortestFirst": ShortestFirstScheduler(),
        "CriticalPath": CriticalPathScheduler(),
        "Oracle": OracleScheduler(),
    }

    results = {}

    for name, scheduler in schedulers.items():
        # 创建模拟器
        sim = Simulator(scheduler=scheduler, num_workers=num_workers)

        # 添加所有工作流
        for arrival_time, tasks in workflows:
            sim.add_workflow(tasks, arrival_time)

        # 运行模拟
        sim.run()

        # 收集结果
        results[name] = sim.get_results()

    # 打印对比
    print(f"{'Strategy':<15} {'Mean':<8} {'P50':<8} {'P95':<8} {'P99':<8} {'Max':<8}")
    print("-" * 65)

    for name in ["FIFO", "ShortestFirst", "CriticalPath", "Oracle"]:
        r = results[name]
        print(
            f"{name:<15} "
            f"{r['mean_latency']:<8.2f} "
            f"{r['p50_latency']:<8.2f} "
            f"{r['p95_latency']:<8.2f} "
            f"{r['p99_latency']:<8.2f} "
            f"{r['max_latency']:<8.2f}"
        )

    # 计算改进百分比
    print("\n=== Improvement over FIFO ===")
    baseline_p95 = results["FIFO"]["p95_latency"]

    for name in ["ShortestFirst", "CriticalPath", "Oracle"]:
        p95 = results[name]["p95_latency"]
        improvement = (baseline_p95 - p95) / baseline_p95 * 100
        print(f"{name:<15}: {improvement:>6.1f}% (P95: {p95:.2f}s vs {baseline_p95:.2f}s)")

    # 判断收益空间
    cp_improvement = (baseline_p95 - results["CriticalPath"]["p95_latency"]) / baseline_p95 * 100
    oracle_improvement = (baseline_p95 - results["Oracle"]["p95_latency"]) / baseline_p95 * 100
    remaining_space = oracle_improvement - cp_improvement

    print(f"\n=== Decision ===")
    if cp_improvement > 20:
        print(f"✅ CriticalPath improves P95 by {cp_improvement:.1f}% → 调度方向成立")
        print(f"   Oracle 还有 {remaining_space:.1f}% 空间 → 学习型调度有价值")
    elif cp_improvement > 5:
        print(f"⚠️  CriticalPath improves P95 by {cp_improvement:.1f}% → 收益中等")
        print(f"   学习型调度最多再挤 {remaining_space:.1f}%，谨慎评估")
    else:
        print(f"❌ CriticalPath improves P95 by {cp_improvement:.1f}% → 调度方向不成立")
        print(f"   放弃该方向，不要浪费 100 卡时")

    return results


if __name__ == "__main__":
    # 运行模拟
    results = run_comparison(
        num_workflows=100,
        num_workers=4,
        arrival_rate=0.2,  # 0.2 workflows/sec → 平均 5s 间隔
    )
