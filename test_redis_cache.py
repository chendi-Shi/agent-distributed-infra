"""
Test Redis Cache Integration
Tests Redis caching with Router
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from dotenv import load_dotenv
load_dotenv()

import asyncio
from infra.storage.redis_cache import RedisCache
from infra.inference.router import ModelRouter


def test_redis_connection():
    """Test Redis connection"""
    print("=" * 60)
    print("Test 1: Redis Connection")
    print("=" * 60)

    cache = RedisCache()
    cache.connect()

    if cache.is_connected():
        print(f"✓ Connected to Redis at {cache.host}:{cache.port}")

        # Get server info
        info = cache.get_info()
        print(f"  Redis version: {info.get('version')}")
        print(f"  Memory used: {info.get('used_memory')}")
        print(f"  Connected clients: {info.get('connected_clients')}")
    else:
        print("✗ Failed to connect to Redis")
        print("  Will use in-memory cache fallback")

    print()
    return cache


def test_basic_cache_operations(cache: RedisCache):
    """Test basic cache operations"""
    print("=" * 60)
    print("Test 2: Basic Cache Operations")
    print("=" * 60)

    # Set a value
    key = "test:hello"
    value = "world"
    success = cache.set(key, value, ttl=60)
    print(f"✓ Set {key} = {value} (success={success})")

    # Get the value
    retrieved = cache.get(key)
    print(f"✓ Get {key} = {retrieved}")
    assert retrieved == value, "Value mismatch!"

    # Check existence
    exists = cache.exists(key)
    print(f"✓ Exists {key} = {exists}")

    # Get TTL
    ttl = cache.get_ttl(key)
    print(f"✓ TTL {key} = {ttl} seconds")

    # Delete
    cache.delete(key)
    print(f"✓ Deleted {key}")

    # Verify deletion
    exists_after = cache.exists(key)
    print(f"✓ Exists after delete = {exists_after}")

    print()


def test_json_cache(cache: RedisCache):
    """Test JSON caching"""
    print("=" * 60)
    print("Test 3: JSON Cache")
    print("=" * 60)

    # Cache a complex object
    key = "test:user"
    user_data = {
        "id": "user-123",
        "name": "Test Agent",
        "role": "worker",
        "stats": {
            "tasks_completed": 42,
            "success_rate": 0.95
        }
    }

    success = cache.set_json(key, user_data, ttl=120)
    print(f"✓ Cached JSON object (success={success})")

    # Retrieve
    retrieved = cache.get_json(key)
    print(f"✓ Retrieved: {retrieved}")

    assert retrieved == user_data, "JSON mismatch!"
    print("✓ JSON data matches!")

    # Cleanup
    cache.delete(key)
    print()


async def test_router_with_redis_cache():
    """Test Router with Redis cache"""
    print("=" * 60)
    print("Test 4: Router with Redis Cache")
    print("=" * 60)

    # Create router (will auto-connect to Redis)
    router = ModelRouter(primary_model="deepseek-chat", enable_caching=True, cache_ttl=300)

    if router.redis_cache.is_connected():
        print("✓ Router connected to Redis")
    else:
        print("⚠ Router using in-memory fallback")

    print()

    # Test queries
    queries = [
        "What is 2+2?",
        "Explain caching in one sentence",
        "What is 2+2?",  # Duplicate - should hit cache
    ]

    print("Running queries...")
    for i, query in enumerate(queries, 1):
        print(f"\nQuery {i}: {query}")
        response = await router.route_request(
            prompt=query,
            agent_id="test-agent"
        )
        print(f"  Response: {response[:100]}...")

    # Get stats
    stats = router.get_stats()
    print(f"\n✓ Router statistics:")
    print(f"  Total requests: {stats['total_requests']}")
    print(f"  Cache hits: {stats['cache_hits']}")
    print(f"  Cache hit rate: {stats['cache_hits']/stats['total_requests']*100:.1f}%")
    print(f"  Small model calls: {stats['small_model_calls']}")
    print(f"  Large model calls: {stats['large_model_calls']}")

    # Get Redis stats
    if router.redis_cache.is_connected():
        redis_stats = router.redis_cache.get_stats()
        print(f"\n✓ Redis statistics:")
        print(f"  Hit rate: {redis_stats['hit_rate']}%")
        print(f"  Memory used: {redis_stats['memory_used']}")

    print()


async def main():
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 18 + "Redis Cache Test" + " " * 22 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    # Test 1: Connection
    cache = test_redis_connection()

    if cache.is_connected():
        # Test 2: Basic operations
        test_basic_cache_operations(cache)

        # Test 3: JSON caching
        test_json_cache(cache)

    # Test 4: Router integration
    await test_router_with_redis_cache()

    print("=" * 60)
    print("✓ All Redis cache tests completed!")
    print("=" * 60)
    print()


if __name__ == '__main__':
    asyncio.run(main())
