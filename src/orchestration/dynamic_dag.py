"""
Dynamic DAG - 支持运行时修改的任务图

核心功能：
1. 运行时添加/删除/修改任务
2. 动态调整依赖关系
3. 循环依赖检测（实时）
4. 已完成任务的回滚
5. 并发执行协调
"""

from typing import Dict, List, Set, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import logging
from enum import Enum
import copy

from src.orchestration.task_dag import Task, TaskStatus, TaskDAG

logger = logging.getLogger(__name__)


class ModificationAction(str, Enum):
    """DAG 修改动作"""
    ADD_TASK = "add_task"
    REMOVE_TASK = "remove_task"
    MODIFY_TASK = "modify_task"
    ADD_DEPENDENCY = "add_dependency"
    REMOVE_DEPENDENCY = "remove_dependency"
    ROLLBACK_TASK = "rollback_task"


@dataclass
class DAGModification:
    """DAG 修改记录"""
    action: ModificationAction
    timestamp: datetime
    task_id: str
    details: Dict[str, Any] = field(default_factory=dict)
    reason: Optional[str] = None


class DynamicDAG(TaskDAG):
    """
    动态 DAG - 支持运行时修改

    扩展自 TaskDAG，增加：
    - 运行时添加/删除任务
    - 动态依赖调整
    - 修改历史记录
    - 并发安全
    """

    def __init__(self):
        super().__init__()
        self.modifications: List[DAGModification] = []
        self.execution_lock = asyncio.Lock()
        self.is_executing = False

    def add_task_runtime(
        self,
        task: Task,
        reason: Optional[str] = None
    ) -> bool:
        """
        运行时添加任务

        Args:
            task: 要添加的任务
            reason: 添加理由（反思结果）

        Returns:
            是否添加成功
        """
        try:
            # 检查任务 ID 是否冲突
            if task.task_id in self.tasks:
                logger.warning(f"Task {task.task_id} already exists")
                return False

            # 检查依赖是否存在
            for dep_id in task.dependencies:
                if dep_id not in self.tasks:
                    logger.error(f"Dependency {dep_id} does not exist")
                    return False

            # 检查是否会引入循环
            if self._would_create_cycle(task.task_id, task.dependencies):
                logger.error(f"Adding task {task.task_id} would create a cycle")
                return False

            # 添加任务
            self.tasks[task.task_id] = task

            # 记录修改
            mod = DAGModification(
                action=ModificationAction.ADD_TASK,
                timestamp=datetime.now(),
                task_id=task.task_id,
                details={
                    "description": task.description,
                    "dependencies": task.dependencies.copy()
                },
                reason=reason
            )
            self.modifications.append(mod)

            logger.info(f"Added task {task.task_id} at runtime")
            return True

        except Exception as e:
            logger.error(f"Failed to add task {task.task_id}: {e}")
            return False

    def remove_task_runtime(
        self,
        task_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        运行时删除任务

        注意：
        - 不能删除已完成的任务
        - 会自动移除依赖此任务的其他任务的依赖关系

        Args:
            task_id: 任务 ID
            reason: 删除理由

        Returns:
            是否删除成功
        """
        if task_id not in self.tasks:
            logger.warning(f"Task {task_id} does not exist")
            return False

        task = self.tasks[task_id]

        # 不能删除已完成的任务
        if task.status == TaskStatus.COMPLETED:
            logger.warning(f"Cannot remove completed task {task_id}")
            return False

        # 移除其他任务对此任务的依赖
        for other_task in self.tasks.values():
            if task_id in other_task.dependencies:
                other_task.dependencies.remove(task_id)
                logger.info(f"Removed dependency {task_id} from {other_task.task_id}")

        # 删除任务
        removed_task = self.tasks.pop(task_id)

        # 记录修改
        mod = DAGModification(
            action=ModificationAction.REMOVE_TASK,
            timestamp=datetime.now(),
            task_id=task_id,
            details={
                "status": removed_task.status.value,
                "had_dependencies": removed_task.dependencies.copy()
            },
            reason=reason
        )
        self.modifications.append(mod)

        logger.info(f"Removed task {task_id} at runtime")
        return True

    def modify_task_runtime(
        self,
        task_id: str,
        new_description: Optional[str] = None,
        new_parameters: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None
    ) -> bool:
        """
        运行时修改任务

        只能修改未执行的任务

        Args:
            task_id: 任务 ID
            new_description: 新描述
            new_parameters: 新参数
            reason: 修改理由

        Returns:
            是否修改成功
        """
        if task_id not in self.tasks:
            logger.warning(f"Task {task_id} does not exist")
            return False

        task = self.tasks[task_id]

        # 只能修改未执行的任务
        if task.status not in [TaskStatus.PENDING, TaskStatus.FAILED]:
            logger.warning(f"Cannot modify task {task_id} in status {task.status}")
            return False

        old_desc = task.description
        old_params = task.parameters.copy()

        if new_description:
            task.description = new_description

        if new_parameters:
            task.parameters.update(new_parameters)

        # 记录修改
        mod = DAGModification(
            action=ModificationAction.MODIFY_TASK,
            timestamp=datetime.now(),
            task_id=task_id,
            details={
                "old_description": old_desc,
                "new_description": new_description,
                "old_parameters": old_params,
                "new_parameters": new_parameters
            },
            reason=reason
        )
        self.modifications.append(mod)

        logger.info(f"Modified task {task_id} at runtime")
        return True

    def add_dependency_runtime(
        self,
        task_id: str,
        dependency_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        运行时添加依赖

        Args:
            task_id: 任务 ID
            dependency_id: 依赖的任务 ID
            reason: 添加理由

        Returns:
            是否添加成功
        """
        if task_id not in self.tasks:
            logger.warning(f"Task {task_id} does not exist")
            return False

        if dependency_id not in self.tasks:
            logger.warning(f"Dependency {dependency_id} does not exist")
            return False

        task = self.tasks[task_id]

        # 不能给已完成的任务添加依赖
        if task.status == TaskStatus.COMPLETED:
            logger.warning(f"Cannot add dependency to completed task {task_id}")
            return False

        # 检查是否会引入循环
        if self._would_create_cycle(task_id, [dependency_id]):
            logger.error(f"Adding dependency would create a cycle")
            return False

        # 添加依赖
        if dependency_id not in task.dependencies:
            task.dependencies.append(dependency_id)

            # 记录修改
            mod = DAGModification(
                action=ModificationAction.ADD_DEPENDENCY,
                timestamp=datetime.now(),
                task_id=task_id,
                details={"dependency_id": dependency_id},
                reason=reason
            )
            self.modifications.append(mod)

            logger.info(f"Added dependency {dependency_id} to task {task_id}")
            return True

        return False

    def remove_dependency_runtime(
        self,
        task_id: str,
        dependency_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        运行时移除依赖

        Args:
            task_id: 任务 ID
            dependency_id: 要移除的依赖 ID
            reason: 移除理由

        Returns:
            是否移除成功
        """
        if task_id not in self.tasks:
            logger.warning(f"Task {task_id} does not exist")
            return False

        task = self.tasks[task_id]

        if dependency_id in task.dependencies:
            task.dependencies.remove(dependency_id)

            # 记录修改
            mod = DAGModification(
                action=ModificationAction.REMOVE_DEPENDENCY,
                timestamp=datetime.now(),
                task_id=task_id,
                details={"dependency_id": dependency_id},
                reason=reason
            )
            self.modifications.append(mod)

            logger.info(f"Removed dependency {dependency_id} from task {task_id}")
            return True

        return False

    def rollback_task(
        self,
        task_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        回滚任务到 PENDING 状态

        用于反思后决定重新执行某个任务

        Args:
            task_id: 任务 ID
            reason: 回滚理由

        Returns:
            是否回滚成功
        """
        if task_id not in self.tasks:
            logger.warning(f"Task {task_id} does not exist")
            return False

        task = self.tasks[task_id]
        old_status = task.status

        # 重置任务状态
        task.status = TaskStatus.PENDING
        task.result = None
        task.error = None
        task.start_time = None
        task.end_time = None
        task.retry_count = 0

        # 记录修改
        mod = DAGModification(
            action=ModificationAction.ROLLBACK_TASK,
            timestamp=datetime.now(),
            task_id=task_id,
            details={"old_status": old_status.value},
            reason=reason
        )
        self.modifications.append(mod)

        logger.info(f"Rolled back task {task_id} from {old_status} to PENDING")
        return True

    def remove_all_dependencies(self, reason: Optional[str] = None):
        """
        移除所有依赖关系

        用于打破死锁
        """
        for task in self.tasks.values():
            if task.dependencies:
                old_deps = task.dependencies.copy()
                task.dependencies.clear()

                mod = DAGModification(
                    action=ModificationAction.REMOVE_DEPENDENCY,
                    timestamp=datetime.now(),
                    task_id=task.task_id,
                    details={"removed_dependencies": old_deps},
                    reason=reason or "Break deadlock"
                )
                self.modifications.append(mod)

        logger.warning("Removed all dependencies to break deadlock")

    def _would_create_cycle(
        self,
        task_id: str,
        new_dependencies: List[str]
    ) -> bool:
        """
        检查添加依赖是否会引入循环

        Args:
            task_id: 任务 ID
            new_dependencies: 新的依赖列表

        Returns:
            是否会引入循环
        """
        # 临时添加依赖
        temp_deps = self.tasks.get(task_id)
        if temp_deps:
            original_deps = temp_deps.dependencies.copy()
            temp_deps.dependencies = new_dependencies
        else:
            # 新任务，临时创建
            temp_task = Task(
                task_id=task_id,
                task_type="temp",
                description="temp",
                dependencies=new_dependencies
            )
            self.tasks[task_id] = temp_task
            original_deps = None

        # 检测循环
        has_cycle = False
        visited = set()
        rec_stack = set()

        def dfs(tid: str) -> bool:
            visited.add(tid)
            rec_stack.add(tid)

            task = self.tasks.get(tid)
            if task:
                for dep_id in task.dependencies:
                    if dep_id not in visited:
                        if dfs(dep_id):
                            return True
                    elif dep_id in rec_stack:
                        return True

            rec_stack.remove(tid)
            return False

        for tid in self.tasks:
            if tid not in visited:
                if dfs(tid):
                    has_cycle = True
                    break

        # 恢复原状态
        if temp_deps:
            if original_deps is not None:
                temp_deps.dependencies = original_deps
            else:
                del self.tasks[task_id]

        return has_cycle

    def get_modification_history(self) -> List[DAGModification]:
        """获取所有修改历史"""
        return self.modifications.copy()

    def get_modification_summary(self) -> Dict[str, Any]:
        """获取修改摘要"""
        summary = {
            "total_modifications": len(self.modifications),
            "by_action": {},
            "recent_modifications": []
        }

        # 按动作分类
        for mod in self.modifications:
            action = mod.action.value
            summary["by_action"][action] = summary["by_action"].get(action, 0) + 1

        # 最近 5 次修改
        summary["recent_modifications"] = [
            {
                "action": mod.action.value,
                "task_id": mod.task_id,
                "timestamp": mod.timestamp.isoformat(),
                "reason": mod.reason
            }
            for mod in self.modifications[-5:]
        ]

        return summary


class DAGExecutor:
    """
    DAG 执行器 - 支持动态调整

    在执行过程中支持暂停、修改、继续
    """

    def __init__(
        self,
        dag: DynamicDAG,
        executor_func: Callable[[Task], Any]
    ):
        """
        Args:
            dag: 动态 DAG
            executor_func: 执行函数，接收 Task，返回结果
        """
        self.dag = dag
        self.executor_func = executor_func
        self.is_paused = False
        self.pause_event = asyncio.Event()
        self.pause_event.set()  # 初始不暂停

    async def execute(self) -> Dict[str, Any]:
        """
        执行 DAG

        Returns:
            执行结果统计
        """
        self.dag.is_executing = True
        start_time = datetime.now()

        try:
            while not self.dag.is_complete():
                # 检查暂停
                await self.pause_event.wait()

                # 获取可执行任务
                ready_tasks = self.dag.get_ready_tasks()

                if not ready_tasks:
                    # 没有可执行任务，检查是否死锁
                    if self.dag.get_statistics()["pending"] > 0:
                        logger.error("Deadlock detected: no ready tasks but pending tasks exist")
                        break
                    else:
                        # 全部完成
                        break

                # 并行执行
                await asyncio.gather(
                    *[self._execute_task(task) for task in ready_tasks],
                    return_exceptions=True
                )

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            stats = self.dag.get_statistics()
            stats["execution_time"] = execution_time
            stats["modifications"] = self.dag.get_modification_summary()

            return stats

        finally:
            self.dag.is_executing = False

    async def _execute_task(self, task: Task):
        """执行单个任务"""
        task.status = TaskStatus.RUNNING
        task.start_time = datetime.now()

        try:
            result = await asyncio.to_thread(self.executor_func, task)
            task.result = result
            task.status = TaskStatus.COMPLETED
            logger.info(f"Task {task.task_id} completed")
        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED
            logger.error(f"Task {task.task_id} failed: {e}")
        finally:
            task.end_time = datetime.now()

    def pause(self):
        """暂停执行"""
        self.is_paused = True
        self.pause_event.clear()
        logger.info("DAG execution paused")

    def resume(self):
        """恢复执行"""
        self.is_paused = False
        self.pause_event.set()
        logger.info("DAG execution resumed")

    def is_executing(self) -> bool:
        """是否正在执行"""
        return self.dag.is_executing
