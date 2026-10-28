"""
Simple Multi-Agent Example
Demonstrates basic multi-agent task decomposition and execution
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from agents.multi_agent import Agent, AgentRole, MultiAgentSystem
from infra.inference.router import ModelRouter
from infra.communication.message_queue import MessageQueue
from infra.storage.vector_store import VectorStore
from orchestration.workflow import WorkflowEngine


async def main():
    print("=" * 60)
    print("Simple Multi-Agent Example")
    print("=" * 60)
    print()

    # Initialize components
    print("Initializing components...")

    router = ModelRouter(primary_model="deepseek-chat", enable_caching=True)
    message_queue = MessageQueue()
    vector_store = VectorStore()
    workflow_engine = WorkflowEngine(router, message_queue, vector_store)

    multi_agent_system = MultiAgentSystem(workflow_engine, max_agents=5)

    print("✓ Components initialized\n")

    # Example task
    task = {
        "task_id": "task-001",
        "description": "Explain what is multi-agent system and how it works",
        "required_role": AgentRole.PLANNER
    }

    print(f"Submitting task: {task['description']}")
    print()

    # Submit task
    await multi_agent_system.submit_task(task)

    # Give some time for processing
    await asyncio.sleep(5)

    # Get statistics
    stats = router.get_stats()
    print("\nRouter Statistics:")
    print(f"  Total Requests: {stats['total_requests']}")
    print(f"  Cache Hits: {stats['cache_hits']}")
    print(f"  Small Model: {stats['small_model_calls']}")
    print(f"  Large Model: {stats['large_model_calls']}")

    print("\n" + "=" * 60)
    print("Example completed!")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
