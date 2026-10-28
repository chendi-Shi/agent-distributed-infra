# Agent Distributed Infrastructure

Multi-Agent System with Distributed Inference Engine and Communication Infrastructure

## Project Overview

A production-grade multi-agent platform combining:
- **Distributed Inference**: vLLM + Ray for high-performance model serving
- **Agent Communication**: RabbitMQ + Redis for async messaging and state management
- **Multi-Agent Orchestration**: Task decomposition, role assignment, result aggregation
- **Context Optimization**: Compression, summarization, sliding window strategies

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Layer                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ Planner  │  │ Worker 1 │  │ Worker 2 │             │
│  │  Agent   │  │  Agent   │  │  Agent   │             │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘             │
└────────┼─────────────┼─────────────┼───────────────────┘
         │             │             │
┌────────┼─────────────┼─────────────┼───────────────────┐
│        │    Communication & Orchestration Layer         │
│  ┌──────────────────────────────────────┐              │
│  │    Message Queue (RabbitMQ)          │              │
│  └──────────────────────────────────────┘              │
│  ┌──────────────────────────────────────┐              │
│  │    Workflow Engine (Custom)          │              │
│  └──────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────┘
         │
┌────────┼────────────────────────────────────────────────┐
│        │      Inference Engine Layer                     │
│  ┌──────────────────────────────────────┐              │
│  │    Model Router & Load Balancer      │              │
│  │  ┌────────┐  ┌────────┐  ┌────────┐ │              │
│  │  │GPT-4   │  │Router  │  │Compress│ │              │
│  │  │(API)   │  │Model   │  │Model   │ │              │
│  │  └────────┘  └────────┘  └────────┘ │              │
│  └──────────────────────────────────────┘              │
│  ┌──────────────────────────────────────┐              │
│  │    Ray Cluster (Distributed)         │              │
│  └──────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────┘
         │
┌────────┼────────────────────────────────────────────────┐
│        │      Storage Layer                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │  Redis   │  │  Milvus  │  │ Postgres │             │
│  │  Cache   │  │  Vector  │  │  State   │             │
│  └──────────┘  └──────────┘  └──────────┘             │
└─────────────────────────────────────────────────────────┘
```

## Key Features

### 1. Distributed Inference
- **vLLM Integration**: High-throughput model serving with continuous batching
- **Multi-Model Support**: Large models (GPT-4) + small models (Router, Compressor)
- **Ray Cluster**: Distributed compute for parallel agent execution
- **Smart Routing**: Trained router decides: cache / small model / large model

### 2. Agent Communication
- **Async Messaging**: RabbitMQ for inter-agent communication
- **State Management**: Redis for shared state and distributed locks
- **Task Queue**: Priority-based task distribution
- **Result Aggregation**: Collect and merge multi-agent outputs

### 3. Multi-Agent Orchestration
- **Task Decomposition**: Break complex tasks into subtasks
- **Role Assignment**: Planner, Worker, Reviewer agents
- **Dynamic Scheduling**: Optimize agent allocation based on load
- **Fault Tolerance**: Retry and fallback mechanisms

### 4. Context Optimization
- **Sliding Window**: Maintain relevant context within token limits
- **Summarization**: Compress long conversations
- **Key Extraction**: Identify and preserve critical information
- **Memory Management**: Short-term + long-term memory

## Tech Stack

### Infrastructure
- **Ray**: Distributed computing framework
- **RabbitMQ**: Message broker for agent communication
- **Redis**: Cache and state management
- **Milvus**: Vector database for RAG
- **PostgreSQL**: Persistent storage for agent state

### Agent Framework
- **LangGraph**: Agent workflow orchestration
- **LangChain**: Tool integration and memory management
- **DeepSeek**: Primary LLM backend

### Monitoring
- **Prometheus**: Metrics collection
- **Grafana**: Visualization dashboards
- **OpenTelemetry**: Distributed tracing

## Training Objectives (Phase 2-3)

### 1. Router Model
- **Input**: Task description, current load, available models
- **Output**: Route decision (cache / small model / large model)
- **Training**: Reinforcement learning with cost-latency-quality tradeoff

### 2. Context Compressor
- **Input**: Long conversation history
- **Output**: Compressed summary preserving key information
- **Training**: Seq2Seq with attention, target 50%+ compression

### 3. Task Decomposer
- **Input**: Complex task description
- **Output**: Subtask breakdown with dependencies
- **Training**: Supervised learning on human-annotated decompositions

### 4. Scheduler Optimizer
- **Input**: Available agents, task queue, resource state
- **Output**: Task assignment and execution order
- **Training**: RL with multi-objective optimization (throughput + latency)

## Project Phases

### Phase 1: Infrastructure Setup (Week 1-2)
- [x] Project structure
- [ ] Docker Compose environment
- [ ] Ray cluster setup
- [ ] RabbitMQ + Redis deployment
- [ ] Milvus vector database
- [ ] Basic agent framework

### Phase 2: Agent Implementation (Week 3-4)
- [ ] Single agent with context management
- [ ] Multi-agent communication protocol
- [ ] Task decomposition logic
- [ ] Workflow orchestration
- [ ] Data collection pipeline

### Phase 3: Model Training (Week 5-6)
- [ ] Collect training data (500+ samples)
- [ ] Train Router model (4090)
- [ ] Train Compressor model (4090)
- [ ] Train Task Decomposer
- [ ] Integration testing

### Phase 4: Optimization & Evaluation (Week 7-8)
- [ ] Benchmark suite
- [ ] Performance optimization
- [ ] Cost analysis
- [ ] Documentation
- [ ] Paper writing

## Budget Estimate

- **Infrastructure**: ¥0 (local Docker)
- **API Calls (Phase 2)**: ¥100-200
- **GPU Training (Phase 3)**: ¥600-1000 (4090 rental)
- **Testing & Evaluation**: ¥100-200
- **Total**: ¥800-1400

## Research Contributions

1. **Distributed inference optimization** for multi-agent systems
2. **Context compression** techniques for long conversations
3. **Multi-agent task decomposition** strategies
4. **Resource scheduling** algorithms for heterogeneous models

## Getting Started

```bash
# Install dependencies
pip install -r requirements.txt

# Start infrastructure
docker-compose up -d

# Run example
python examples/simple_multi_agent.py

# Monitor
open http://localhost:3000  # Grafana
open http://localhost:15672 # RabbitMQ UI
```

## Documentation

- [Architecture Design](docs/architecture.md)
- [Agent Development Guide](docs/agent_guide.md)
- [Training Pipeline](docs/training.md)
- [API Reference](docs/api.md)

## License

MIT
