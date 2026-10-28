"""
Redis Cache Manager for Agent Infrastructure
Provides caching layer for model responses and agent state
"""
import redis
import json
import logging
import os
from typing import Optional, Any, Dict
from datetime import timedelta


logger = logging.getLogger(__name__)


class RedisCache:
    """Redis-based cache manager"""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: Optional[int] = None,
        password: Optional[str] = None,
        default_ttl: int = 3600  # 1 hour default TTL
    ):
        self.host = host or os.getenv('REDIS_HOST', 'localhost')
        self.port = port or int(os.getenv('REDIS_PORT', 6379))
        self.db = db or int(os.getenv('REDIS_DB', 0))
        self.password = password or os.getenv('REDIS_PASSWORD', None)
        self.default_ttl = default_ttl

        self.client = None
        self.logger = logging.getLogger("RedisCache")
        self._is_connected = False

    def connect(self):
        """Connect to Redis"""
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password if self.password else None,
                decode_responses=True,
                socket_connect_timeout=5
            )

            # Test connection
            self.client.ping()
            self._is_connected = True
            self.logger.info(f"Connected to Redis at {self.host}:{self.port}")

        except redis.ConnectionError as e:
            self.logger.error(f"Failed to connect to Redis: {e}")
            self._is_connected = False
            self.logger.warning("Running without Redis cache (fallback to memory)")
        except Exception as e:
            self.logger.error(f"Redis connection error: {e}")
            self._is_connected = False

    def is_connected(self) -> bool:
        """Check if connected to Redis"""
        if not self._is_connected or not self.client:
            return False

        try:
            self.client.ping()
            return True
        except:
            self._is_connected = False
            return False

    def get(self, key: str) -> Optional[str]:
        """Get value from cache"""
        if not self.is_connected():
            return None

        try:
            value = self.client.get(key)
            if value:
                self.logger.debug(f"Cache hit: {key}")
            return value
        except Exception as e:
            self.logger.error(f"Error getting from cache: {e}")
            return None

    def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None
    ) -> bool:
        """Set value in cache with TTL"""
        if not self.is_connected():
            return False

        try:
            ttl = ttl or self.default_ttl
            self.client.setex(key, ttl, value)
            self.logger.debug(f"Cached: {key} (TTL={ttl}s)")
            return True
        except Exception as e:
            self.logger.error(f"Error setting cache: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.is_connected():
            return False

        try:
            self.client.delete(key)
            return True
        except Exception as e:
            self.logger.error(f"Error deleting from cache: {e}")
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists"""
        if not self.is_connected():
            return False

        try:
            return self.client.exists(key) > 0
        except Exception as e:
            self.logger.error(f"Error checking existence: {e}")
            return False

    def get_json(self, key: str) -> Optional[Any]:
        """Get JSON value from cache"""
        value = self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                self.logger.error(f"Error decoding JSON: {e}")
                return None
        return None

    def set_json(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """Set JSON value in cache"""
        try:
            json_str = json.dumps(value)
            return self.set(key, json_str, ttl)
        except (TypeError, ValueError) as e:
            self.logger.error(f"Error encoding JSON: {e}")
            return False

    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a counter"""
        if not self.is_connected():
            return None

        try:
            return self.client.incr(key, amount)
        except Exception as e:
            self.logger.error(f"Error incrementing: {e}")
            return None

    def get_ttl(self, key: str) -> Optional[int]:
        """Get TTL of a key (seconds)"""
        if not self.is_connected():
            return None

        try:
            ttl = self.client.ttl(key)
            return ttl if ttl > 0 else None
        except Exception as e:
            self.logger.error(f"Error getting TTL: {e}")
            return None

    def keys(self, pattern: str = "*") -> list:
        """Get keys matching pattern"""
        if not self.is_connected():
            return []

        try:
            return self.client.keys(pattern)
        except Exception as e:
            self.logger.error(f"Error getting keys: {e}")
            return []

    def flush(self) -> bool:
        """Flush all keys in current DB"""
        if not self.is_connected():
            return False

        try:
            self.client.flushdb()
            self.logger.info("Flushed Redis database")
            return True
        except Exception as e:
            self.logger.error(f"Error flushing database: {e}")
            return False

    def get_info(self) -> Dict:
        """Get Redis server info"""
        if not self.is_connected():
            return {}

        try:
            info = self.client.info()
            return {
                "version": info.get("redis_version"),
                "used_memory": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "total_commands_processed": info.get("total_commands_processed"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
            }
        except Exception as e:
            self.logger.error(f"Error getting info: {e}")
            return {}

    def get_stats(self) -> Dict:
        """Get cache statistics"""
        info = self.get_info()

        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses

        hit_rate = (hits / total * 100) if total > 0 else 0

        return {
            "connected": self.is_connected(),
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "hits": hits,
            "misses": misses,
            "hit_rate": round(hit_rate, 2),
            "memory_used": info.get("used_memory"),
        }

    def close(self):
        """Close Redis connection"""
        if self.client:
            try:
                self.client.close()
                self.logger.info("Redis connection closed")
            except Exception as e:
                self.logger.error(f"Error closing connection: {e}")
            finally:
                self._is_connected = False


class CacheWithFallback:
    """Cache that falls back to in-memory dict if Redis unavailable"""

    def __init__(self, redis_cache: RedisCache):
        self.redis_cache = redis_cache
        self.memory_cache: Dict[str, str] = {}
        self.logger = logging.getLogger("CacheWithFallback")

    def get(self, key: str) -> Optional[str]:
        """Get from Redis, fallback to memory"""
        # Try Redis first
        value = self.redis_cache.get(key)
        if value is not None:
            return value

        # Fallback to memory
        return self.memory_cache.get(key)

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Set in Redis and memory"""
        # Try Redis
        redis_success = self.redis_cache.set(key, value, ttl)

        # Always save to memory as fallback
        self.memory_cache[key] = value

        return redis_success or True  # Success if either works

    def delete(self, key: str) -> bool:
        """Delete from both"""
        redis_success = self.redis_cache.delete(key)
        if key in self.memory_cache:
            del self.memory_cache[key]
        return redis_success

    def exists(self, key: str) -> bool:
        """Check existence in either"""
        return self.redis_cache.exists(key) or (key in self.memory_cache)
