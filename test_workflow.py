"""
Test Workflow Engine with DAG Support
Tests task dependencies, parallel execution, and failure handling
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from dotenv import load_dotenv
load_dotenv()

import asyncio
from orchestration.task_dag import WorkflowBuilder, TaskStatus
from orchestration.workflow import WorkflowEngine, analysis_executor, planning_executor, review_executor
from infra.inference.router import ModelRouter
from infra.communication.message_queue import MessageQueue
from infra.storage.vector_store import VectorStore


async def test_simple_workflow():
    """Test a simple linear workflow"""
    print("=" * 60)
    print("Test 1: Simple Linear Workflow")
    print("=" * 60)

    # Build workflow
    builder = WorkflowBuilder()
    builder.add_task(
        task_id="task-1",
        task_type="analysis",
        description="Analyze what is a multi-agent system",
        dependencies=[]
    ).add_task(
        task_id="task-2",
        task_type="planning",
        description="Plan how to implement a multi-agent system",
        dependencies=["task-1"]
    )

    dag = builder.build()
    print(f"✓ Workflow created with {len(dag.tasks)} tasks")
    print(f"  Task 1: {dag.get_task('task-1').description}")
    print(f"  Task 2: {dag.get_task('task-2').description}")
    print()

    # Initialize components
    router = ModelRouter(primary_model="deepseek-chat", enable_caching=True)
    message_queue = MessageQueue()
    vector_store = VectorStore()

    # Create engine and register executors
    engine = WorkflowEngine(router, message_queue, vector_store)
    engine.register_executor("analysis", analysis_executor)
    engine.register_executor("planning", planning_executor)

    # Execute workflow
    print("Executing workflow...")
    result = await engine.execute_workflow("workflow-simple", dag)

    print(f"\n✓ Workflow completed!")
    print(f"  Status: {result['status']}")
    print(f"  Execution time: {result['execution_time']:.2f}s")
    print(f"  Statistics: {result['statistics']}")
    print()


async def test_parallel_workflow():
    """Test parallel task execution"""
    print("=" * 60)
    print("Test 2: Parallel Workflow Execution")
    print("=" * 60)

    # Build workflow with parallel tasks
    builder = WorkflowBuilder()

    # Initial task
    builder.add_task(
        task_id="init",
        task_type="analysis",
        description="Initialize multi-agent project",
        dependencies=[]
    )

    # Three parallel tasks
    builder.add_task(
        task_id="parallel-1",
        task_type="analysis",
        description="Analyze message queue architecture",
        dependencies=["init"]
    ).add_task(
        task_id="parallel-2",
        task_type="analysis",
        description="Analyze distributed inference",
        dependencies=["init"]
    ).add_task(
        task_id="parallel-3",
        task_type="analysis",
        description="Analyze context compression",
        dependencies=["init"]
    )

    # Final review task depends on all parallel tasks
    builder.add_task(
        task_id="review",
        task_type="review",
        description="Review all analysis results",
        dependencies=["parallel-1", "parallel-2", "parallel-3"]
    )

    dag = builder.build()
    print(f"✓ Workflow created with {len(dag.tasks)} tasks")
    print(f"  Structure: init → [3 parallel tasks] → review")
    print()

    # Initialize components
    router = ModelRouter(primary_model="deepseek-chat", enable_caching=True)
    message_queue = MessageQueue()
    vector_store = VectorStore()

    # Create engine
    engine = WorkflowEngine(router, message_queue, vector_store)
    engine.register_executor("analysis", analysis_executor)
    engine.register_executor("review", review_executor)

    # Execute workflow
    print("Executing workflow (3 tasks in parallel)...")
    result = await engine.execute_workflow("workflow-parallel", dag)

    print(f"\n✓ Workflow completed!")
    print(f"  Status: {result['status']}")
    print(f"  Execution time: {result['execution_time']:.2f}s")
    print(f"  Statistics: {result['statistics']}")

    # Show execution order
    print("\nTask execution times:")
    for task_id, task_result in result['results'].items():
        if task_result['execution_time']:
            print(f"  {task_id}: {task_result['execution_time']:.2f}s ({task_result['status']})")
    print()


async def test_dag_validation():
    """Test DAG validation (cycle detection)"""
    print("=" * 60)
    print("Test 3: DAG Validation (Cycle Detection)")
    print("=" * 60)

    # Try to create a cycle
    builder = WorkflowBuilder()
    builder.add_task(
        task_id="task-a",
        task_type="analysis",
        description="Task A",
        dependencies=["task-b"]  # A depends on B
    ).add_task(
        task_id="task-b",
        task_type="analysis",
        description="Task B",
        dependencies=["task-a"]  # B depends on A (cycle!)
    )

    try:
        dag = builder.build()  # Should raise error
        print("✗ Failed to detect cycle!")
    except ValueError as e:
        print(f"✓ Cycle detected correctly: {e}")

    print()


async def main():
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "Workflow Engine Test" + " " * 23 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    # Test 1: Simple linear workflow
    await test_simple_workflow()

    # Test 2: Parallel execution
    await test_parallel_workflow()

    # Test 3: Cycle detection
    await test_dag_validation()

    print("=" * 60)
    print("✓ All workflow tests completed!")
    print("=" * 60)
    print()


if __name__ == '__main__':
    asyncio.run(main())
