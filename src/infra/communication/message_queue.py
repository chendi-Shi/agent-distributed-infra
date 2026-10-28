"""Message Queue for Agent Communication"""
import logging
import pika
import asyncio
from typing import Callable, Dict, Optional
from datetime import datetime
import os

from .message_protocol import AgentMessage, MessagePriority

logger = logging.getLogger(__name__)


class MessageQueue:
    """RabbitMQ wrapper for agent communication with priority support"""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ):
        self.host = host or os.getenv('RABBITMQ_HOST', 'localhost')
        self.port = port or int(os.getenv('RABBITMQ_PORT', 5672))
        self.user = user or os.getenv('RABBITMQ_USER', 'admin')
        self.password = password or os.getenv('RABBITMQ_PASSWORD', 'admin123')

        self.connection = None
        self.channel = None
        self.logger = logging.getLogger("MessageQueue")
        self._consumers = {}  # Track active consumers
        self._is_connected = False

    def connect(self):
        """Connect to RabbitMQ"""
        try:
            credentials = pika.PlainCredentials(self.user, self.password)
            parameters = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            self._is_connected = True
            self.logger.info(f"Connected to RabbitMQ at {self.host}:{self.port}")

        except Exception as e:
            self.logger.error(f"Failed to connect to RabbitMQ: {e}")
            self._is_connected = False
            self.logger.warning("Running without message queue")

    def declare_queue(self, queue: str, priority: bool = True):
        """Declare a queue with optional priority support"""
        if not self.channel:
            return

        try:
            args = {}
            if priority:
                args['x-max-priority'] = 10  # Support priority 0-10

            self.channel.queue_declare(
                queue=queue,
                durable=True,
                arguments=args
            )
            self.logger.debug(f"Declared queue: {queue} (priority={priority})")
        except Exception as e:
            self.logger.error(f"Failed to declare queue {queue}: {e}")

    def publish(self, queue: str, message: str, priority: int = 5):
        """Publish message to queue with priority"""
        if not self.channel:
            self.logger.warning("Message queue not connected, skipping publish")
            return False

        try:
            self.declare_queue(queue, priority=True)

            properties = pika.BasicProperties(
                delivery_mode=2,  # Persistent
                priority=priority,
                timestamp=int(datetime.utcnow().timestamp())
            )

            self.channel.basic_publish(
                exchange='',
                routing_key=queue,
                body=message,
                properties=properties
            )
            self.logger.debug(f"Published to {queue} (priority={priority}): {message[:50]}...")
            return True

        except Exception as e:
            self.logger.error(f"Failed to publish message: {e}")
            return False

    def publish_message(self, queue: str, message: AgentMessage) -> bool:
        """Publish AgentMessage object to queue"""
        try:
            # Map MessagePriority to RabbitMQ priority (0-10)
            priority_map = {
                1: 2,   # LOW
                2: 5,   # NORMAL
                3: 8,   # HIGH
                4: 10   # URGENT
            }
            rabbitmq_priority = priority_map.get(message.priority, 5)

            json_str = message.to_json()
            return self.publish(queue, json_str, priority=rabbitmq_priority)
        except Exception as e:
            self.logger.error(f"Failed to publish AgentMessage: {e}")
            return False

    def consume(self, queue: str, callback: Callable, prefetch_count: int = 1):
        """Consume messages from queue with manual ACK"""
        if not self.channel:
            self.logger.warning("Message queue not connected, skipping consume")
            return

        try:
            self.declare_queue(queue, priority=True)

            # Set QoS - only process prefetch_count messages at a time
            self.channel.basic_qos(prefetch_count=prefetch_count)

            def wrapped_callback(ch, method, properties, body):
                """Wrapper that adds ACK/NACK support"""
                try:
                    # Decode message
                    message_str = body.decode('utf-8')

                    # Call user callback
                    success = callback(message_str, method.delivery_tag)

                    # ACK or NACK based on callback result
                    if success:
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                        self.logger.debug(f"ACK message from {queue}")
                    else:
                        # Requeue on failure
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                        self.logger.warning(f"NACK message from {queue} (requeued)")

                except Exception as e:
                    self.logger.error(f"Error processing message: {e}")
                    # NACK and requeue on error
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

            consumer_tag = self.channel.basic_consume(
                queue=queue,
                on_message_callback=wrapped_callback,
                auto_ack=False  # Manual ACK
            )

            self._consumers[queue] = consumer_tag
            self.logger.info(f"Consuming from queue: {queue} (prefetch={prefetch_count})")
            self.channel.start_consuming()

        except Exception as e:
            self.logger.error(f"Failed to consume messages: {e}")

    def stop_consuming(self, queue: Optional[str] = None):
        """Stop consuming from queue(s)"""
        if not self.channel:
            return

        try:
            if queue and queue in self._consumers:
                self.channel.basic_cancel(self._consumers[queue])
                del self._consumers[queue]
                self.logger.info(f"Stopped consuming from {queue}")
            else:
                self.channel.stop_consuming()
                self._consumers.clear()
                self.logger.info("Stopped all consumers")
        except Exception as e:
            self.logger.error(f"Failed to stop consuming: {e}")

    def get_queue_size(self, queue: str) -> int:
        """Get number of messages in queue"""
        if not self.channel:
            return 0

        try:
            method = self.channel.queue_declare(queue=queue, durable=True, passive=True)
            return method.method.message_count
        except Exception as e:
            self.logger.error(f"Failed to get queue size: {e}")
            return 0

    def purge_queue(self, queue: str) -> bool:
        """Remove all messages from queue"""
        if not self.channel:
            return False

        try:
            self.channel.queue_purge(queue=queue)
            self.logger.info(f"Purged queue: {queue}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to purge queue: {e}")
            return False

    def is_connected(self) -> bool:
        """Check if connected to RabbitMQ"""
        return self._is_connected and self.connection and self.connection.is_open

    def close(self):
        """Close connection"""
        try:
            self.stop_consuming()
            if self.connection and self.connection.is_open:
                self.connection.close()
                self.logger.info("Message queue connection closed")
            self._is_connected = False
        except Exception as e:
            self.logger.error(f"Error closing connection: {e}")
