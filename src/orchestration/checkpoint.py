"""
Checkpoint 与回滚机制

功能：
1. 保存 DAG 执行快照
2. 回滚到指定 checkpoint
3. 增量恢复
"""

import pickle
import json
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import logging
import copy

from src.orchestration.dynamic_dag import DynamicDAG, Task

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """Checkpoint 快照"""
    checkpoint_id: str
    timestamp: datetime
    dag_state: Dict[str, Any]  # 序列化的 DAG 状态
    reason: Optional[str] = None
    metadata: Dict[str, Any] = None


class CheckpointManager:
    """
    Checkpoint 管理器

    功能：
    1. 自动或手动创建 checkpoint
    2. 恢复到历史 checkpoint
    3. 增量差异对比
    """

    def __init__(
        self,
        checkpoint_dir: Optional[Path] = None,
        auto_checkpoint_interval: int = 5  # 每执行 N 个任务自动保存
    ):
        self.checkpoint_dir = checkpoint_dir or Path("./checkpoints")
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self.auto_checkpoint_interval = auto_checkpoint_interval
        self.checkpoints: List[Checkpoint] = []

        # 加载已有 checkpoints
        self._load_checkpoints()

        logger.info(f"CheckpointManager initialized at {self.checkpoint_dir}")

    def create_checkpoint(
        self,
        dag: DynamicDAG,
        reason: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        创建 checkpoint

        Args:
            dag: 当前 DAG
            reason: 创建理由
            metadata: 额外元数据

        Returns:
            checkpoint_id
        """
        checkpoint_id = f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        # 序列化 DAG 状态
        dag_state = self._serialize_dag(dag)

        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            timestamp=datetime.now(),
            dag_state=dag_state,
            reason=reason,
            metadata=metadata or {}
        )

        # 保存到内存
        self.checkpoints.append(checkpoint)

        # 持久化到磁盘
        self._save_checkpoint(checkpoint)

        logger.info(f"Created checkpoint {checkpoint_id}: {reason}")
        return checkpoint_id

    def restore_checkpoint(
        self,
        checkpoint_id: str,
        dag: DynamicDAG
    ) -> bool:
        """
        恢复到指定 checkpoint

        Args:
            checkpoint_id: checkpoint ID
            dag: 要恢复的 DAG（会被修改）

        Returns:
            是否恢复成功
        """
        checkpoint = self._find_checkpoint(checkpoint_id)
        if not checkpoint:
            logger.error(f"Checkpoint {checkpoint_id} not found")
            return False

        try:
            # 恢复 DAG 状态
            self._deserialize_dag(checkpoint.dag_state, dag)

            logger.info(f"Restored checkpoint {checkpoint_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore checkpoint {checkpoint_id}: {e}")
            return False

    def get_checkpoint_diff(
        self,
        checkpoint_id: str,
        current_dag: DynamicDAG
    ) -> Dict[str, Any]:
        """
        对比 checkpoint 与当前状态的差异

        Returns:
            {
                "added_tasks": [...],
                "removed_tasks": [...],
                "modified_tasks": [...],
                "status_changes": {...}
            }
        """
        checkpoint = self._find_checkpoint(checkpoint_id)
        if not checkpoint:
            return {}

        old_state = checkpoint.dag_state
        new_state = self._serialize_dag(current_dag)

        diff = {
            "added_tasks": [],
            "removed_tasks": [],
            "modified_tasks": [],
            "status_changes": {}
        }

        old_task_ids = set(old_state["tasks"].keys())
        new_task_ids = set(new_state["tasks"].keys())

        # 新增的任务
        diff["added_tasks"] = list(new_task_ids - old_task_ids)

        # 删除的任务
        diff["removed_tasks"] = list(old_task_ids - new_task_ids)

        # 修改的任务
        for task_id in old_task_ids & new_task_ids:
            old_task = old_state["tasks"][task_id]
            new_task = new_state["tasks"][task_id]

            if old_task != new_task:
                diff["modified_tasks"].append(task_id)

                # 状态变化
                if old_task["status"] != new_task["status"]:
                    diff["status_changes"][task_id] = {
                        "from": old_task["status"],
                        "to": new_task["status"]
                    }

        return diff

    def list_checkpoints(self) -> List[Dict]:
        """列出所有 checkpoints"""
        return [
            {
                "checkpoint_id": cp.checkpoint_id,
                "timestamp": cp.timestamp.isoformat(),
                "reason": cp.reason,
                "num_tasks": len(cp.dag_state["tasks"])
            }
            for cp in self.checkpoints
        ]

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """删除 checkpoint"""
        checkpoint = self._find_checkpoint(checkpoint_id)
        if not checkpoint:
            return False

        # 从内存删除
        self.checkpoints = [
            cp for cp in self.checkpoints
            if cp.checkpoint_id != checkpoint_id
        ]

        # 从磁盘删除
        checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()

        logger.info(f"Deleted checkpoint {checkpoint_id}")
        return True

    def _serialize_dag(self, dag: DynamicDAG) -> Dict[str, Any]:
        """序列化 DAG"""
        tasks_dict = {}

        for task_id, task in dag.tasks.items():
            tasks_dict[task_id] = {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "description": task.description,
                "parameters": task.parameters,
                "dependencies": task.dependencies.copy(),
                "status": task.status.value,
                "result": str(task.result) if task.result else None,
                "error": task.error,
                "max_retries": task.max_retries,
                "retry_count": task.retry_count,
                "start_time": task.start_time.isoformat() if task.start_time else None,
                "end_time": task.end_time.isoformat() if task.end_time else None,
                "assigned_agent": task.assigned_agent,
                "required_role": task.required_role,
            }

        return {
            "tasks": tasks_dict,
            "modifications": [
                {
                    "action": mod.action.value,
                    "timestamp": mod.timestamp.isoformat(),
                    "task_id": mod.task_id,
                    "details": mod.details,
                    "reason": mod.reason
                }
                for mod in dag.modifications
            ]
        }

    def _deserialize_dag(self, dag_state: Dict[str, Any], dag: DynamicDAG):
        """反序列化到 DAG"""
        from src.orchestration.task_dag import TaskStatus

        # 清空现有任务
        dag.tasks.clear()

        # 恢复任务
        for task_id, task_data in dag_state["tasks"].items():
            task = Task(
                task_id=task_data["task_id"],
                task_type=task_data["task_type"],
                description=task_data["description"],
                parameters=task_data["parameters"],
                dependencies=task_data["dependencies"],
                status=TaskStatus(task_data["status"]),
                result=task_data["result"],
                error=task_data["error"],
                max_retries=task_data["max_retries"],
                retry_count=task_data["retry_count"],
            )

            if task_data["start_time"]:
                task.start_time = datetime.fromisoformat(task_data["start_time"])
            if task_data["end_time"]:
                task.end_time = datetime.fromisoformat(task_data["end_time"])

            task.assigned_agent = task_data["assigned_agent"]
            task.required_role = task_data["required_role"]

            dag.tasks[task_id] = task

    def _save_checkpoint(self, checkpoint: Checkpoint):
        """保存 checkpoint 到磁盘"""
        checkpoint_file = self.checkpoint_dir / f"{checkpoint.checkpoint_id}.json"

        data = {
            "checkpoint_id": checkpoint.checkpoint_id,
            "timestamp": checkpoint.timestamp.isoformat(),
            "dag_state": checkpoint.dag_state,
            "reason": checkpoint.reason,
            "metadata": checkpoint.metadata
        }

        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_checkpoints(self):
        """从磁盘加载 checkpoints"""
        if not self.checkpoint_dir.exists():
            return

        for checkpoint_file in self.checkpoint_dir.glob("checkpoint_*.json"):
            try:
                with open(checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                checkpoint = Checkpoint(
                    checkpoint_id=data["checkpoint_id"],
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    dag_state=data["dag_state"],
                    reason=data.get("reason"),
                    metadata=data.get("metadata")
                )

                self.checkpoints.append(checkpoint)
            except Exception as e:
                logger.warning(f"Failed to load checkpoint {checkpoint_file}: {e}")

        # 按时间排序
        self.checkpoints.sort(key=lambda cp: cp.timestamp)

        logger.info(f"Loaded {len(self.checkpoints)} checkpoints")

    def _find_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """查找 checkpoint"""
        for cp in self.checkpoints:
            if cp.checkpoint_id == checkpoint_id:
                return cp
        return None

    def auto_checkpoint(
        self,
        dag: DynamicDAG,
        completed_tasks: int
    ) -> Optional[str]:
        """
        自动创建 checkpoint

        Args:
            dag: 当前 DAG
            completed_tasks: 已完成任务数

        Returns:
            checkpoint_id 或 None
        """
        if completed_tasks % self.auto_checkpoint_interval == 0:
            return self.create_checkpoint(
                dag,
                reason=f"Auto checkpoint after {completed_tasks} tasks"
            )
        return None
