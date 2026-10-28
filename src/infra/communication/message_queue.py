"""Message Queue for Agent Communication"""
import logging
import pika
from typing import Callable, Dict

logger = logging.getLogger(__name__)


class MessageQueue:
    """RabbitMQ wrapper for agent communication"""

    def __init__(self, host: str = 'localhost', port: int = 5672):
        self.host = host
        self.port = port
        self.connection = None
        self.channel = None
        self.logger = logging.getLogger("MessageQueue")

    def connect(self):
        """Connect to RabbitMQ"""
        try:
            credentials = pika.PlainCredentials('admin', 'admin123')
            parameters = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                credentials=credentials
            )
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            self.logger.info(f"Connected to RabbitMQ at {self.host}:{self.port}")

        except Exception as e:
            self.logger.error(f"Failed to connect to RabbitMQ: {e}")
            # Graceful degradation - system can work without MQ
            self.logger.warning("Running without message queue")

    def publish(self, queue: str, message: str):
        """Publish message to queue"""
        if not self.channel:
            self.logger.warning("Message queue not connected, skipping publish")
            return

        try:
            self.channel.queue_declare(queue=queue, durable=True)
            self.channel.basic_publish(
                exchange='',
                routing_key=queue,
                body=message,
                properties=pika.BasicProperties(delivery_mode=2)  # Persistent
            )
            self.logger.debug(f"Published to {queue}: {message[:50]}...")

        except Exception as e:
            self.logger.error(f"Failed to publish message: {e}")

    def consume(self, queue: str, callback: Callable):
        """Consume messages from queue"""
        if not self.channel:
            self.logger.warning("Message queue not connected, skipping consume")
            return

        try:
            self.channel.queue_declare(queue=queue, durable=True)
            self.channel.basic_consume(
                queue=queue,
                on_message_callback=callback,
                auto_ack=False
            )
            self.logger.info(f"Consuming from queue: {queue}")
            self.channel.start_consuming()

        except Exception as e:
            self.logger.error(f"Failed to consume messages: {e}")

    def close(self):
        """Close connection"""
        if self.connection:
            self.connection.close()
            self.logger.info("Message queue connection closed")
