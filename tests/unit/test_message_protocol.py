"""
Unit tests for message protocol
Tests message creation, serialization, and validation
"""
import pytest
import json
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from infra.communication.message_protocol import (
    MessageType,
    MessagePriority,
    AgentMessage,
    MessageBuilder,
    TaskRequest,
    TaskResponse,
    AgentStatus
)


class TestMessageTypes:
    """Test message type enums"""

    def test_message_types_exist(self):
        """Test all message types are defined"""
        assert MessageType.TASK_REQUEST == "task_request"
        assert MessageType.TASK_RESPONSE == "task_response"
        assert MessageType.AGENT_STATUS == "agent_status"
        assert MessageType.ERROR == "error"
        assert MessageType.HEARTBEAT == "heartbeat"

    def test_message_priorities_exist(self):
        """Test all priority levels are defined"""
        assert MessagePriority.LOW == 1
        assert MessagePriority.NORMAL == 2
        assert MessagePriority.HIGH == 3
        assert MessagePriority.URGENT == 4


class TestAgentMessage:
    """Test AgentMessage creation and serialization"""

    def test_create_basic_message(self):
        """Test creating a basic message"""
        msg = AgentMessage(
            message_type=MessageType.HEARTBEAT,
            sender_id="agent-1",
            payload={"status": "alive"}
        )

        assert msg.message_type == MessageType.HEARTBEAT
        assert msg.sender_id == "agent-1"
        assert msg.priority == MessagePriority.NORMAL  # Default
        assert msg.payload == {"status": "alive"}
        assert msg.message_id is not None
        assert isinstance(msg.timestamp, datetime)

    def test_message_serialization(self):
        """Test JSON serialization and deserialization"""
        original = AgentMessage(
            message_type=MessageType.TASK_REQUEST,
            sender_id="coordinator",
            receiver_id="worker-1",
            payload={"task_id": "task-001", "description": "Test task"},
            priority=MessagePriority.HIGH
        )

        # Serialize
        json_str = original.to_json()
        assert isinstance(json_str, str)

        # Deserialize
        restored = AgentMessage.from_json(json_str)
        assert restored.message_id == original.message_id
        assert restored.message_type == original.message_type
        assert restored.sender_id == original.sender_id
        assert restored.receiver_id == original.receiver_id
        assert restored.priority == original.priority
        assert restored.payload == original.payload

    def test_message_to_dict(self):
        """Test converting message to dictionary"""
        msg = AgentMessage(
            message_type=MessageType.ERROR,
            sender_id="agent-1",
            payload={"error": "Something went wrong"}
        )

        msg_dict = msg.to_dict()
        assert isinstance(msg_dict, dict)
        assert msg_dict["message_type"] == "error"
        assert msg_dict["sender_id"] == "agent-1"

    def test_message_correlation(self):
        """Test message correlation for request-response"""
        request = AgentMessage(
            message_type=MessageType.TASK_REQUEST,
            sender_id="coordinator",
            receiver_id="worker",
            payload={},
            correlation_id="req-123"
        )

        assert request.correlation_id == "req-123"


class TestMessageBuilder:
    """Test MessageBuilder helper methods"""

    def test_create_task_request(self):
        """Test creating task request"""
        msg = MessageBuilder.create_task_request(
            sender_id="coordinator",
            receiver_id="worker-1",
            task_id="task-001",
            task_type="analysis",
            description="Analyze the system",
            parameters={"depth": "detailed"},
            priority=MessagePriority.HIGH
        )

        assert msg.message_type == MessageType.TASK_REQUEST
        assert msg.sender_id == "coordinator"
        assert msg.receiver_id == "worker-1"
        assert msg.priority == MessagePriority.HIGH
        assert msg.payload["task_id"] == "task-001"
        assert msg.payload["task_type"] == "analysis"
        assert msg.payload["description"] == "Analyze the system"
        assert msg.payload["parameters"]["depth"] == "detailed"

    def test_create_task_response(self):
        """Test creating task response"""
        msg = MessageBuilder.create_task_response(
            sender_id="worker-1",
            receiver_id="coordinator",
            task_id="task-001",
            status="success",
            result="Analysis complete",
            execution_time=5.2
        )

        assert msg.message_type == MessageType.TASK_RESPONSE
        assert msg.payload["task_id"] == "task-001"
        assert msg.payload["status"] == "success"
        assert msg.payload["result"] == "Analysis complete"
        assert msg.payload["execution_time"] == 5.2

    def test_create_agent_status(self):
        """Test creating agent status"""
        msg = MessageBuilder.create_agent_status(
            agent_id="worker-1",
            status="busy",
            current_tasks=["task-001", "task-002"],
            capabilities=["analysis", "planning"],
            load=0.75
        )

        assert msg.message_type == MessageType.AGENT_STATUS
        assert msg.sender_id == "worker-1"
        assert msg.payload["status"] == "busy"
        assert msg.payload["current_tasks"] == ["task-001", "task-002"]
        assert msg.payload["load"] == 0.75

    def test_create_heartbeat(self):
        """Test creating heartbeat"""
        msg = MessageBuilder.create_heartbeat("agent-1")

        assert msg.message_type == MessageType.HEARTBEAT
        assert msg.sender_id == "agent-1"
        assert msg.priority == MessagePriority.LOW
        assert "timestamp" in msg.payload

    def test_create_error(self):
        """Test creating error message"""
        msg = MessageBuilder.create_error(
            sender_id="worker-1",
            error_message="Task failed",
            error_code="E001",
            correlation_id="req-123"
        )

        assert msg.message_type == MessageType.ERROR
        assert msg.priority == MessagePriority.HIGH
        assert msg.payload["error_message"] == "Task failed"
        assert msg.payload["error_code"] == "E001"
        assert msg.correlation_id == "req-123"


class TestTaskModels:
    """Test Task-related Pydantic models"""

    def test_task_request_model(self):
        """Test TaskRequest model"""
        task = TaskRequest(
            task_id="task-001",
            task_type="analysis",
            description="Analyze data",
            parameters={"format": "json"},
            required_role="worker",
            dependencies=["task-000"],
            timeout=300
        )

        assert task.task_id == "task-001"
        assert task.task_type == "analysis"
        assert task.parameters["format"] == "json"
        assert task.timeout == 300

    def test_task_response_model(self):
        """Test TaskResponse model"""
        response = TaskResponse(
            task_id="task-001",
            status="success",
            result={"data": [1, 2, 3]},
            execution_time=2.5
        )

        assert response.task_id == "task-001"
        assert response.status == "success"
        assert response.result == {"data": [1, 2, 3]}
        assert response.error is None

    def test_agent_status_model(self):
        """Test AgentStatus model"""
        status = AgentStatus(
            agent_id="worker-1",
            status="idle",
            current_tasks=[],
            capabilities=["worker"],
            load=0.0
        )

        assert status.agent_id == "worker-1"
        assert status.status == "idle"
        assert len(status.current_tasks) == 0
        assert status.load == 0.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
