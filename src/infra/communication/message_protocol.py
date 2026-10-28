"""
Message Protocol for Multi-Agent Communication
Defines the message format and serialization for agent communication
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import json
import uuid


class MessageType(str, Enum):
    """Message types for agent communication"""
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    AGENT_STATUS = "agent_status"
    COORDINATION = "coordination"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class MessagePriority(int, Enum):
    """Message priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class AgentMessage(BaseModel):
    """Base message format for agent communication"""

    # Message metadata
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message_type: MessageType
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Sender and receiver
    sender_id: str
    receiver_id: Optional[str] = None  # None for broadcast

    # Message content
    payload: Dict[str, Any]

    # Correlation (for request-response pattern)
    correlation_id: Optional[str] = None  # Link responses to requests
    reply_to: Optional[str] = None  # Queue name for reply

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def to_json(self) -> str:
        """Serialize message to JSON"""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> 'AgentMessage':
        """Deserialize message from JSON"""
        return cls.model_validate_json(json_str)

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentMessage':
        """Create message from dictionary"""
        return cls.model_validate(data)


class TaskRequest(BaseModel):
    """Task request payload"""
    task_id: str
    task_type: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    required_role: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    timeout: Optional[int] = None  # seconds


class TaskResponse(BaseModel):
    """Task response payload"""
    task_id: str
    status: str  # success, failed, partial
    result: Any
    error: Optional[str] = None
    execution_time: float  # seconds
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentStatus(BaseModel):
    """Agent status payload"""
    agent_id: str
    status: str  # idle, busy, error, offline
    current_tasks: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    load: float = 0.0  # 0.0 to 1.0


class MessageBuilder:
    """Builder for constructing messages"""

    @staticmethod
    def create_task_request(
        sender_id: str,
        receiver_id: str,
        task_id: str,
        task_type: str,
        description: str,
        parameters: Optional[Dict[str, Any]] = None,
        priority: MessagePriority = MessagePriority.NORMAL,
        **kwargs
    ) -> AgentMessage:
        """Create a task request message"""
        task_request = TaskRequest(
            task_id=task_id,
            task_type=task_type,
            description=description,
            parameters=parameters or {},
            **{k: v for k, v in kwargs.items() if k in TaskRequest.model_fields}
        )

        return AgentMessage(
            message_type=MessageType.TASK_REQUEST,
            priority=priority,
            sender_id=sender_id,
            receiver_id=receiver_id,
            payload=task_request.model_dump(),
            correlation_id=task_id
        )

    @staticmethod
    def create_task_response(
        sender_id: str,
        receiver_id: str,
        task_id: str,
        status: str,
        result: Any,
        execution_time: float,
        error: Optional[str] = None,
        correlation_id: Optional[str] = None,
        **kwargs
    ) -> AgentMessage:
        """Create a task response message"""
        task_response = TaskResponse(
            task_id=task_id,
            status=status,
            result=result,
            error=error,
            execution_time=execution_time,
            **{k: v for k, v in kwargs.items() if k in TaskResponse.model_fields}
        )

        return AgentMessage(
            message_type=MessageType.TASK_RESPONSE,
            priority=MessagePriority.NORMAL,
            sender_id=sender_id,
            receiver_id=receiver_id,
            payload=task_response.model_dump(),
            correlation_id=correlation_id or task_id
        )

    @staticmethod
    def create_agent_status(
        agent_id: str,
        status: str,
        current_tasks: Optional[List[str]] = None,
        capabilities: Optional[List[str]] = None,
        load: float = 0.0
    ) -> AgentMessage:
        """Create an agent status message"""
        agent_status = AgentStatus(
            agent_id=agent_id,
            status=status,
            current_tasks=current_tasks or [],
            capabilities=capabilities or [],
            load=load
        )

        return AgentMessage(
            message_type=MessageType.AGENT_STATUS,
            priority=MessagePriority.LOW,
            sender_id=agent_id,
            payload=agent_status.model_dump()
        )

    @staticmethod
    def create_heartbeat(agent_id: str) -> AgentMessage:
        """Create a heartbeat message"""
        return AgentMessage(
            message_type=MessageType.HEARTBEAT,
            priority=MessagePriority.LOW,
            sender_id=agent_id,
            payload={"timestamp": datetime.utcnow().isoformat()}
        )

    @staticmethod
    def create_error(
        sender_id: str,
        error_message: str,
        error_code: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> AgentMessage:
        """Create an error message"""
        return AgentMessage(
            message_type=MessageType.ERROR,
            priority=MessagePriority.HIGH,
            sender_id=sender_id,
            payload={
                "error_message": error_message,
                "error_code": error_code
            },
            correlation_id=correlation_id
        )
