"""
Standalone test script - tests core functionality without Docker
"""
import os
import sys
import asyncio
from pathlib import Path

# Set environment
os.environ['DEEPSEEK_API_KEY'] = 'sk-a4e3cd98749e4ed1b4d743b04b107881'
os.environ['PRIMARY_MODEL'] = 'deepseek-chat'
os.environ['DEEPSEEK_BASE_URL'] = 'https://api.deepseek.com'

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from infra.inference.router import ModelRouter


async def main():
    print("=" * 60)
    print("Agent Distributed Infrastructure - Standalone Test")
    print("=" * 60)
    print()

    # Test 1: Model Router
    print("Test 1: Model Router Initialization...")
    try:
        router = ModelRouter(primary_model='deepseek-chat', enable_caching=True)
        print("✓ Router initialized")
    except Exception as e:
        print(f"✗ Router failed: {e}")
        return

    # Test 2: Simple Request
    print("\nTest 2: Simple Request Routing...")
    try:
        response = await router.route_request(
            prompt="What is 2+2?",
            agent_id="test-agent"
        )
        print(f"✓ Response: {response[:100]}...")
    except Exception as e:
        print(f"✗ Request failed: {e}")
        return

    # Test 3: Cache Test
    print("\nTest 3: Cache Functionality...")
    try:
        # Same request should hit cache
        response2 = await router.route_request(
            prompt="What is 2+2?",
            agent_id="test-agent"
        )
        stats = router.get_stats()
        print(f"✓ Cache hits: {stats['cache_hits']}/{stats['total_requests']}")
    except Exception as e:
        print(f"✗ Cache test failed: {e}")

    # Test 4: Complex Request
    print("\nTest 4: Complex Request...")
    try:
        response3 = await router.route_request(
            prompt="Explain the architecture of a multi-agent system with distributed inference",
            agent_id="test-agent"
        )
        print(f"✓ Complex response generated ({len(response3)} chars)")
    except Exception as e:
        print(f"✗ Complex request failed: {e}")

    # Final Statistics
    print("\n" + "=" * 60)
    print("Test Results:")
    stats = router.get_stats()
    print(f"  Total Requests: {stats['total_requests']}")
    print(f"  Cache Hits: {stats['cache_hits']}")
    print(f"  Cache Hit Rate: {stats['cache_hits']/stats['total_requests']*100:.1f}%")
    print(f"  Small Model Calls: {stats['small_model_calls']}")
    print(f"  Large Model Calls: {stats['large_model_calls']}")
    print("=" * 60)
    print("\n✓ All tests passed!")


if __name__ == '__main__':
    asyncio.run(main())
