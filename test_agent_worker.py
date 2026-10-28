"""
Test Agent Worker with RabbitMQ Integration
Tests agents consuming and processing tasks from message queue
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from dotenv import load_dotenv
load_dotenv()

import asyncio
import time
from agents.agent_worker import AgentPool
from agents.multi_agent import AgentRole
from infra.communication.message_protocol import MessageBuilder, MessagePriority
from infra.communication.message_queue import MessageQueue
from infra.inference.router import ModelRouter
from infra.storage.vector_store import VectorStore
from orchestration.workflow import WorkflowEngine


async def test_agent_worker():
    """Test single agent processing tasks"""
    print("=" * 60)
    print("Test: Agent Worker Processing Tasks")
    print("=" * 60)
    print()

    # Initialize components
    router = ModelRouter(primary_model="deepseek-chat", enable_caching=True)
    message_queue = MessageQueue()
    vector_store = VectorStore()
    workflow_engine = WorkflowEngine(router, message_queue, vector_store)

    # Create agent pool
    pool = AgentPool(workflow_engine, message_queue)

    # Create one worker agent
    worker = pool.create_agent("worker-1", AgentRole.WORKER)
    print(f"✓ Created agent: {worker.agent_id}")
    print()

    # Publish test tasks to the queue
    print("Publishing tasks to queue...")
    tasks = [
        ("task-1", "What is a multi-agent system?", MessagePriority.NORMAL),
        ("task-2", "Explain message queues", MessagePriority.HIGH),
        ("task-3", "What is workflow orchestration?", MessagePriority.URGENT),
    ]

    for task_id, description, priority in tasks:
        msg = MessageBuilder.create_task_request(
            sender_id="coordinator",
            receiver_id=worker.agent_id,
            task_id=task_id,
            task_type="analysis",
            description=description,
            priority=priority
        )
        msg.reply_to = "agent_responses"  # Where to send responses

        message_queue.publish_message("agent_tasks", msg)
        print(f"  ✓ Published: {task_id} [{priority.name}]")

    print()

    # Start agent in background
    print("Starting agent worker...")
    agent_task = asyncio.create_task(worker.start())

    # Give it time to process tasks
    await asyncio.sleep(60)  # Wait 1 minute for processing

    # Stop agent
    print("\nStopping agent...")
    message_queue.stop_consuming("agent_tasks")

    # Get statistics
    stats = worker.get_statistics()
    print(f"\n✓ Agent statistics:")
    print(f"  Agent ID: {stats['agent_id']}")
    print(f"  Role: {stats['role']}")
    print(f"  Status: {stats['status']}")
    print(f"  Tasks processed: {stats['tasks_processed']}")
    print(f"  Tasks failed: {stats['tasks_failed']}")
    print(f"  Success rate: {stats['success_rate']*100:.1f}%")
    print()


async def test_multi_agent_pool():
    """Test multiple agents working together"""
    print("=" * 60)
    print("Test: Multi-Agent Pool")
    print("=" * 60)
    print()

    # Initialize components
    router = ModelRouter(primary_model="deepseek-chat", enable_caching=True)
    message_queue = MessageQueue()
    vector_store = VectorStore()
    workflow_engine = WorkflowEngine(router, message_queue, vector_store)

    # Create agent pool with multiple agents
    pool = AgentPool(workflow_engine, message_queue)

    # Create different types of agents
    pool.create_agent("planner-1", AgentRole.PLANNER)
    pool.create_agent("worker-1", AgentRole.WORKER)
    pool.create_agent("worker-2", AgentRole.WORKER)
    pool.create_agent("reviewer-1", AgentRole.REVIEWER)

    print(f"✓ Created {len(pool.agents)} agents")
    print()

    # Publish tasks for different agent types
    print("Publishing tasks...")

    # Task for planner
    msg = MessageBuilder.create_task_request(
        sender_id="coordinator",
        receiver_id="planner-1",
        task_id="plan-task",
        task_type="planning",
        description="Plan the implementation of a distributed agent system",
        parameters={"required_role": "planner"},
        priority=MessagePriority.HIGH
    )
    message_queue.publish_message("agent_tasks", msg)
    print("  ✓ Published planning task")

    # Tasks for workers
    for i in range(3):
        msg = MessageBuilder.create_task_request(
            sender_id="coordinator",
            receiver_id=f"worker-{(i%2)+1}",
            task_id=f"work-task-{i+1}",
            task_type="execution",
            description=f"Execute subtask {i+1}",
            parameters={"required_role": "worker"},
            priority=MessagePriority.NORMAL
        )
        message_queue.publish_message("agent_tasks", msg)
    print("  ✓ Published 3 worker tasks")

    # Task for reviewer
    msg = MessageBuilder.create_task_request(
        sender_id="coordinator",
        receiver_id="reviewer-1",
        task_id="review-task",
        task_type="review",
        description="Review the completed work",
        parameters={"required_role": "reviewer"},
        priority=MessagePriority.NORMAL
    )
    message_queue.publish_message("agent_tasks", msg)
    print("  ✓ Published review task")

    print()

    # Check queue size
    queue_size = message_queue.get_queue_size("agent_tasks")
    print(f"✓ Queue size: {queue_size} tasks")
    print()

    print("Note: Run agents separately to see them process these tasks")
    print("  Command: python -c 'from test_agent_worker import start_agent_pool; import asyncio; asyncio.run(start_agent_pool())'")
    print()


async def start_agent_pool():
    """Helper function to start agent pool (for manual testing)"""
    router = ModelRouter(primary_model="deepseek-chat", enable_caching=True)
    message_queue = MessageQueue()
    vector_store = VectorStore()
    workflow_engine = WorkflowEngine(router, message_queue, vector_store)

    pool = AgentPool(workflow_engine, message_queue)
    pool.create_agent("worker-1", AgentRole.WORKER)

    print("Starting agent pool... (Press Ctrl+C to stop)")
    try:
        await pool.start_all()
    except KeyboardInterrupt:
        print("\nStopping...")
        await pool.stop_all()


async def main():
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "Agent Worker Test" + " " * 26 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    # Test 1: Single agent
    print("Skipping live agent test (requires long-running process)")
    print("Use the following command to start agents manually:")
    print("  python -c 'from test_agent_worker import start_agent_pool; import asyncio; asyncio.run(start_agent_pool())'")
    print()

    # Test 2: Multi-agent pool setup
    await test_multi_agent_pool()

    print("=" * 60)
    print("✓ Agent worker tests completed!")
    print("=" * 60)
    print()


if __name__ == '__main__':
    asyncio.run(main())
