"""
系统监控模块

实时采集：
1. 队列长度（RabbitMQ）
2. CPU/内存利用率
3. 任务成功率（滑动窗口）
4. 平均执行时间
"""

import psutil
import time
from dataclasses import dataclass
from typing import Optional, List
from collections import deque
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class SystemState:
    """系统状态快照"""
    queue_length: int
    cpu_utilization: float  # 0-1
    memory_usage: float  # 0-1
    recent_success_rate: float  # 0-1
    avg_execution_time: float  # seconds
    timestamp: datetime

    def is_overloaded(self) -> bool:
        """系统是否过载"""
        return (
            self.queue_length > 10 or
            self.cpu_utilization > 0.9 or
            self.memory_usage > 0.85
        )

    def is_idle(self) -> bool:
        """系统是否空闲"""
        return (
            self.queue_length < 3 and
            self.cpu_utilization < 0.5 and
            self.memory_usage < 0.6
        )

    def to_dict(self):
        return {
            "queue_length": self.queue_length,
            "cpu_utilization": self.cpu_utilization,
            "memory_usage": self.memory_usage,
            "recent_success_rate": self.recent_success_rate,
            "avg_execution_time": self.avg_execution_time,
            "timestamp": self.timestamp.isoformat(),
            "is_overloaded": self.is_overloaded(),
            "is_idle": self.is_idle(),
        }


@dataclass
class TaskExecution:
    """任务执行记录"""
    task_id: str
    success: bool
    execution_time: float
    timestamp: datetime


class SystemMonitor:
    """
    系统监控器

    功能：
    1. 实时采集系统指标
    2. 计算滑动窗口统计
    3. 触发告警
    """

    def __init__(
        self,
        window_size: int = 100,  # 滑动窗口大小
        queue_client=None,  # RabbitMQ 客户端
    ):
        self.window_size = window_size
        self.queue_client = queue_client

        # 滑动窗口：最近 N 次任务执行
        self.execution_history: deque[TaskExecution] = deque(maxlen=window_size)

        # 统计
        self.total_tasks = 0
        self.successful_tasks = 0

        logger.info(f"SystemMonitor initialized with window_size={window_size}")

    def record_execution(
        self,
        task_id: str,
        success: bool,
        execution_time: float
    ):
        """
        记录任务执行

        Args:
            task_id: 任务 ID
            success: 是否成功
            execution_time: 执行时间（秒）
        """
        record = TaskExecution(
            task_id=task_id,
            success=success,
            execution_time=execution_time,
            timestamp=datetime.now()
        )

        self.execution_history.append(record)
        self.total_tasks += 1
        if success:
            self.successful_tasks += 1

    def get_current_state(self) -> SystemState:
        """
        获取当前系统状态

        Returns:
            SystemState 对象
        """
        # 1. CPU 利用率
        cpu_percent = psutil.cpu_percent(interval=0.1) / 100.0

        # 2. 内存使用率
        memory = psutil.virtual_memory()
        memory_percent = memory.percent / 100.0

        # 3. 队列长度
        queue_length = self._get_queue_length()

        # 4. 最近成功率（滑动窗口）
        recent_success_rate = self._calculate_success_rate()

        # 5. 平均执行时间（滑动窗口）
        avg_execution_time = self._calculate_avg_execution_time()

        state = SystemState(
            queue_length=queue_length,
            cpu_utilization=cpu_percent,
            memory_usage=memory_percent,
            recent_success_rate=recent_success_rate,
            avg_execution_time=avg_execution_time,
            timestamp=datetime.now()
        )

        return state

    def _get_queue_length(self) -> int:
        """获取队列长度"""
        if self.queue_client:
            try:
                # 假设 queue_client 有 get_queue_length 方法
                return self.queue_client.get_queue_length()
            except Exception as e:
                logger.warning(f"Failed to get queue length: {e}")

        # 降级：从执行历史估算
        # 最近 1 分钟内启动但未完成的任务数
        one_min_ago = datetime.now() - timedelta(minutes=1)
        pending = sum(
            1 for rec in self.execution_history
            if rec.timestamp > one_min_ago and not rec.success
        )
        return pending

    def _calculate_success_rate(self) -> float:
        """计算最近成功率"""
        if not self.execution_history:
            return 1.0

        total = len(self.execution_history)
        successful = sum(1 for rec in self.execution_history if rec.success)

        return successful / total if total > 0 else 1.0

    def _calculate_avg_execution_time(self) -> float:
        """计算平均执行时间"""
        if not self.execution_history:
            return 5.0  # 默认值

        times = [rec.execution_time for rec in self.execution_history]
        return sum(times) / len(times)

    def get_statistics(self) -> dict:
        """获取完整统计"""
        state = self.get_current_state()

        return {
            "current_state": state.to_dict(),
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "overall_success_rate": (
                self.successful_tasks / self.total_tasks
                if self.total_tasks > 0 else 1.0
            ),
            "window_size": len(self.execution_history),
        }

    def check_alerts(self) -> List[str]:
        """
        检查告警条件

        Returns:
            告警消息列表
        """
        alerts = []
        state = self.get_current_state()

        if state.cpu_utilization > 0.9:
            alerts.append(f"⚠️ CPU 利用率过高: {state.cpu_utilization:.1%}")

        if state.memory_usage > 0.85:
            alerts.append(f"⚠️ 内存使用率过高: {state.memory_usage:.1%}")

        if state.queue_length > 20:
            alerts.append(f"⚠️ 队列积压严重: {state.queue_length} 任务")

        if state.recent_success_rate < 0.7:
            alerts.append(f"⚠️ 最近成功率偏低: {state.recent_success_rate:.1%}")

        return alerts


class PerformanceTracker:
    """
    性能追踪器

    用于反思时分析性能趋势
    """

    def __init__(self, history_limit: int = 1000):
        self.history_limit = history_limit
        self.state_history: deque[SystemState] = deque(maxlen=history_limit)

    def record_state(self, state: SystemState):
        """记录系统状态"""
        self.state_history.append(state)

    def get_trend(self, metric: str, minutes: int = 10) -> dict:
        """
        获取指标趋势

        Args:
            metric: 指标名称 (cpu_utilization, memory_usage, queue_length, etc.)
            minutes: 时间范围（分钟）

        Returns:
            {
                "trend": "rising" | "falling" | "stable",
                "change_rate": float,
                "current_value": float,
                "min_value": float,
                "max_value": float
            }
        """
        if not self.state_history:
            return {"trend": "stable", "change_rate": 0.0}

        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        recent_states = [
            s for s in self.state_history
            if s.timestamp > cutoff_time
        ]

        if len(recent_states) < 2:
            return {"trend": "stable", "change_rate": 0.0}

        # 提取指标值
        values = [getattr(s, metric) for s in recent_states]

        # 计算趋势
        first_half = values[:len(values)//2]
        second_half = values[len(values)//2:]

        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)

        change_rate = (avg_second - avg_first) / avg_first if avg_first > 0 else 0

        if change_rate > 0.1:
            trend = "rising"
        elif change_rate < -0.1:
            trend = "falling"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "change_rate": change_rate,
            "current_value": values[-1],
            "min_value": min(values),
            "max_value": max(values),
        }

    def should_scale_down(self) -> bool:
        """是否应该降低并行度"""
        cpu_trend = self.get_trend("cpu_utilization")
        memory_trend = self.get_trend("memory_usage")

        return (
            cpu_trend["trend"] == "rising" and cpu_trend["current_value"] > 0.8 or
            memory_trend["trend"] == "rising" and memory_trend["current_value"] > 0.8
        )

    def should_scale_up(self) -> bool:
        """是否应该提高并行度"""
        cpu_trend = self.get_trend("cpu_utilization")
        queue_trend = self.get_trend("queue_length")

        return (
            cpu_trend["trend"] == "stable" and cpu_trend["current_value"] < 0.5 and
            queue_trend["current_value"] > 5
        )
