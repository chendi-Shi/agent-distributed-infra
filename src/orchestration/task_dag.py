"""
Task DAG (Directed Acyclic Graph) for Workflow Management
Supports task dependencies, parallel execution, and failure handling
"""
from typing import Dict, List, Set, Optional, Any
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    """Represents a single task in the workflow"""
    task_id: str
    task_type: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Dependencies
    dependencies: List[str] = field(default_factory=list)  # Task IDs this task depends on

    # Execution
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None

    # Retry configuration
    max_retries: int = 3
    retry_count: int = 0

    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Agent assignment
    assigned_agent: Optional[str] = None
    required_role: Optional[str] = None

    def __hash__(self):
        return hash(self.task_id)

    @property
    def execution_time(self) -> Optional[float]:
        """Get execution time in seconds"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    @property
    def is_terminal(self) -> bool:
        """Check if task is in terminal state"""
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED)

    @property
    def can_retry(self) -> bool:
        """Check if task can be retried"""
        return self.status == TaskStatus.FAILED and self.retry_count < self.max_retries


class TaskDAG:
    """Directed Acyclic Graph for managing task dependencies"""

    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.logger = logging.getLogger("TaskDAG")

    def add_task(self, task: Task):
        """Add a task to the DAG"""
        if task.task_id in self.tasks:
            raise ValueError(f"Task {task.task_id} already exists")

        self.tasks[task.task_id] = task
        self.logger.debug(f"Added task: {task.task_id}")

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        return self.tasks.get(task_id)

    def validate(self) -> bool:
        """Validate DAG structure (no cycles, all dependencies exist)"""
        # Check all dependencies exist
        for task in self.tasks.values():
            for dep_id in task.dependencies:
                if dep_id not in self.tasks:
                    raise ValueError(f"Task {task.task_id} depends on non-existent task {dep_id}")

        # Check for cycles using DFS
        visited = set()
        rec_stack = set()

        def has_cycle(task_id: str) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)

            task = self.tasks[task_id]
            for dep_id in task.dependencies:
                if dep_id not in visited:
                    if has_cycle(dep_id):
                        return True
                elif dep_id in rec_stack:
                    return True

            rec_stack.remove(task_id)
            return False

        for task_id in self.tasks:
            if task_id not in visited:
                if has_cycle(task_id):
                    raise ValueError(f"Cycle detected in DAG involving task {task_id}")

        self.logger.info(f"DAG validated: {len(self.tasks)} tasks, no cycles")
        return True

    def get_ready_tasks(self) -> List[Task]:
        """Get tasks that are ready to execute (all dependencies met)"""
        ready = []

        for task in self.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue

            # Check if all dependencies are completed
            deps_met = all(
                self.tasks[dep_id].status == TaskStatus.COMPLETED
                for dep_id in task.dependencies
            )

            if deps_met:
                ready.append(task)

        return ready

    def get_failed_tasks(self) -> List[Task]:
        """Get tasks that failed and can be retried"""
        return [task for task in self.tasks.values() if task.can_retry]

    def get_statistics(self) -> Dict[str, Any]:
        """Get DAG execution statistics"""
        stats = {
            "total": len(self.tasks),
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0
        }

        for task in self.tasks.values():
            stats[task.status.value] += 1

        return stats

    def is_complete(self) -> bool:
        """Check if all tasks are in terminal state"""
        return all(task.is_terminal for task in self.tasks.values())

    def topological_sort(self) -> List[Task]:
        """Get tasks in topological order"""
        in_degree = {task_id: 0 for task_id in self.tasks}

        # Calculate in-degrees
        for task in self.tasks.values():
            for dep_id in task.dependencies:
                in_degree[task.task_id] += 1

        # Queue for tasks with no dependencies
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        sorted_tasks = []

        while queue:
            task_id = queue.pop(0)
            sorted_tasks.append(self.tasks[task_id])

            # Find tasks that depend on this task
            for other_task in self.tasks.values():
                if task_id in other_task.dependencies:
                    in_degree[other_task.task_id] -= 1
                    if in_degree[other_task.task_id] == 0:
                        queue.append(other_task.task_id)

        return sorted_tasks


class WorkflowBuilder:
    """Builder for constructing workflows"""

    def __init__(self):
        self.dag = TaskDAG()

    def add_task(
        self,
        task_id: str,
        task_type: str,
        description: str,
        dependencies: Optional[List[str]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        required_role: Optional[str] = None
    ) -> 'WorkflowBuilder':
        """Add a task to the workflow"""
        task = Task(
            task_id=task_id,
            task_type=task_type,
            description=description,
            dependencies=dependencies or [],
            parameters=parameters or {},
            max_retries=max_retries,
            required_role=required_role
        )
        self.dag.add_task(task)
        return self

    def build(self) -> TaskDAG:
        """Build and validate the DAG"""
        self.dag.validate()
        return self.dag
