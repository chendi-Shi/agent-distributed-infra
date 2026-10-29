"""
Baseline Agent - 传统 Multi-Agent（无反思）

用于对比实验：
- 一次性分解任务
- 按依赖顺序执行
- 无动态调整
- 无错误恢复
"""

import asyncio
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
import logging

from src.orchestration.task_dag import Task, TaskStatus, TaskDAG, WorkflowBuilder
from src.monitoring.system_monitor import SystemMonitor

logger = logging.getLogger(__name__)


class BaselineAgent:
    """
    Baseline Agent - 传统方式

    特点：
    1. 一次性规划，不反思
    2. 静态 DAG，不修改
    3. 失败即停止，不恢复
    """

    def __init__(self, llm_client):
        self.llm = llm_client
        self.monitor = SystemMonitor(window_size=100)

    async def execute_task(
        self,
        task_description: str,
        executor_func: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        执行任务（传统方式）

        Args:
            task_description: 任务描述
            executor_func: 实际执行函数（可选）

        Returns:
            执行结果
        """
        start_time = datetime.now()

        # 1. 一次性分解（无系统状态感知）
        logger.info("Decomposing task (one-time planning)...")
        subtasks = await self._decompose_task(task_description)

        # 2. 构建静态 DAG（可能失败）
        try:
            dag = self._build_dag(subtasks)
        except ValueError as e:
            # 规划失败（如循环依赖），直接返回失败
            logger.error(f"Failed to build DAG: {e}")
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            return {
                "success": False,
                "task_description": task_description,
                "execution_time": execution_time,
                "dag_statistics": {"total": 0, "completed": 0, "failed": 1},
                "reflections": [],
                "reflection_count": 0,
                "system_stats": self.monitor.get_statistics(),
                "error": str(e)
            }

        # 3. 按序执行（无反思）
        completed_tasks = 0

        while not dag.is_complete():
            ready_tasks = dag.get_ready_tasks()

            if not ready_tasks:
                # 无可执行任务，检查是否有待执行
                stats = dag.get_statistics()
                if stats["pending"] > 0:
                    logger.error("Deadlock: no ready tasks but pending exist")
                    break
                else:
                    break

            # 执行一批任务
            for task in ready_tasks[:3]:  # 限制并行度
                await self._execute_task(task, executor_func)
                completed_tasks += 1

                # 记录监控
                self.monitor.record_execution(
                    task.task_id,
                    task.status == TaskStatus.COMPLETED,
                    task.execution_time or 0
                )

                # 失败即停止（无错误恢复）
                if task.status == TaskStatus.FAILED:
                    logger.warning(f"Task {task.task_id} failed, stopping execution")
                    # 标记剩余任务为跳过
                    for t in dag.tasks.values():
                        if t.status == TaskStatus.PENDING:
                            t.status = TaskStatus.SKIPPED
                    break

        # 4. 收集结果
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        stats = dag.get_statistics()
        success = stats["completed"] == stats["total"]

        result = {
            "success": success,
            "task_description": task_description,
            "execution_time": execution_time,
            "dag_statistics": stats,
            "reflections": [],  # 无反思
            "reflection_count": 0,
            "system_stats": self.monitor.get_statistics(),
        }

        logger.info(f"Baseline completed: success={success}, time={execution_time:.2f}s")

        return result

    async def _decompose_task(self, task_description: str) -> List[Dict]:
        """一次性分解任务"""
        prompt = f"""
任务：{task_description}

请将任务分解为 3-7 个子任务，格式：
[
  {{"id": "1", "description": "...", "dependencies": []}},
  {{"id": "2", "description": "...", "dependencies": ["1"]}},
  ...
]

要求：
1. 子任务应该具体可执行
2. 合理设置依赖关系
3. 粒度适中
"""

        response = await self.llm.generate(prompt)

        # 解析
        import json
        try:
            subtasks = json.loads(response)
            return subtasks
        except:
            # 降级：单任务
            return [{"id": "1", "description": task_description, "dependencies": []}]

    def _build_dag(self, subtasks: List[Dict]) -> TaskDAG:
        """构建静态 DAG"""
        builder = WorkflowBuilder()

        for st in subtasks:
            builder.add_task(
                task_id=st["id"],
                task_type="subtask",
                description=st["description"],
                dependencies=st.get("dependencies", [])
            )

        return builder.build()

    async def _execute_task(
        self,
        task: Task,
        executor_func: Optional[Callable] = None
    ):
        """执行单个任务"""
        task.status = TaskStatus.RUNNING
        task.start_time = datetime.now()

        try:
            if executor_func:
                result = await asyncio.to_thread(executor_func, task)
            else:
                prompt = f"执行任务：{task.description}\n请给出执行结果。"
                result = await self.llm.generate(prompt)

            task.result = result
            task.status = TaskStatus.COMPLETED
            logger.info(f"Task {task.task_id} completed")
        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED
            logger.error(f"Task {task.task_id} failed: {e}")
        finally:
            task.end_time = datetime.now()
