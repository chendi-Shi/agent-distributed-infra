"""
Multi-Agent with Distributed Infrastructure
Main entry point
"""
import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.multi_agent import MultiAgentSystem
from infra.inference.router import ModelRouter
from infra.communication.message_queue import MessageQueue
from infra.storage.vector_store import VectorStore
from orchestration.workflow import WorkflowEngine

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Main execution loop."""
    logger.info("=" * 60)
    logger.info("Agent Distributed Infrastructure Starting")
    logger.info("=" * 60)

    # Validate configuration
    if not os.getenv('DEEPSEEK_API_KEY'):
        logger.error("DEEPSEEK_API_KEY not found in environment")
        sys.exit(1)

    # Initialize infrastructure components
    logger.info("Initializing infrastructure...")

    # Model router for intelligent inference routing
    router = ModelRouter(
        primary_model=os.getenv('PRIMARY_MODEL', 'deepseek-chat'),
        enable_caching=True
    )

    # Message queue for agent communication
    message_queue = MessageQueue(
        host=os.getenv('RABBITMQ_HOST', 'localhost'),
        port=int(os.getenv('RABBITMQ_PORT', 5672))
    )

    # Vector store for RAG
    vector_store = VectorStore(
        host=os.getenv('MILVUS_HOST', 'localhost'),
        port=int(os.getenv('MILVUS_PORT', 19530))
    )

    # Workflow engine for orchestration
    workflow_engine = WorkflowEngine(
        router=router,
        message_queue=message_queue,
        vector_store=vector_store
    )

    # Initialize multi-agent system
    multi_agent_system = MultiAgentSystem(
        workflow_engine=workflow_engine,
        max_agents=int(os.getenv('MAX_AGENTS', 10))
    )

    logger.info("Infrastructure initialized successfully")
    logger.info(f"Model: {os.getenv('PRIMARY_MODEL')}")
    logger.info(f"Max Agents: {os.getenv('MAX_AGENTS')}")

    # Start the system
    logger.info("\nStarting multi-agent system...")
    logger.info("Press Ctrl+C to stop\n")

    try:
        await multi_agent_system.run()
    except KeyboardInterrupt:
        logger.info("\nShutting down gracefully...")
        await multi_agent_system.shutdown()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

    logger.info("System stopped")


if __name__ == '__main__':
    asyncio.run(main())
