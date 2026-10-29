"""
Agent Worker with RabbitMQ Integration
Agents that consume tasks from message queue and execute them
"""
import asyncio
import logging
from typing import Dict, Optional, Callable
from datetime import datetime
import time

from infra.communication.message_protocol import (
    AgentMessage, MessageBuilder, MessageType, MessagePriority
)
from infra.communication.message_queue import MessageQueue
from agents.multi_agent import AgentRole
from monitoring.metrics import get_metrics_collector


logger = logging.getLogger(__name__)


class AgentWorker:
    """Agent that processes tasks from RabbitMQ"""

    def __init__(
        self,
        agent_id: str,
        role: AgentRole,
        workflow_engine,
        message_queue: MessageQueue,
        queue_name: str = "agent_tasks"
    ):
        self.agent_id = agent_id
        self.role = role
        self.workflow_engine = workflow_engine
        self.message_queue = message_queue
        self.queue_name = queue_name

        self.status = "idle"
        self.current_task = None
        self.tasks_processed = 0
        self.tasks_failed = 0

        self.logger = logging.getLogger(f"AgentWorker-{agent_id}")
        self.running = False

        # Initialize metrics
        self.metrics = get_metrics_collector()

    async def start(self):
        """Start the agent worker loop"""
        self.running = True
        self.logger.info(f"Agent {self.agent_id} ({self.role.value}) starting...")

        # Connect to message queue
        self.message_queue.connect()

        if not self.message_queue.is_connected():
            self.logger.error("Failed to connect to message queue")
            return

        # Publish status
        await self._publish_status("idle")

        # Start consuming tasks
        await self._consume_tasks()

    async def stop(self):
        """Stop the agent worker"""
        self.running = False
        self.logger.info(f"Agent {self.agent_id} stopping...")
        await self._publish_status("offline")

    async def _consume_tasks(self):
        """Consume and process tasks from message queue"""
        def callback(message_str: str, delivery_tag: int) -> bool:
            """Callback for processing messages"""
            try:
                # Parse message
                msg = AgentMessage.from_json(message_str)

                # Check if this message is for us
                if msg.message_type != MessageType.TASK_REQUEST:
                    self.logger.debug(f"Ignoring non-task message: {msg.message_type}")
                    return True  # ACK anyway

                # Check role requirement
                task_payload = msg.payload
                required_role = task_payload.get('required_role')
                if required_role and required_role != self.role.value:
                    self.logger.debug(f"Task requires {required_role}, skipping")
                    return True  # ACK and let another agent handle it

                # Process task synchronously
                success = asyncio.run(self._process_task_message(msg))

                return success

            except Exception as e:
                self.logger.error(f"Error in callback: {e}")
                return False  # NACK and requeue

        try:
            # Start consuming
            self.message_queue.consume(
                self.queue_name,
                callback,
                prefetch_count=1  # Process one task at a time
            )
        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        except Exception as e:
            self.logger.error(f"Error consuming tasks: {e}")

    async def _process_task_message(self, msg: AgentMessage) -> bool:
        """Process a task message"""
        task_id = msg.payload['task_id']
        self.current_task = task_id
        self.status = "busy"

        start_time = time.time()

        # Update active tasks metric
        self.metrics.set_agent_active_tasks(self.agent_id, self.role.value, 1)

        try:
            self.logger.info(f"Processing task: {task_id}")

            # Extract task details
            task_type = msg.payload['task_type']
            description = msg.payload['description']
            parameters = msg.payload.get('parameters', {})

            # Execute task based on role
            result = await self._execute_by_role(
                task_type, description, parameters
            )

            execution_time = time.time() - start_time

            # Record metrics for successful task
            self.metrics.record_agent_task(self.agent_id, self.role.value, "success")
            self.metrics.record_agent_task_duration(
                self.agent_id, self.role.value, task_type, execution_time
            )

            # Send response
            await self._send_task_response(
                msg,
                status="success",
                result=result,
                execution_time=execution_time
            )

            self.tasks_processed += 1
            self.status = "idle"
            self.current_task = None

            self.logger.info(
                f"Task {task_id} completed in {execution_time:.2f}s"
            )

            return True

        except Exception as e:
            execution_time = time.time() - start_time

            self.logger.error(f"Task {task_id} failed: {e}")

            # Record metrics for failed task
            self.metrics.record_agent_task(self.agent_id, self.role.value, "failed")
            self.metrics.record_error("agent_worker", type(e).__name__)

            # Send error response
            await self._send_task_response(
                msg,
                status="failed",
                result=None,
                execution_time=execution_time,
                error=str(e)
            )

            self.tasks_failed += 1
            self.status = "idle"
            self.current_task = None

            return False

    async def _execute_by_role(
        self, task_type: str, description: str, parameters: Dict
    ) -> str:
        """Execute task based on agent role"""
        if self.role == AgentRole.PLANNER:
            prompt = f"Plan how to accomplish this task:\n{description}\nParameters: {parameters}"
        elif self.role == AgentRole.WORKER:
            prompt = f"Execute this task:\n{description}\nParameters: {parameters}"
        elif self.role == AgentRole.REVIEWER:
            prompt = f"Review this result:\n{description}\nParameters: {parameters}"
        else:  # COORDINATOR
            prompt = f"Coordinate execution of:\n{description}\nParameters: {parameters}"

        # Use router to process
        response = await self.workflow_engine.router.route_request(
            prompt=prompt,
            agent_id=self.agent_id,
            enable_rag=parameters.get('enable_rag', False)
        )

        return response

    async def _send_task_response(
        self,
        request_msg: AgentMessage,
        status: str,
        result: Optional[str],
        execution_time: float,
        error: Optional[str] = None
    ):
        """Send task response back"""
        response_msg = MessageBuilder.create_task_response(
            sender_id=self.agent_id,
            receiver_id=request_msg.sender_id,
            task_id=request_msg.payload['task_id'],
            status=status,
            result=result,
            execution_time=execution_time,
            error=error,
            correlation_id=request_msg.correlation_id
        )

        # Publish to response queue
        response_queue = request_msg.reply_to or "agent_responses"
        self.message_queue.publish_message(response_queue, response_msg)

    async def _publish_status(self, status: str):
        """Publish agent status"""
        status_msg = MessageBuilder.create_agent_status(
            agent_id=self.agent_id,
            status=status,
            current_tasks=[self.current_task] if self.current_task else [],
            capabilities=[self.role.value],
            load=0.0 if status == "idle" else 1.0
        )

        self.message_queue.publish_message("agent_status", status_msg)

    def get_statistics(self) -> Dict:
        """Get agent statistics"""
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "status": self.status,
            "current_task": self.current_task,
            "tasks_processed": self.tasks_processed,
            "tasks_failed": self.tasks_failed,
            "success_rate": (
                self.tasks_processed / (self.tasks_processed + self.tasks_failed)
                if (self.tasks_processed + self.tasks_failed) > 0
                else 0.0
            )
        }


class AgentPool:
    """Pool of agent workers"""

    def __init__(self, workflow_engine, message_queue: MessageQueue):
        self.workflow_engine = workflow_engine
        self.message_queue = message_queue
        self.agents: Dict[str, AgentWorker] = {}
        self.logger = logging.getLogger("AgentPool")

    def create_agent(
        self,
        agent_id: str,
        role: AgentRole,
        queue_name: str = "agent_tasks"
    ) -> AgentWorker:
        """Create a new agent worker"""
        agent = AgentWorker(
            agent_id=agent_id,
            role=role,
            workflow_engine=self.workflow_engine,
            message_queue=self.message_queue,
            queue_name=queue_name
        )

        self.agents[agent_id] = agent
        self.logger.info(f"Created agent: {agent_id} ({role.value})")

        return agent

    async def start_all(self):
        """Start all agents"""
        self.logger.info(f"Starting {len(self.agents)} agents...")

        tasks = [
            asyncio.create_task(agent.start())
            for agent in self.agents.values()
        ]

        await asyncio.gather(*tasks)

    async def stop_all(self):
        """Stop all agents"""
        self.logger.info("Stopping all agents...")

        for agent in self.agents.values():
            await agent.stop()

    def get_statistics(self) -> Dict:
        """Get statistics for all agents"""
        return {
            "total_agents": len(self.agents),
            "agents": [
                agent.get_statistics()
                for agent in self.agents.values()
            ]
        }
