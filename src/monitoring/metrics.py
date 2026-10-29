"""
Prometheus Metrics for Agent Infrastructure
Collects and exposes metrics for monitoring
"""
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Summary,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST
)
import logging
from typing import Dict, Optional
import time


logger = logging.getLogger(__name__)


class MetricsCollector:
    """Centralized metrics collector for the agent infrastructure"""

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()
        self.logger = logging.getLogger("MetricsCollector")

        # Agent metrics
        self.agent_tasks_total = Counter(
            'agent_tasks_total',
            'Total number of tasks processed by agents',
            ['agent_id', 'role', 'status'],
            registry=self.registry
        )

        self.agent_task_duration = Histogram(
            'agent_task_duration_seconds',
            'Task execution duration in seconds',
            ['agent_id', 'role', 'task_type'],
            registry=self.registry
        )

        self.agent_active_tasks = Gauge(
            'agent_active_tasks',
            'Number of currently active tasks',
            ['agent_id', 'role'],
            registry=self.registry
        )

        # Router metrics
        self.router_requests_total = Counter(
            'router_requests_total',
            'Total number of routing requests',
            ['route_type'],  # cache, small, large
            registry=self.registry
        )

        self.router_cache_hits = Counter(
            'router_cache_hits_total',
            'Number of cache hits',
            registry=self.registry
        )

        self.router_cache_misses = Counter(
            'router_cache_misses_total',
            'Number of cache misses',
            registry=self.registry
        )

        self.router_response_time = Histogram(
            'router_response_time_seconds',
            'Router response time in seconds',
            ['route_type'],
            registry=self.registry
        )

        # Message queue metrics
        self.queue_messages_published = Counter(
            'queue_messages_published_total',
            'Total messages published to queue',
            ['queue_name', 'priority'],
            registry=self.registry
        )

        self.queue_messages_consumed = Counter(
            'queue_messages_consumed_total',
            'Total messages consumed from queue',
            ['queue_name', 'status'],  # ack, nack
            registry=self.registry
        )

        self.queue_size = Gauge(
            'queue_size',
            'Current queue size',
            ['queue_name'],
            registry=self.registry
        )

        self.queue_processing_time = Histogram(
            'queue_processing_time_seconds',
            'Message processing time',
            ['queue_name'],
            registry=self.registry
        )

        # Workflow metrics
        self.workflow_executions_total = Counter(
            'workflow_executions_total',
            'Total workflow executions',
            ['workflow_id', 'status'],
            registry=self.registry
        )

        self.workflow_duration = Histogram(
            'workflow_duration_seconds',
            'Workflow execution duration',
            ['workflow_id'],
            registry=self.registry
        )

        self.workflow_task_count = Histogram(
            'workflow_task_count',
            'Number of tasks in workflow',
            ['workflow_id'],
            registry=self.registry
        )

        # Redis cache metrics
        self.redis_operations_total = Counter(
            'redis_operations_total',
            'Total Redis operations',
            ['operation', 'status'],  # get/set/delete, success/failure
            registry=self.registry
        )

        self.redis_hit_rate = Gauge(
            'redis_hit_rate',
            'Redis cache hit rate percentage',
            registry=self.registry
        )

        self.redis_memory_used = Gauge(
            'redis_memory_used_bytes',
            'Redis memory usage in bytes',
            registry=self.registry
        )

        # System metrics
        self.system_errors_total = Counter(
            'system_errors_total',
            'Total system errors',
            ['component', 'error_type'],
            registry=self.registry
        )

        self.logger.info("Metrics collector initialized")

    # Agent metrics methods

    def record_agent_task(self, agent_id: str, role: str, status: str):
        """Record agent task completion"""
        self.agent_tasks_total.labels(
            agent_id=agent_id,
            role=role,
            status=status
        ).inc()

    def record_agent_task_duration(self, agent_id: str, role: str, task_type: str, duration: float):
        """Record task execution duration"""
        self.agent_task_duration.labels(
            agent_id=agent_id,
            role=role,
            task_type=task_type
        ).observe(duration)

    def set_agent_active_tasks(self, agent_id: str, role: str, count: int):
        """Set number of active tasks for agent"""
        self.agent_active_tasks.labels(
            agent_id=agent_id,
            role=role
        ).set(count)

    # Router metrics methods

    def record_router_request(self, route_type: str, response_time: float):
        """Record router request"""
        self.router_requests_total.labels(route_type=route_type).inc()
        self.router_response_time.labels(route_type=route_type).observe(response_time)

    def record_cache_hit(self):
        """Record cache hit"""
        self.router_cache_hits.inc()

    def record_cache_miss(self):
        """Record cache miss"""
        self.router_cache_misses.inc()

    # Queue metrics methods

    def record_message_published(self, queue_name: str, priority: str):
        """Record message published to queue"""
        self.queue_messages_published.labels(
            queue_name=queue_name,
            priority=priority
        ).inc()

    def record_message_consumed(self, queue_name: str, status: str):
        """Record message consumed from queue"""
        self.queue_messages_consumed.labels(
            queue_name=queue_name,
            status=status
        ).inc()

    def set_queue_size(self, queue_name: str, size: int):
        """Set current queue size"""
        self.queue_size.labels(queue_name=queue_name).set(size)

    def record_queue_processing_time(self, queue_name: str, duration: float):
        """Record message processing time"""
        self.queue_processing_time.labels(queue_name=queue_name).observe(duration)

    # Workflow metrics methods

    def record_workflow_execution(self, workflow_id: str, status: str, duration: float, task_count: int):
        """Record workflow execution"""
        self.workflow_executions_total.labels(
            workflow_id=workflow_id,
            status=status
        ).inc()

        self.workflow_duration.labels(workflow_id=workflow_id).observe(duration)
        self.workflow_task_count.labels(workflow_id=workflow_id).observe(task_count)

    # Redis metrics methods

    def record_redis_operation(self, operation: str, status: str):
        """Record Redis operation"""
        self.redis_operations_total.labels(
            operation=operation,
            status=status
        ).inc()

    def update_redis_stats(self, hit_rate: float, memory_used: int):
        """Update Redis statistics"""
        self.redis_hit_rate.set(hit_rate)
        self.redis_memory_used.set(memory_used)

    # System metrics methods

    def record_error(self, component: str, error_type: str):
        """Record system error"""
        self.system_errors_total.labels(
            component=component,
            error_type=error_type
        ).inc()

    # Export metrics

    def export_metrics(self) -> bytes:
        """Export metrics in Prometheus format"""
        return generate_latest(self.registry)

    def get_content_type(self) -> str:
        """Get Prometheus content type"""
        return CONTENT_TYPE_LATEST


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create global metrics collector"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def reset_metrics():
    """Reset global metrics collector (for testing)"""
    global _metrics_collector
    _metrics_collector = None
