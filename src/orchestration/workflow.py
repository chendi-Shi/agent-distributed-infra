"""Workflow Engine for Agent Orchestration with DAG Support"""
import logging
import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

from .task_dag import TaskDAG, Task, TaskStatus, WorkflowBuilder

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Orchestrates agent workflows with DAG-based task management"""

    def __init__(self, router, message_queue, vector_store):
        self.router = router
        self.message_queue = message_queue
        self.vector_store = vector_store
        self.logger = logging.getLogger("WorkflowEngine")

        # Active workflows
        self.active_workflows: Dict[str, TaskDAG] = {}

        # Task executor registry
        self.task_executors: Dict[str, Callable] = {}

    def register_executor(self, task_type: str, executor: Callable):
        """Register a task executor for a specific task type"""
        self.task_executors[task_type] = executor
        self.logger.info(f"Registered executor for task type: {task_type}")

    async def execute_workflow(self, workflow_id: str, dag: TaskDAG) -> Dict[str, Any]:
        """Execute a workflow DAG with parallel task execution"""
        self.logger.info(f"Starting workflow: {workflow_id}")
        self.active_workflows[workflow_id] = dag

        start_time = datetime.utcnow()

        try:
            # Validate DAG
            dag.validate()

            # Execute tasks
            await self._execute_dag(workflow_id, dag)

            # Collect results
            results = self._collect_results(dag)

            end_time = datetime.utcnow()
            execution_time = (end_time - start_time).total_seconds()

            stats = dag.get_statistics()

            return {
                "workflow_id": workflow_id,
                "status": "completed" if stats["failed"] == 0 else "partial",
                "execution_time": execution_time,
                "statistics": stats,
                "results": results
            }

        except Exception as e:
            self.logger.error(f"Workflow {workflow_id} failed: {e}")
            return {
                "workflow_id": workflow_id,
                "status": "failed",
                "error": str(e),
                "statistics": dag.get_statistics()
            }
        finally:
            # Cleanup
            if workflow_id in self.active_workflows:
                del self.active_workflows[workflow_id]

    async def _execute_dag(self, workflow_id: str, dag: TaskDAG):
        """Execute DAG with parallel task execution"""
        while not dag.is_complete():
            # Get ready tasks
            ready_tasks = dag.get_ready_tasks()

            if not ready_tasks:
                # Check for failed tasks that can be retried
                failed_tasks = dag.get_failed_tasks()
                if failed_tasks:
                    self.logger.info(f"Retrying {len(failed_tasks)} failed tasks")
                    for task in failed_tasks:
                        task.status = TaskStatus.PENDING
                        task.retry_count += 1
                    continue
                else:
                    # No tasks ready and no retries available
                    self.logger.warning("No tasks ready to execute, but DAG not complete")
                    break

            # Execute ready tasks in parallel
            self.logger.info(f"Executing {len(ready_tasks)} tasks in parallel")

            tasks_coroutines = [
                self._execute_task(workflow_id, task)
                for task in ready_tasks
            ]

            await asyncio.gather(*tasks_coroutines, return_exceptions=True)

            # Small delay to avoid busy loop
            await asyncio.sleep(0.1)

    async def _execute_task(self, workflow_id: str, task: Task):
        """Execute a single task"""
        task.status = TaskStatus.RUNNING
        task.start_time = datetime.utcnow()

        self.logger.info(f"Executing task: {task.task_id} (type={task.task_type})")

        try:
            # Get executor for task type
            executor = self.task_executors.get(task.task_type)

            if executor:
                # Use registered executor
                result = await executor(task, self.router, self.message_queue)
            else:
                # Default executor: use router
                result = await self._default_executor(task)

            task.result = result
            task.status = TaskStatus.COMPLETED
            task.end_time = datetime.utcnow()

            self.logger.info(
                f"Task {task.task_id} completed in {task.execution_time:.2f}s"
            )

        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED
            task.end_time = datetime.utcnow()

            self.logger.error(
                f"Task {task.task_id} failed (retry {task.retry_count}/{task.max_retries}): {e}"
            )

    async def _default_executor(self, task: Task) -> Any:
        """Default task executor using router"""
        response = await self.router.route_request(
            prompt=task.description,
            agent_id=task.task_id,
            enable_rag=task.parameters.get('enable_rag', False)
        )
        return response

    def _collect_results(self, dag: TaskDAG) -> Dict[str, Any]:
        """Collect results from all tasks"""
        results = {}

        for task_id, task in dag.tasks.items():
            results[task_id] = {
                "status": task.status.value,
                "result": task.result,
                "error": task.error,
                "execution_time": task.execution_time,
                "retry_count": task.retry_count
            }

        return results

    def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get status of an active workflow"""
        dag = self.active_workflows.get(workflow_id)
        if not dag:
            return None

        return {
            "workflow_id": workflow_id,
            "statistics": dag.get_statistics(),
            "is_complete": dag.is_complete()
        }


# Example task executors

async def analysis_executor(task: Task, router, message_queue) -> str:
    """Executor for analysis tasks"""
    prompt = f"Analyze the following: {task.description}\nParameters: {task.parameters}"
    response = await router.route_request(prompt=prompt, agent_id=task.task_id)
    return response


async def planning_executor(task: Task, router, message_queue) -> str:
    """Executor for planning tasks"""
    prompt = f"Create a plan for: {task.description}\nParameters: {task.parameters}"
    response = await router.route_request(prompt=prompt, agent_id=task.task_id)
    return response


async def review_executor(task: Task, router, message_queue) -> str:
    """Executor for review tasks"""
    # Get results from dependencies
    dep_results = task.parameters.get('dependency_results', [])

    prompt = f"Review the following results and provide feedback:\n"
    prompt += f"Task: {task.description}\n"
    prompt += f"Results to review: {dep_results}"

    response = await router.route_request(prompt=prompt, agent_id=task.task_id)
    return response
