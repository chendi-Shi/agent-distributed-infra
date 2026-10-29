"""
简化版事件驱动调度模拟器 - 修复版

核心修复：
1. 任务初始化时全部标记为 pending
2. 第一个事件必须触发任务就绪检查
3. 空结果保护
"""

import heapq
import random
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from collections import defaultdict


@dataclass
class Task:
    """单个子任务"""
    task_id: str
    workflow_id: str
    estimated_time: float
    actual_time: float
    dependencies: List[str] = field(default_factory=list)

    status: str = "pending"
    submit_time: float = 0.0
    start_time: Optional[float] = None
    finish_time: Optional[float] = None

    def latency(self) -> Optional[float]:
        if self.finish_time is None:
            return None
        return self.finish_time - self.submit_time


@dataclass
class Event:
    time: float
    event_type: str  # "arrival" / "completion"
    task_id: Optional[str] = None

    def __lt__(self, other):
        return self.time < other.time


class WorkflowGenerator:
    def __init__(self, seed: int = 42):
        random.seed(seed)
        np.random.seed(seed)

    def generate_workflow(
        self,
        workflow_id: str,
        submit_time: float,
        num_tasks: int = 5,
        parallelism: float = 0.3,
    ) -> List[Task]:
        tasks = []

        for i in range(num_tasks):
            log_mean, log_std = 1.5, 0.8
            actual_time = np.random.lognormal(log_mean, log_std)
            estimated_time = max(0.5, actual_time * np.random.normal(1.0, 0.2))

            dependencies = []
            if i > 0:
                if random.random() > parallelism:
                    dependencies.append(f"{workflow_id}_task_{i-1}")
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
    def priority(self, task: Task, queue_state: Dict) -> float:
        raise NotImplementedError


class FIFOScheduler(Scheduler):
    def priority(self, task: Task, queue_state: Dict) -> float:
        return -task.submit_time


class ShortestFirstScheduler(Scheduler):
    def priority(self, task: Task, queue_state: Dict) -> float:
        return -task.estimated_time


class CriticalPathScheduler(Scheduler):
    def __init__(self):
        self.depth_cache = {}

    def priority(self, task: Task, queue_state: Dict) -> float:
        depth = self._compute_downstream_depth(task, queue_state)
        return depth * task.estimated_time

    def _compute_downstream_depth(self, task: Task, queue_state: Dict) -> int:
        if task.task_id in self.depth_cache:
            return self.depth_cache[task.task_id]

        all_tasks = queue_state["all_tasks"]
        downstream = [
            t for t in all_tasks.values()
            if task.task_id in t.dependencies
        ]

        if not downstream:
            depth = 1
        else:
            depth = 1 + max(
                self._compute_downstream_depth(d, queue_state)
                for d in downstream
            )

        self.depth_cache[task.task_id] = depth
        return depth


class OracleScheduler(Scheduler):
    def priority(self, task: Task, queue_state: Dict) -> float:
        return -task.actual_time


class Simulator:
    def __init__(self, scheduler: Scheduler, num_workers: int = 4):
        self.scheduler = scheduler
        self.num_workers = num_workers

        self.current_time = 0.0
        self.event_queue = []
        self.all_tasks: Dict[str, Task] = {}
        self.ready_queue: List[Task] = []
        self.running_tasks: List[Task] = []
        self.completed_tasks: List[Task] = []

        self.stats = {
            "total_tasks": 0,
            "task_latencies": [],
        }

    def add_workflow(self, tasks: List[Task], arrival_time: float):
        # 添加到达事件
        heapq.heappush(
            self.event_queue,
            Event(time=arrival_time, event_type="arrival", task_id=None)
        )

        # 注册所有任务
        for task in tasks:
            task.submit_time = arrival_time
            task.status = "pending"
            self.all_tasks[task.task_id] = task

        self.stats["total_tasks"] += len(tasks)

    def run(self):
        """运行模拟"""
        max_iterations = 100000
        iteration = 0

        while (self.event_queue or self.running_tasks or self.ready_queue) and iteration < max_iterations:
            iteration += 1

            # 处理下一个事件
            if self.event_queue:
                event = heapq.heappop(self.event_queue)
                self.current_time = event.time

                if event.event_type == "completion":
                    self._handle_completion(event.task_id)

            # 更新就绪队列
            self._update_ready_queue()

            # 调度任务
            self._schedule_tasks()

            # 防止死循环
            if not self.event_queue and not self.running_tasks:
                break

        if iteration >= max_iterations:
            print(f"Warning: Simulator reached max iterations")

    def _handle_completion(self, task_id: str):
        task = self.all_tasks[task_id]
        task.status = "done"
        task.finish_time = self.current_time

        self.running_tasks.remove(task)
        self.completed_tasks.append(task)
        self.stats["task_latencies"].append(task.latency())

    def _update_ready_queue(self):
        """检查所有 pending 任务，依赖满足的变为 ready"""
        for task in list(self.all_tasks.values()):
            if task.status != "pending":
                continue

            # 检查时间
            if self.current_time < task.submit_time:
                continue

            # 检查依赖
            deps_satisfied = all(
                self.all_tasks.get(dep_id, Task("", "", 0, 0, status="done")).status == "done"
                for dep_id in task.dependencies
            )

            if deps_satisfied:
                task.status = "ready"
                self.ready_queue.append(task)

    def _schedule_tasks(self):
        """从就绪队列选任务执行"""
        while len(self.running_tasks) < self.num_workers and self.ready_queue:
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
                Event(time=completion_time, event_type="completion", task_id=task.task_id)
            )

    def get_results(self) -> Dict:
        latencies = self.stats["task_latencies"]

        if len(latencies) == 0:
            return {
                "mean_latency": 0,
                "p50_latency": 0,
                "p95_latency": 0,
                "p99_latency": 0,
                "max_latency": 0,
                "total_tasks": 0,
            }

        return {
            "mean_latency": np.mean(latencies),
            "p50_latency": np.percentile(latencies, 50),
            "p95_latency": np.percentile(latencies, 95),
            "p99_latency": np.percentile(latencies, 99),
            "max_latency": np.max(latencies),
            "total_tasks": len(latencies),
        }


def run_comparison(num_workflows: int = 50, num_workers: int = 4, arrival_rate: float = 0.1):
    print(f"=== Scheduling Simulation ===")
    print(f"Workflows: {num_workflows}, Workers: {num_workers}, λ={arrival_rate}/s\n")

    # 生成工作流
    generator = WorkflowGenerator(seed=42)
    workflows = []

    current_time = 0.0
    for i in range(num_workflows):
        interarrival = np.random.exponential(1.0 / arrival_rate)
        current_time += interarrival

        tasks = generator.generate_workflow(
            workflow_id=f"wf_{i}",
            submit_time=current_time,
            num_tasks=random.randint(3, 7),
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
        sim = Simulator(scheduler=scheduler, num_workers=num_workers)

        for arrival_time, tasks in workflows:
            sim.add_workflow(tasks, arrival_time)

        sim.run()
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

    # 计算改进
    print("\n=== Improvement over FIFO ===")
    baseline_p95 = results["FIFO"]["p95_latency"]

    for name in ["ShortestFirst", "CriticalPath", "Oracle"]:
        p95 = results[name]["p95_latency"]
        improvement = (baseline_p95 - p95) / baseline_p95 * 100
        print(f"{name:<15}: {improvement:>6.1f}% (P95: {p95:.2f}s vs {baseline_p95:.2f}s)")

    # 判断
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
    results = run_comparison(
        num_workflows=100,
        num_workers=4,
        arrival_rate=0.2,
    )
