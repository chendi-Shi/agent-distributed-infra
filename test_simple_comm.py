"""
Simple Multi-Agent Communication Test
Tests basic message publishing and consuming
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from dotenv import load_dotenv
load_dotenv()

import time
from infra.communication.message_protocol import (
    MessageBuilder,
    MessagePriority,
    AgentMessage
)
from infra.communication.message_queue import MessageQueue

def main():
    print("\n╔" + "=" * 58 + "╗")
    print("║  Multi-Agent Communication - Simple Test" + " " * 16 + "║")
    print("╚" + "=" * 58 + "╝\n")

    # Connect to RabbitMQ
    print("Connecting to RabbitMQ...")
    mq = MessageQueue()
    mq.connect()

    if not mq.is_connected():
        print("✗ Failed to connect to RabbitMQ")
        return

    print(f"✓ Connected to {mq.host}:{mq.port}\n")

    # Create test queue
    queue_name = "agent_tasks"
    print(f"Creating queue: {queue_name}")
    mq.declare_queue(queue_name, priority=True)
    print(f"✓ Queue declared\n")

    # Publish messages
    print("Publishing messages...")
    messages = [
        ("urgent", MessagePriority.URGENT, "Handle critical system alert"),
        ("normal", MessagePriority.NORMAL, "Process user request"),
        ("low", MessagePriority.LOW, "Background cleanup task"),
    ]

    for task_id, priority, description in messages:
        msg = MessageBuilder.create_task_request(
            sender_id="coordinator",
            receiver_id="worker-1",
            task_id=f"task-{task_id}",
            task_type="process",
            description=description,
            priority=priority
        )

        success = mq.publish_message(queue_name, msg)
        status = "✓" if success else "✗"
        print(f"  {status} {task_id.upper()}: {description}")

    # Check queue
    size = mq.get_queue_size(queue_name)
    print(f"\n✓ Queue size: {size} messages\n")

    # Consume messages
    print("Consuming messages (highest priority first)...")
    received = []

    def callback(message_str: str, delivery_tag: int) -> bool:
        msg = AgentMessage.from_json(message_str)
        task_id = msg.payload['task_id']
        priority = msg.priority.name
        description = msg.payload['description']

        print(f"  ✓ Received: {task_id} [{priority}]")
        print(f"    → {description}")

        received.append((task_id, priority))

        # Stop after 3 messages
        if len(received) >= 3:
            mq.stop_consuming()

        return True

    try:
        mq.consume(queue_name, callback, prefetch_count=1)
    except KeyboardInterrupt:
        pass

    # Summary
    print(f"\n" + "=" * 60)
    print(f"✓ Test completed!")
    print(f"  Messages published: 3")
    print(f"  Messages received: {len(received)}")
    print(f"  Order: {' → '.join([t[0] for t in received])}")
    print("=" * 60 + "\n")

    mq.close()

if __name__ == '__main__':
    main()
