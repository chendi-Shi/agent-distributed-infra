"""
Model Router for Intelligent Inference Routing
Decides: cache / small model / large model
"""
import os
import hashlib
import logging
import time
from typing import Optional, Dict
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from infra.storage.redis_cache import RedisCache, CacheWithFallback
from monitoring.metrics import get_metrics_collector

logger = logging.getLogger(__name__)


class ModelRouter:
    """
    Intelligent model router that decides:
    1. Check cache (Redis)
    2. Use small model (Router model) for simple queries
    3. Use large model (GPT-4/DeepSeek) for complex queries
    """

    def __init__(self, primary_model: str, enable_caching: bool = True, cache_ttl: int = 3600):
        self.primary_model = primary_model
        self.enable_caching = enable_caching
        self.cache_ttl = cache_ttl
        self.logger = logging.getLogger("ModelRouter")

        # Initialize metrics collector
        self.metrics = get_metrics_collector()

        # Initialize Redis cache with fallback
        self.redis_cache = RedisCache(default_ttl=cache_ttl)
        self.redis_cache.connect()
        self.cache = CacheWithFallback(self.redis_cache)

        # Initialize primary LLM
        self.llm = ChatOpenAI(
            model=primary_model,
            openai_api_key=os.getenv('DEEPSEEK_API_KEY'),
            openai_api_base=os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
            temperature=0.7
        )

        # TODO: Load router model for decision making
        # self.router_model = self._load_router_model()

        self.logger.info(f"Model Router initialized with {primary_model}")

        # Statistics
        self.stats = {
            "cache_hits": 0,
            "small_model_calls": 0,
            "large_model_calls": 0,
            "total_requests": 0
        }

    async def route_request(
        self,
        prompt: str,
        agent_id: str,
        enable_rag: bool = False,
        force_large_model: bool = False
    ) -> str:
        """
        Route request to appropriate backend

        Args:
            prompt: Input prompt
            agent_id: Agent making the request
            enable_rag: Whether to use RAG retrieval
            force_large_model: Force using large model

        Returns:
            Model response
        """
        start_time = time.time()
        self.stats["total_requests"] += 1

        # Step 1: Check cache
        if self.enable_caching and not force_large_model:
            cache_key = self._generate_cache_key(prompt)
            cached_response = self._get_from_cache(cache_key)

            if cached_response:
                self.stats["cache_hits"] += 1
                self.logger.debug(f"Cache hit for agent {agent_id}")

                # Record metrics
                self.metrics.record_cache_hit()
                self.metrics.record_router_request("cache", time.time() - start_time)

                return cached_response
            else:
                self.metrics.record_cache_miss()

        # Step 2: Decide routing strategy
        if force_large_model:
            route = "large"
        else:
            route = await self._decide_route(prompt)

        # Step 3: Execute based on route
        if route == "small":
            response = await self._call_small_model(prompt)
            self.stats["small_model_calls"] += 1
        else:
            response = await self._call_large_model(prompt)
            self.stats["large_model_calls"] += 1

        # Step 4: Cache response
        if self.enable_caching:
            cache_key = self._generate_cache_key(prompt)
            self._save_to_cache(cache_key, response)

        # Record metrics
        response_time = time.time() - start_time
        self.metrics.record_router_request(route, response_time)

        self.logger.info(
            f"Request routed to {route} model for agent {agent_id} "
            f"(Cache: {self.stats['cache_hits']}/{self.stats['total_requests']}) "
            f"in {response_time:.2f}s"
        )

        return response

    async def _decide_route(self, prompt: str) -> str:
        """
        Decide routing strategy

        TODO: Use trained router model for decision
        Currently uses simple heuristics
        """
        # Simple heuristic: length-based routing
        if len(prompt) < 100 and "?" in prompt:
            return "small"  # Simple query
        else:
            return "large"  # Complex query

    async def _call_small_model(self, prompt: str) -> str:
        """Call small model (currently falls back to large model)"""
        # TODO: Implement actual small model call
        # For now, use same model with simpler prompt
        self.logger.debug("Calling small model")
        return await self._call_large_model(prompt)

    async def _call_large_model(self, prompt: str) -> str:
        """Call large model (DeepSeek/GPT-4)"""
        self.logger.debug("Calling large model")

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return response.content

        except Exception as e:
            self.logger.error(f"Large model call failed: {e}")
            raise

    def _generate_cache_key(self, prompt: str) -> str:
        """Generate cache key from prompt"""
        return hashlib.md5(prompt.encode()).hexdigest()

    def _get_from_cache(self, key: str) -> Optional[str]:
        """Get response from cache (Redis with memory fallback)"""
        return self.cache.get(key)

    def _save_to_cache(self, key: str, response: str):
        """Save response to cache (Redis with memory fallback)"""
        self.cache.set(key, response, ttl=self.cache_ttl)

    def get_stats(self) -> Dict:
        """Get routing statistics"""
        return self.stats.copy()

    def _load_router_model(self):
        """Load trained router model"""
        # TODO: Implement router model loading
        # This will be trained in Phase 3
        pass
