"""
Test Multi-Agent Message Communication
Tests the message protocol and RabbitMQ integration
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from dotenv import load_dotenv
load_dotenv()

import time
from infra.communication.message_protocol import (
    MessageBuilder,
    MessageType,
    MessagePriority,
    AgentMessage
)
from infra.communication.message_queue import MessageQueue

def test_message_protocol():
    """Test message creation and serialization"""
    print("=" * 60)
    print("Test 1: Message Protocol")
    print("=" * 60)

    # Create a task request
    msg = MessageBuilder.create_task_request(
        sender_id="agent-1",
        receiver_id="agent-2",
        task_id="task-001",
        task_type="analysis",
        description="Analyze the multi-agent system architecture",
        parameters={"depth": "detailed"},
        priority=MessagePriority.HIGH
    )

    print(f"✓ Created message: {msg.message_id}")
    print(f"  Type: {msg.message_type}")
    print(f"  Priority: {msg.priority}")
    print(f"  Sender: {msg.sender_id} -> Receiver: {msg.receiver_id}")

    # Serialize to JSON
    json_str = msg.to_json()
    print(f"✓ Serialized to JSON ({len(json_str)} bytes)")

    # Deserialize back
    msg_restored = AgentMessage.from_json(json_str)
    assert msg_restored.message_id == msg.message_id
    print(f"✓ Deserialized successfully")
    print()

def test_message_queue_connection():
    """Test RabbitMQ connection"""
    print("=" * 60)
    print("Test 2: RabbitMQ Connection")
    print("=" * 60)

    mq = MessageQueue()
    mq.connect()

    if mq.is_connected():
        print(f"✓ Connected to RabbitMQ at {mq.host}:{mq.port}")
    else:
        print("✗ Failed to connect to RabbitMQ")
        return None

    print()
    return mq

def test_publish_messages(mq: MessageQueue):
    """Test publishing messages with different priorities"""
    print("=" * 60)
    print("Test 3: Publish Messages")
    print("=" * 60)

    queue_name = "test_agent_tasks"

    # Purge queue first
    mq.purge_queue(queue_name)

    # Create messages with different priorities
    messages = [
        MessageBuilder.create_task_request(
            sender_id="coordinator",
            receiver_id="worker-1",
            task_id="task-low",
            task_type="backup",
            description="Low priority background task",
            priority=MessagePriority.LOW
        ),
        MessageBuilder.create_task_request(
            sender_id="coordinator",
            receiver_id="worker-1",
            task_id="task-normal",
            task_type="process",
            description="Normal priority task",
            priority=MessagePriority.NORMAL
        ),
        MessageBuilder.create_task_request(
            sender_id="coordinator",
            receiver_id="worker-1",
            task_id="task-urgent",
            task_type="alert",
            description="Urgent priority task",
            priority=MessagePriority.URGENT
        ),
    ]

    # Publish messages
    for msg in messages:
        success = mq.publish_message(queue_name, msg)
        if success:
            print(f"✓ Published: {msg.payload['task_id']} (priority={msg.priority.name})")
        else:
            print(f"✗ Failed to publish: {msg.payload['task_id']}")

    # Check queue size
    size = mq.get_queue_size(queue_name)
    print(f"\n✓ Queue '{queue_name}' size: {size} messages")
    print()

def test_consume_messages(mq: MessageQueue):
    """Test consuming messages (they should be ordered by priority)"""
    print("=" * 60)
    print("Test 4: Consume Messages (Priority Order)")
    print("=" * 60)

    queue_name = "test_agent_tasks"
    messages_received = []

    def callback(message_str: str, delivery_tag: int) -> bool:
        """Callback to process messages"""
        try:
            msg = AgentMessage.from_json(message_str)
            task_id = msg.payload['task_id']
            priority = msg.priority.name

            print(f"✓ Received: {task_id} (priority={priority})")
            messages_received.append(task_id)

            # Stop after receiving all 3 messages
            if len(messages_received) >= 3:
                mq.stop_consuming(queue_name)

            return True  # ACK the message
        except Exception as e:
            print(f"✗ Error processing message: {e}")
            return False  # NACK and requeue

    # Consume messages
    try:
        mq.consume(queue_name, callback, prefetch_count=1)
    except KeyboardInterrupt:
        pass

    print(f"\n✓ Received {len(messages_received)} messages")
    print(f"  Order: {' -> '.join(messages_received)}")
    print(f"  Expected: task-urgent -> task-normal -> task-low")
    print()

def test_agent_status_messages(mq: MessageQueue):
    """Test agent status broadcasting"""
    print("=" * 60)
    print("Test 5: Agent Status Messages")
    print("=" * 60)

    queue_name = "agent_status"

    # Create status message
    status_msg = MessageBuilder.create_agent_status(
        agent_id="worker-1",
        status="busy",
        current_tasks=["task-001", "task-002"],
        capabilities=["analysis", "planning"],
        load=0.75
    )

    success = mq.publish_message(queue_name, status_msg)
    if success:
        print(f"✓ Published status: agent={status_msg.sender_id}, status={status_msg.payload['status']}")
        print(f"  Current tasks: {status_msg.payload['current_tasks']}")
        print(f"  Load: {status_msg.payload['load']*100}%")

    print()

def main():
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "Multi-Agent Communication Test" + " " * 18 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    # Test 1: Message Protocol
    test_message_protocol()

    # Test 2: Connect to RabbitMQ
    mq = test_message_queue_connection()
    if not mq:
        print("\n✗ Cannot continue without RabbitMQ connection")
        print("  Make sure RabbitMQ is running: docker-compose ps")
        return

    try:
        # Test 3: Publish messages
        test_publish_messages(mq)

        # Test 4: Consume messages (priority order)
        test_consume_messages(mq)

        # Test 5: Agent status
        test_agent_status_messages(mq)

    finally:
        # Cleanup
        mq.close()

    print("=" * 60)
    print("✓ All tests completed!")
    print("=" * 60)
    print()

if __name__ == '__main__':
    main()
