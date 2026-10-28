"""Workflow Engine for Agent Orchestration"""
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Orchestrates agent workflows"""

    def __init__(self, router, message_queue, vector_store):
        self.router = router
        self.message_queue = message_queue
        self.vector_store = vector_store
        self.logger = logging.getLogger("WorkflowEngine")

    async def execute_workflow(self, workflow: Dict) -> Dict:
        """Execute a multi-step workflow"""
        self.logger.info(f"Executing workflow: {workflow.get('workflow_id')}")

        results = []
        for step in workflow.get('steps', []):
            result = await self._execute_step(step)
            results.append(result)

        return {
            "workflow_id": workflow.get('workflow_id'),
            "results": results,
            "status": "completed"
        }

    async def _execute_step(self, step: Dict) -> Dict:
        """Execute a single workflow step"""
        self.logger.debug(f"Executing step: {step.get('step_id')}")

        # Use router to execute step
        response = await self.router.route_request(
            prompt=step.get('prompt'),
            agent_id=step.get('agent_id', 'workflow'),
            enable_rag=step.get('enable_rag', False)
        )

        return {
            "step_id": step.get('step_id'),
            "result": response
        }
