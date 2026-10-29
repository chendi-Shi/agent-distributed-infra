"""
Multi-Agent System Implementation
Coordinates multiple agents for task execution
"""
import asyncio
import logging
from typing import List, Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Agent roles in the system"""
    PLANNER = "planner"
    WORKER = "worker"
    REVIEWER = "reviewer"
    COORDINATOR = "coordinator"


class Agent:
    """Base agent class"""

    def __init__(self, agent_id: str, role: AgentRole, workflow_engine):
        self.agent_id = agent_id
        self.role = role
        self.workflow_engine = workflow_engine
        self.status = "idle"
        self.logger = logging.getLogger(f"Agent-{agent_id}")

    async def process_task(self, task: Dict) -> Dict:
        """Process a task based on agent role"""
        self.status = "busy"
        self.logger.info(f"Processing task: {task.get('task_id')}")

        try:
            if self.role == AgentRole.PLANNER:
                result = await self._plan_task(task)
            elif self.role == AgentRole.WORKER:
                result = await self._execute_task(task)
            elif self.role == AgentRole.REVIEWER:
                result = await self._review_task(task)
            else:
                result = await self._coordinate_task(task)

            self.status = "idle"
            return result

        except Exception as e:
            self.logger.error(f"Task failed: {e}")
            self.status = "error"
            raise

    async def _plan_task(self, task: Dict) -> Dict:
        """Plan how to execute a complex task"""
        # Use LLM to decompose task into subtasks
        prompt = f"Decompose the following task into subtasks:\n{task['description']}"

        response = await self.workflow_engine.router.route_request(
            prompt=prompt,
            agent_id=self.agent_id
        )

        return {
            "task_id": task["task_id"],
            "subtasks": self._parse_subtasks(response),
            "agent_id": self.agent_id
        }

    async def _execute_task(self, task: Dict) -> Dict:
        """Execute a specific task"""
        # Implement task execution logic
        prompt = f"Execute the following task:\n{task['description']}"

        response = await self.workflow_engine.router.route_request(
            prompt=prompt,
            agent_id=self.agent_id,
            enable_rag=task.get('enable_rag', False)
        )

        return {
            "task_id": task["task_id"],
            "result": response,
            "agent_id": self.agent_id
        }

    async def _review_task(self, task: Dict) -> Dict:
        """Review task results"""
        prompt = f"Review the following result:\n{task['result']}"

        response = await self.workflow_engine.router.route_request(
            prompt=prompt,
            agent_id=self.agent_id
        )

        return {
            "task_id": task["task_id"],
            "review": response,
            "approved": "approved" in response.lower(),
            "agent_id": self.agent_id
        }

    async def _coordinate_task(self, task: Dict) -> Dict:
        """Coordinate multiple agents"""
        # Implement coordination logic
        return {
            "task_id": task["task_id"],
            "status": "coordinated",
            "agent_id": self.agent_id
        }

    def _parse_subtasks(self, response: str) -> List[Dict]:
        """Parse LLM response into subtasks"""
        # Simple parsing logic - can be improved
        lines = response.strip().split('\n')
        subtasks = []

        for i, line in enumerate(lines):
            if line.strip() and not line.startswith('#'):
                subtasks.append({
                    "subtask_id": f"sub-{i}",
                    "description": line.strip(),
                    "status": "pending"
                })

        return subtasks


class MultiAgentSystem:
    """Multi-agent system coordinator"""

    def __init__(self, workflow_engine, max_agents: int = 10):
        self.workflow_engine = workflow_engine
        self.max_agents = max_agents
        self.agents: Dict[str, Agent] = {}
        self.task_queue = asyncio.Queue()
        self.logger = logging.getLogger("MultiAgentSystem")

    async def run(self):
        """Start the multi-agent system"""
        self.logger.info("Multi-agent system started")

        # Create initial agents
        await self._create_agents()

        # Start task processing loop
        await self._process_tasks()

    async def _create_agents(self):
        """Create initial set of agents"""
        # Create one coordinator
        coordinator = Agent("coordinator-1", AgentRole.COORDINATOR, self.workflow_engine)
        self.agents[coordinator.agent_id] = coordinator

        # Create planner
        planner = Agent("planner-1", AgentRole.PLANNER, self.workflow_engine)
        self.agents[planner.agent_id] = planner

        # Create workers
        for i in range(3):
            worker = Agent(f"worker-{i+1}", AgentRole.WORKER, self.workflow_engine)
            self.agents[worker.agent_id] = worker

        # Create reviewer
        reviewer = Agent("reviewer-1", AgentRole.REVIEWER, self.workflow_engine)
        self.agents[reviewer.agent_id] = reviewer

        self.logger.info(f"Created {len(self.agents)} agents")

    async def _process_tasks(self):
        """Process tasks from the queue"""
        while True:
            try:
                # Wait for task
                task = await self.task_queue.get()

                # Find available agent
                agent = await self._find_available_agent(task)

                if agent:
                    # Process task
                    result = await agent.process_task(task)
                    self.logger.info(f"Task {task['task_id']} completed by {agent.agent_id}")
                else:
                    # Re-queue task
                    await self.task_queue.put(task)
                    await asyncio.sleep(1)

            except Exception as e:
                self.logger.error(f"Error processing task: {e}")

    async def _find_available_agent(self, task: Dict) -> Optional[Agent]:
        """Find an available agent for the task"""
        required_role = task.get('required_role', AgentRole.WORKER)

        for agent in self.agents.values():
            if agent.role == required_role and agent.status == "idle":
                return agent

        return None

    async def submit_task(self, task: Dict):
        """Submit a task to the system"""
        await self.task_queue.put(task)
        self.logger.info(f"Task {task['task_id']} submitted")

    async def shutdown(self):
        """Shutdown the system gracefully"""
        self.logger.info("Shutting down multi-agent system...")
        # Implement cleanup logic


class MultiAgentOrchestrator:
    """
    Orchestrator for multi-agent collaboration with parallelism
    Used in comparison experiments
    """

    def __init__(self, router=None):
        from infra.inference.router import ModelRouter
        self.router = router or ModelRouter(primary_model="deepseek-chat")
        self.logger = logging.getLogger("MultiAgentOrchestrator")
        self.total_tokens = 0
        self.api_calls = 0

    async def execute_task(self, task_description: str, parameters: Dict) -> str:
        """
        Execute task with multi-agent collaboration and parallelism

        Args:
            task_description: Task to execute
            parameters: Task parameters

        Returns:
            Final result
        """
        self.logger.info(f"Executing task: {task_description[:50]}...")

        # Step 1: Planner decomposes task into subtasks
        plan_prompt = f"""You are a Planner. Decompose this task into 2-3 parallel subtasks:

Task: {task_description}
Parameters: {parameters}

Output format:
SUBTASK 1: [description]
SUBTASK 2: [description]
SUBTASK 3: [description] (if needed)"""

        api_calls_before = self.router.stats['total_requests']

        plan = await self.router.route_request(
            prompt=plan_prompt,
            agent_id="planner-orchestrator"
        )

        self.total_tokens += len(plan_prompt.split()) * 1.3 + len(plan.split()) * 1.3

        # Parse subtasks
        subtasks = self._parse_subtasks(plan)
        self.logger.debug(f"Decomposed into {len(subtasks)} subtasks")

        # Step 2: Execute subtasks in parallel
        worker_tasks = []
        for i, subtask in enumerate(subtasks):
            worker_tasks.append(
                self._execute_subtask(f"worker-{i+1}", subtask)
            )

        # Run all subtasks concurrently
        subtask_results = await asyncio.gather(*worker_tasks, return_exceptions=True)

        # Handle exceptions
        for i, result in enumerate(subtask_results):
            if isinstance(result, Exception):
                self.logger.error(f"Subtask {i} failed: {result}")
                subtask_results[i] = f"[Failed: {result}]"

        # Step 3: Reviewer aggregates results
        review_prompt = f"""You are a Reviewer. Aggregate these parallel subtask results into final result:

Original Task: {task_description}

Subtask Results:
{chr(10).join(f'{i+1}. {r}' for i, r in enumerate(subtask_results))}

Provide the final consolidated result."""

        final_result = await self.router.route_request(
            prompt=review_prompt,
            agent_id="reviewer-orchestrator"
        )

        self.total_tokens += len(review_prompt.split()) * 1.3 + len(final_result.split()) * 1.3
        self.api_calls = self.router.stats['total_requests'] - api_calls_before

        self.logger.info(f"Task completed with {len(subtasks)} parallel subtasks")

        return final_result

    async def _execute_subtask(self, worker_id: str, subtask: str) -> str:
        """Execute a single subtask"""
        prompt = f"""You are a Worker. Execute this subtask:

{subtask}

Provide the result."""

        result = await self.router.route_request(
            prompt=prompt,
            agent_id=worker_id
        )

        self.total_tokens += len(prompt.split()) * 1.3 + len(result.split()) * 1.3

        return result

    def _parse_subtasks(self, plan: str) -> List[str]:
        """Parse plan into subtasks"""
        lines = plan.strip().split('\n')
        subtasks = []

        for line in lines:
            line = line.strip()
            # Match "SUBTASK N:" or numbered items
            if line.startswith('SUBTASK') or (len(line) > 2 and line[0].isdigit() and line[1] in '.):'):
                # Extract description after colon or number
                if ':' in line:
                    desc = line.split(':', 1)[1].strip()
                else:
                    desc = line[2:].strip()

                if desc:
                    subtasks.append(desc)

        # Fallback: if no subtasks parsed, treat whole plan as one subtask
        if not subtasks:
            subtasks = [plan]

        return subtasks

    def get_token_usage(self) -> int:
        """Get total token usage"""
        return int(self.total_tokens)
