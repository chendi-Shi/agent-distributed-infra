"""
Unit tests for Task DAG (Directed Acyclic Graph)
Tests task dependencies, validation, and topological sorting
"""
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from orchestration.task_dag import (
    Task,
    TaskStatus,
    TaskDAG,
    WorkflowBuilder
)


class TestTask:
    """Test Task model"""

    def test_create_task(self):
        """Test creating a task"""
        task = Task(
            task_id="task-1",
            task_type="analysis",
            description="Analyze data",
            parameters={"depth": "detailed"}
        )

        assert task.task_id == "task-1"
        assert task.status == TaskStatus.PENDING
        assert task.result is None
        assert task.max_retries == 3

    def test_task_with_dependencies(self):
        """Test task with dependencies"""
        task = Task(
            task_id="task-2",
            task_type="review",
            description="Review results",
            dependencies=["task-1"]
        )

        assert "task-1" in task.dependencies

    def test_task_is_terminal(self):
        """Test terminal status checking"""
        task = Task(task_id="t1", task_type="work", description="Do work")

        assert not task.is_terminal  # PENDING

        task.status = TaskStatus.RUNNING
        assert not task.is_terminal

        task.status = TaskStatus.COMPLETED
        assert task.is_terminal

        task.status = TaskStatus.FAILED
        assert task.is_terminal

    def test_task_can_retry(self):
        """Test retry logic"""
        task = Task(task_id="t1", task_type="work", description="Work", max_retries=2)

        assert not task.can_retry  # Not failed yet

        task.status = TaskStatus.FAILED
        task.retry_count = 0
        assert task.can_retry

        task.retry_count = 1
        assert task.can_retry

        task.retry_count = 2
        assert not task.can_retry  # Max retries reached


class TestTaskDAG:
    """Test TaskDAG operations"""

    def test_create_empty_dag(self):
        """Test creating empty DAG"""
        dag = TaskDAG()
        assert len(dag.tasks) == 0

    def test_add_task(self):
        """Test adding tasks to DAG"""
        dag = TaskDAG()

        task1 = Task(task_id="t1", task_type="work", description="Work 1")
        dag.add_task(task1)

        assert len(dag.tasks) == 1
        assert "t1" in dag.tasks

    def test_add_duplicate_task_fails(self):
        """Test that adding duplicate task raises error"""
        dag = TaskDAG()

        task1 = Task(task_id="t1", task_type="work", description="Work")
        dag.add_task(task1)

        task2 = Task(task_id="t1", task_type="work", description="Duplicate")

        with pytest.raises(ValueError, match="already exists"):
            dag.add_task(task2)

    def test_get_task(self):
        """Test getting task by ID"""
        dag = TaskDAG()
        task = Task(task_id="t1", task_type="work", description="Work")
        dag.add_task(task)

        retrieved = dag.get_task("t1")
        assert retrieved is not None
        assert retrieved.task_id == "t1"

        missing = dag.get_task("nonexistent")
        assert missing is None

    def test_validate_missing_dependency(self):
        """Test validation catches missing dependencies"""
        dag = TaskDAG()

        task = Task(
            task_id="t2",
            task_type="work",
            description="Work",
            dependencies=["t1"]  # t1 doesn't exist
        )
        dag.add_task(task)

        with pytest.raises(ValueError, match="non-existent"):
            dag.validate()

    def test_validate_cycle_detection(self):
        """Test cycle detection"""
        dag = TaskDAG()

        # Create a cycle: t1 -> t2 -> t1
        task1 = Task(
            task_id="t1",
            task_type="work",
            description="Work 1",
            dependencies=["t2"]
        )
        task2 = Task(
            task_id="t2",
            task_type="work",
            description="Work 2",
            dependencies=["t1"]
        )

        dag.add_task(task1)
        dag.add_task(task2)

        with pytest.raises(ValueError, match="Cycle detected"):
            dag.validate()

    def test_validate_valid_dag(self):
        """Test validation passes for valid DAG"""
        dag = TaskDAG()

        task1 = Task(task_id="t1", task_type="work", description="Work 1")
        task2 = Task(
            task_id="t2",
            task_type="work",
            description="Work 2",
            dependencies=["t1"]
        )

        dag.add_task(task1)
        dag.add_task(task2)

        assert dag.validate()

    def test_get_ready_tasks(self):
        """Test getting tasks ready to execute"""
        dag = TaskDAG()

        task1 = Task(task_id="t1", task_type="work", description="Work 1")
        task2 = Task(
            task_id="t2",
            task_type="work",
            description="Work 2",
            dependencies=["t1"]
        )

        dag.add_task(task1)
        dag.add_task(task2)

        # Initially, only t1 is ready
        ready = dag.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "t1"

        # Complete t1, now t2 is ready
        task1.status = TaskStatus.COMPLETED
        ready = dag.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "t2"

    def test_get_statistics(self):
        """Test getting DAG statistics"""
        dag = TaskDAG()

        task1 = Task(task_id="t1", task_type="work", description="Work 1")
        task2 = Task(task_id="t2", task_type="work", description="Work 2")
        task3 = Task(task_id="t3", task_type="work", description="Work 3")

        dag.add_task(task1)
        dag.add_task(task2)
        dag.add_task(task3)

        task1.status = TaskStatus.COMPLETED
        task2.status = TaskStatus.RUNNING
        # task3 is PENDING

        stats = dag.get_statistics()
        assert stats["total"] == 3
        assert stats["completed"] == 1
        assert stats["running"] == 1
        assert stats["pending"] == 1
        assert stats["failed"] == 0

    def test_is_complete(self):
        """Test checking if DAG is complete"""
        dag = TaskDAG()

        task1 = Task(task_id="t1", task_type="work", description="Work 1")
        task2 = Task(task_id="t2", task_type="work", description="Work 2")

        dag.add_task(task1)
        dag.add_task(task2)

        assert not dag.is_complete()

        task1.status = TaskStatus.COMPLETED
        assert not dag.is_complete()

        task2.status = TaskStatus.COMPLETED
        assert dag.is_complete()

    def test_topological_sort(self):
        """Test topological sorting"""
        dag = TaskDAG()

        # Create linear chain: t1 -> t2 -> t3
        task1 = Task(task_id="t1", task_type="work", description="Work 1")
        task2 = Task(
            task_id="t2",
            task_type="work",
            description="Work 2",
            dependencies=["t1"]
        )
        task3 = Task(
            task_id="t3",
            task_type="work",
            description="Work 3",
            dependencies=["t2"]
        )

        dag.add_task(task3)  # Add in random order
        dag.add_task(task1)
        dag.add_task(task2)

        sorted_tasks = dag.topological_sort()

        assert len(sorted_tasks) == 3
        assert sorted_tasks[0].task_id == "t1"
        assert sorted_tasks[1].task_id == "t2"
        assert sorted_tasks[2].task_id == "t3"


class TestWorkflowBuilder:
    """Test WorkflowBuilder"""

    def test_build_simple_workflow(self):
        """Test building a simple workflow"""
        builder = WorkflowBuilder()

        builder.add_task(
            task_id="t1",
            task_type="analysis",
            description="Analyze data"
        ).add_task(
            task_id="t2",
            task_type="review",
            description="Review results",
            dependencies=["t1"]
        )

        dag = builder.build()

        assert len(dag.tasks) == 2
        assert "t1" in dag.tasks
        assert "t2" in dag.tasks

    def test_build_with_parameters(self):
        """Test building workflow with parameters"""
        builder = WorkflowBuilder()

        builder.add_task(
            task_id="t1",
            task_type="work",
            description="Work",
            parameters={"param1": "value1"},
            max_retries=5,
            required_role="worker"
        )

        dag = builder.build()
        task = dag.get_task("t1")

        assert task.parameters == {"param1": "value1"}
        assert task.max_retries == 5
        assert task.required_role == "worker"

    def test_build_validates_dag(self):
        """Test that build validates the DAG"""
        builder = WorkflowBuilder()

        # Create invalid DAG (missing dependency)
        builder.add_task(
            task_id="t2",
            task_type="work",
            description="Work",
            dependencies=["t1"]  # t1 doesn't exist
        )

        with pytest.raises(ValueError):
            builder.build()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
