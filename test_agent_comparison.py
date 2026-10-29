"""
Test Agent Comparison Framework
Run comparison experiment with sample tasks
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging

from experiments.agent_comparison import AgentComparisonFramework
from infra.inference.router import ModelRouter


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


# Sample tasks for comparison
SAMPLE_TASKS = [
    {
        "id": "task-001",
        "description": "Analyze the performance bottlenecks in a distributed system",
        "parameters": {
            "system_type": "microservices",
            "metrics": ["latency", "throughput", "error_rate"]
        }
    },
    {
        "id": "task-002",
        "description": "Design a caching strategy for a high-traffic web application",
        "parameters": {
            "traffic": "10M requests/day",
            "cache_types": ["Redis", "CDN", "browser"]
        }
    },
    {
        "id": "task-003",
        "description": "Review code for security vulnerabilities",
        "parameters": {
            "language": "Python",
            "focus_areas": ["SQL injection", "XSS", "authentication"]
        }
    }
]


async def main():
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 25 + "AGENT COMPARISON TEST" + " " * 32 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    # Initialize router
    print("Initializing Model Router...")
    router = ModelRouter(
        primary_model="deepseek-chat",
        enable_caching=True,
        cache_ttl=300
    )
    print(f"✓ Router initialized with {router.primary_model}\n")

    # Initialize comparison framework
    print("Initializing Comparison Framework...")
    framework = AgentComparisonFramework(router)
    print("✓ Framework initialized\n")

    # Run comparison
    print(f"Running comparison with {len(SAMPLE_TASKS)} tasks...")
    print("This will test 3 modes × 3 tasks = 9 executions\n")

    results = await framework.run_comparison(SAMPLE_TASKS)

    # Print results
    framework.print_results()

    # Save results
    framework.save_results("comparison_results.json")

    print("\n✓ Comparison completed!")
    print("  Results saved to: comparison_results.json")
    print()


if __name__ == '__main__':
    asyncio.run(main())
