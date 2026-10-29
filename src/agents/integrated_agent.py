"""
ReflectiveAgent 集成 - 连接所有组件

将 ReflectiveAgent、DynamicDAG、SystemMonitor、CheckpointManager 整合
"""

import asyncio
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import logging

from src.agents.reflective_agent import (
    ReflectiveAgent,
    SubTask,
    SubTaskStatus,
    ReflectionResult,
)
from src.orchestration.dynamic_dag import DynamicDAG, Task, TaskStatus, DAGExecutor
from src.monitoring.system_monitor import SystemMonitor, SystemState
from src.orchestration.checkpoint import CheckpointManager

logger = logging.getLogger(__name__)


class IntegratedReflectiveAgent:
    """
    集成的反思型 Agent

    整合：
    - ReflectiveAgent（算法核心）
    - DynamicDAG（任务编排）
    - SystemMonitor（状态监控）
    - CheckpointManager（回滚机制）
    """

    def __init__(
        self,
        llm_client,
        checkpoint_dir: Optional[str] = None,
    ):
        self.llm = llm_client

        # 核心组件
        self.agent = ReflectiveAgent(llm_client, reflection_interval=2)
        self.monitor = SystemMonitor(window_size=100)
        self.checkpoint_mgr = CheckpointManager(checkpoint_dir=checkpoint_dir)

        # 执行状态
        self.current_dag: Optional[DynamicDAG] = None
        self.completed_tasks = 0

    async def execute_task(
        self,
        task_description: str,
        executor_func: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        执行任务（完整流程）

        Args:
            task_description: 任务描述
            executor_func: 实际执行函数（可选，用于测试）

        Returns:
            执行结果
        """
        start_time = datetime.now()

        # 1. 获取系统状态
        system_state = self.monitor.get_current_state()
        logger.info(f"System state: CPU={system_state.cpu_utilization:.1%}, "
                   f"Memory={system_state.memory_usage:.1%}, "
                   f"Queue={system_state.queue_length}")

        # 2. 初始规划（使用 ReflectiveAgent）
        logger.info("Creating initial plan...")
        subtasks = await self.agent._initial_plan(task_description, system_state)

        # 3. 转换为 DynamicDAG
        self.current_dag = self._subtasks_to_dag(subtasks)

        # 4. 创建初始 checkpoint
        initial_cp = self.checkpoint_mgr.create_checkpoint(
            self.current_dag,
            reason="Initial plan"
        )
        logger.info(f"Created checkpoint: {initial_cp}")

        # 5. 执行-反思循环
        reflections = []
        self.completed_tasks = 0

        while not self.current_dag.is_complete():
            # 5.1 执行一批任务
            ready_tasks = self.current_dag.get_ready_tasks()

            if not ready_tasks:
                # 死锁检测
                pending_count = self.current_dag.get_statistics()["pending"]
                if pending_count > 0:
                    logger.warning("Deadlock detected!")
                    reflection = await self._handle_deadlock(
                        task_description, system_state
                    )
                    reflections.append(reflection)

                    if not reflection.need_replan:
                        break
                else:
                    break

            # 5.2 执行任务
            for task in ready_tasks[:3]:  # 限制并行度
                await self._execute_dag_task(task, executor_func)
                self.completed_tasks += 1

                # 记录到监控
                self.monitor.record_execution(
                    task.task_id,
                    task.status == TaskStatus.COMPLETED,
                    task.execution_time or 0
                )

            # 5.3 定期反思
            if self.completed_tasks % self.agent.reflection_interval == 0:
                system_state = self.monitor.get_current_state()

                reflection = await self._reflect_and_adjust(
                    task_description,
                    system_state
                )
                reflections.append(reflection)

                # 如果重新规划，创建 checkpoint
                if reflection.need_replan:
                    cp_id = self.checkpoint_mgr.create_checkpoint(
                        self.current_dag,
                        reason=f"After reflection: {reflection.reason}"
                    )
                    logger.info(f"Created checkpoint after replan: {cp_id}")

        # 6. 最终反思
        final_reflection = await self.agent._final_reflect(
            task_description,
            self._dag_to_subtasks(self.current_dag)
        )
        reflections.append(final_reflection)

        # 7. 收集结果
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        stats = self.current_dag.get_statistics()
        success = stats["completed"] == stats["total"]

        result = {
            "success": success,
            "task_description": task_description,
            "execution_time": execution_time,
            "dag_statistics": stats,
            "reflections": [
                {
                    "need_replan": r.need_replan,
                    "reason": r.reason,
                    "actions": r.actions
                }
                for r in reflections
            ],
            "reflection_count": sum(1 for r in reflections if r.need_replan),
            "checkpoints": self.checkpoint_mgr.list_checkpoints(),
            "system_stats": self.monitor.get_statistics(),
        }

        logger.info(f"Task completed: success={success}, time={execution_time:.2f}s, "
                   f"reflections={result['reflection_count']}")

        return result

    def _subtasks_to_dag(self, subtasks: list) -> DynamicDAG:
        """将 SubTask 列表转换为 DynamicDAG"""
        dag = DynamicDAG()

        for st in subtasks:
            task = Task(
                task_id=st.id,
                task_type="subtask",
                description=st.description,
                dependencies=st.dependencies,
                status=self._convert_status(st.status),
            )
            dag.add_task(task)

        dag.validate()
        return dag

    def _dag_to_subtasks(self, dag: DynamicDAG) -> list:
        """将 DynamicDAG 转换为 SubTask 列表"""
        subtasks = []

        for task in dag.tasks.values():
            st = SubTask(
                id=task.task_id,
                description=task.description,
                status=self._convert_status_reverse(task.status),
                result=task.result,
                error=task.error,
                dependencies=task.dependencies.copy()
            )
            if task.start_time:
                st.start_time = task.start_time.timestamp()
            if task.end_time:
                st.end_time = task.end_time.timestamp()

            subtasks.append(st)

        return subtasks

    def _convert_status(self, status: SubTaskStatus) -> TaskStatus:
        """SubTaskStatus → TaskStatus"""
        mapping = {
            SubTaskStatus.PENDING: TaskStatus.PENDING,
            SubTaskStatus.RUNNING: TaskStatus.RUNNING,
            SubTaskStatus.SUCCESS: TaskStatus.COMPLETED,
            SubTaskStatus.FAILED: TaskStatus.FAILED,
            SubTaskStatus.SKIPPED: TaskStatus.SKIPPED,
        }
        return mapping.get(status, TaskStatus.PENDING)

    def _convert_status_reverse(self, status: TaskStatus) -> SubTaskStatus:
        """TaskStatus → SubTaskStatus"""
        mapping = {
            TaskStatus.PENDING: SubTaskStatus.PENDING,
            TaskStatus.RUNNING: SubTaskStatus.RUNNING,
            TaskStatus.COMPLETED: SubTaskStatus.SUCCESS,
            TaskStatus.FAILED: SubTaskStatus.FAILED,
            TaskStatus.SKIPPED: SubTaskStatus.SKIPPED,
        }
        return mapping.get(status, SubTaskStatus.PENDING)

    async def _execute_dag_task(
        self,
        task: Task,
        executor_func: Optional[Callable] = None
    ):
        """执行单个 DAG 任务"""
        task.status = TaskStatus.RUNNING
        task.start_time = datetime.now()

        try:
            if executor_func:
                # 使用提供的执行函数
                result = await asyncio.to_thread(executor_func, task)
            else:
                # 使用 LLM 执行
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

    async def _reflect_and_adjust(
        self,
        task_description: str,
        system_state: SystemState
    ) -> ReflectionResult:
        """反思并调整 DAG"""
        # 获取当前子任务列表
        subtasks = self._dag_to_subtasks(self.current_dag)

        # 调用 ReflectiveAgent 的反思逻辑
        reflection = await self.agent._reflect(
            task_description,
            subtasks,
            system_state
        )

        if reflection.need_replan:
            logger.info(f"Replanning: {reflection.reason}")

            # 应用调整到 DAG
            self._apply_reflection_to_dag(reflection)

        return reflection

    def _apply_reflection_to_dag(self, reflection: ReflectionResult):
        """将反思结果应用到 DAG"""
        # 1. 删除任务
        for task_id in reflection.remove_subtask_ids:
            self.current_dag.remove_task_runtime(task_id, reason=reflection.reason)

        # 2. 修改任务
        for task_id, new_desc in reflection.modify_subtasks.items():
            self.current_dag.modify_task_runtime(
                task_id,
                new_description=new_desc,
                reason=reflection.reason
            )

        # 3. 添加新任务
        for new_st in reflection.new_subtasks:
            new_task = Task(
                task_id=new_st.id,
                task_type="subtask",
                description=new_st.description,
                dependencies=new_st.dependencies,
            )
            self.current_dag.add_task_runtime(new_task, reason=reflection.reason)

        # 4. 特殊动作
        if "remove_all_dependencies" in reflection.actions:
            self.current_dag.remove_all_dependencies(reason="Break deadlock")

    async def _handle_deadlock(
        self,
        task_description: str,
        system_state: SystemState
    ) -> ReflectionResult:
        """处理死锁"""
        subtasks = self._dag_to_subtasks(self.current_dag)

        reflection = await self.agent._reflect_on_deadlock(
            task_description,
            subtasks,
            system_state
        )

        if reflection.need_replan:
            self._apply_reflection_to_dag(reflection)

        return reflection
