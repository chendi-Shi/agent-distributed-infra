# 完整技术路线：Agent + 分布式推理基础设施

> **核心理念**：Agent 执行闭环 → 多 Agent 协作策略 → 实验评测 → 基于轨迹训练策略  
> **同时体现**：开发能力 + 算法能力 + 工程能力

---

## 🎯 整体架构

```
用户任务
   ↓
【策略层】Task Decomposer (4090 小模型) → 分解成子任务
   ↓
【策略层】Tool Selector (4090 小模型) → 为每个子任务选工具
   ↓
【执行层】Multi-Agent Orchestrator + DeepSeek API → 并行执行
   ↓
【数据层】Trajectory Collector → 存储完整执行轨迹
   ↓
【训练层】4090 训练小模型 → 更新 Decomposer/Selector/Router
   ↓
【验证层】性能提升 (成本降低、速度加快、成功率提高)
```

**基础设施（Infra）贯穿全程：**
- 消息队列（RabbitMQ）- 任务分发
- 状态存储（PostgreSQL + Redis）- 轨迹持久化
- 监控系统（Prometheus + Grafana）- 性能追踪

---

## 📅 完整开发计划（8 周）

### Phase 1: 基础设施搭建（Week 1-2）✅ 85%

**目标**：构建 Multi-Agent 协作基础设施

**已完成：**
- ✅ Docker 基础设施（Redis, RabbitMQ, PostgreSQL）
- ✅ 消息通信协议（优先级队列、消息序列化）
- ✅ 工作流 DAG 引擎（并行执行、依赖管理）
- ✅ Agent Worker（任务消费、角色分工）
- ✅ Redis 缓存集成（Router 持久化）
- ✅ 单元测试（32 个测试，100% 通过）
- ✅ Prometheus 监控系统
- ✅ Grafana 仪表盘（10 个监控面板）

**输出：**
- 分布式 Agent 基础设施
- 监控系统（实时性能追踪）

---

### Phase 2: 轨迹收集 + 人工标注（Week 3-4）

**目标**：收集真实执行轨迹，通过主动学习 + 人工标注构建高质量训练数据

#### 2.1 轨迹收集（自动化）

**方式**：运行 Multi-Agent 系统处理真实任务，记录完整执行过程

```bash
# 收集 100 条轨迹（Multi-Agent 模式）
python scripts/collect_trajectories.py --num_tasks 100 --modes multi_agent
```

**收集内容**：
- 任务描述和参数
- 任务分解结果（Planner 输出的子任务列表）
- 工具调用序列（每个工具的输入/输出/耗时）
- 中间状态和最终结果
- 性能指标（执行时间、API 调用数、Token 消耗）

**目标数据量**：200-300 条轨迹（覆盖 4 种任务类型）

---

#### 2.2 主动学习样本选择 ⭐ 关键创新

**问题**：不是所有轨迹都值得标注，如何选出最有价值的样本？

**解决方案**：主动学习（Active Learning）

```python
# src/monitoring/active_learning.py

class ActiveLearningSampler:
    def select_samples(self, trajectories, budget=50):
        """
        混合策略：
        1. 不确定性采样：任务复杂度异常、耗时难预测
        2. 多样性采样：TF-IDF 聚类，每簇选代表
        3. 边界案例：部分成功的轨迹
        """
```

**优势**：
- 只需标注 50-80 条（而非全部 300 条）
- 选出的样本信息量最大
- 减少标注工作量 60-70%

---

#### 2.3 人工标注 ⭐ 核心数据来源

**标注界面**：简单的 Web UI（Flask）

```bash
# 启动标注界面
python scripts/annotation_ui.py

# 访问 http://localhost:5000
```

**标注内容**：

| 维度 | 标注项 | 用途 |
|------|--------|------|
| **任务分解** | 质量评分（1-5）<br>改进建议<br>修正后的子任务列表 | 训练 Task Decomposer |
| **工具选择** | 每个子任务的最优工具<br>选择理由 | 训练 Tool Selector |
| **优先级** | 子任务的正确排序 | 优化调度策略 |
| **整体** | 质量评分（1-5）<br>备注 | 数据清洗过滤 |

**标注工作量**：
- **第一轮**：50-80 条 × 3 分钟 = 2.5-4 小时
- **第二轮**（训练后主动学习）：20-30 条 × 3 分钟 = 1-1.5 小时
- **总计**：70-110 条，3.5-5.5 小时

**示例标注流程**：
```
任务描述：设计一个支持 100 万 QPS 的分布式缓存系统

系统分解（5 个子任务）：
1. 分析需求和规模
2. 设计架构
3. 选择技术栈
4. 设计一致性协议
5. 编写文档

你的标注：
- 分解质量：4/5
- 改进建议：缺少"容量规划和成本估算"这一步
- 工具选择：
  * 子任务 1 → web_search（查行业标准）
  * 子任务 2 → design_tool（架构图）
  * 子任务 3 → code_review（技术选型对比）
```

---

#### 2.4 训练数据生成

从标注数据自动生成训练集：

```python
# src/training/data_generator.py

def generate_decomposer_dataset(annotated_trajectories):
    """
    Input: 任务描述
    Output: 修正后的子任务列表（人工标注）
    
    示例：
    {
        "input": "设计一个分布式缓存系统",
        "output": [
            "分析系统需求和规模",
            "容量规划和成本估算",  # 人工添加
            "设计缓存架构（分层、分片）",
            "选择技术栈（Redis/Memcached）",
            "设计一致性协议",
            "编写部署文档"
        ]
    }
    """
```

**数据清洗**：
- 只保留质量评分 ≥ 3 的样本
- 去重相似任务
- 平衡不同任务类型

**输出格式**：Hugging Face `datasets` 兼容的 JSON Lines

```bash
data/
  training/
    decomposer_train.jsonl      # 50-80 样本
    tool_selector_train.jsonl   # 100-150 样本（每个子任务一条）
    router_train.jsonl          # 自动生成（基于执行时间）
```

---

### Phase 3: 4090 训练小模型（Week 5-6）

**目标**：在 4090 上训练策略模型，降低 API 成本

#### 3.1 训练环境配置

**硬件：**
- GPU: RTX 4090 (24GB)
- RAM: 32GB+
- Storage: 100GB SSD

**软件栈：**
```bash
# PyTorch + transformers + peft (LoRA)
torch==2.5.0
transformers==4.47.0
peft==0.14.0
bitsandbytes==0.45.0  # QLoRA 量化
datasets==3.2.0
accelerate==1.2.0
```

---

#### 3.2 基座模型选择

**候选模型（开源、4090 可训练）：**

| 模型 | 参数量 | 显存需求 | 推理速度 | 优势 |
|------|--------|----------|----------|------|
| **Qwen2.5-7B** | 7B | ~14GB (FP16) | 快 | 中文友好、性能强 |
| **Llama-3.1-8B** | 8B | ~16GB (FP16) | 快 | Meta 官方、生态好 |
| **DeepSeek-Coder-6.7B** | 6.7B | ~13GB (FP16) | 快 | 代码能力强 |

**推荐**：**Qwen2.5-7B**（中文任务、性能最优）

---

#### 3.3 训练方案

**方法：LoRA（Low-Rank Adaptation）**
- 只训练 0.1-1% 的参数（高效、省显存）
- 适合 4090（24GB 显存足够）

**训练超参数：**
```python
# scripts/train_decomposer.py
training_args = TrainingArguments(
    output_dir="./models/decomposer",
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,  # 等效 batch_size=16
    learning_rate=2e-4,
    fp16=True,  # 混合精度训练
    logging_steps=10,
    save_steps=100,
    warmup_steps=50,
)

lora_config = LoraConfig(
    r=16,  # LoRA rank
    lora_alpha=32,
    target_modules=["q_proj", "v_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)
```

**训练时间估算：**
- Decomposer (500 样本): ~30 分钟
- Tool Selector (1500 样本): ~1.5 小时
- Router (3000 样本): ~3 小时

**总成本**：~5 小时 GPU 时间（约 ¥50-100，如果租用云 GPU）

---

#### 3.4 三个小模型训练

##### 1️⃣ Task Decomposer（任务分解器）

**输入示例：**
```json
{
  "instruction": "将以下任务分解为 3-5 个可并行的子任务",
  "task": "设计一个分布式缓存系统，支持 1M QPS"
}
```

**输出示例：**
```json
{
  "subtasks": [
    "分析系统需求：1M QPS、数据规模、延迟要求",
    "设计缓存架构：分层（L1/L2）、分片策略",
    "选择技术栈：Redis Cluster vs Memcached",
    "设计一致性协议：CAP 权衡、数据同步",
    "编写部署文档：配置参数、监控指标"
  ]
}
```

**训练脚本：**
```bash
python scripts/train_decomposer.py \
  --base_model Qwen/Qwen2.5-7B \
  --data_path data/training/decomposer_train.jsonl \
  --output_dir models/decomposer \
  --epochs 3 \
  --batch_size 4
```

---

##### 2️⃣ Tool Selector（工具选择器）

**输入示例：**
```json
{
  "subtask": "分析代码中的安全漏洞",
  "available_tools": [
    "code_review - 人工审查代码",
    "static_analysis - 静态分析工具（快、覆盖全）",
    "web_search - 搜索已知漏洞",
    "llm_analyze - 大模型深度分析（慢、准确）"
  ]
}
```

**输出示例：**
```json
{
  "selected_tool": "static_analysis",
  "reason": "安全漏洞检测需要全面扫描，静态分析工具速度快且覆盖率高"
}
```

**训练脚本：**
```bash
python scripts/train_tool_selector.py \
  --base_model Qwen/Qwen2.5-7B \
  --data_path data/training/tool_selector_train.jsonl \
  --output_dir models/tool_selector \
  --epochs 3
```

---

##### 3️⃣ Router Model（路由决策器）

**输入示例：**
```json
{
  "query": "解释 Transformer 架构的自注意力机制",
  "length": 28,
  "has_question": false,
  "complexity_keywords": ["解释", "架构", "机制"]
}
```

**输出示例：**
```json
{
  "route": "large",
  "confidence": 0.92
}
```

**路由规则：**
- `cache`: 重复问题（检查缓存）
- `small`: 简单问题（< 100 token，事实查询）
- `large`: 复杂推理、代码生成、长文本

**训练脚本：**
```bash
python scripts/train_router.py \
  --base_model Qwen/Qwen2.5-7B \
  --data_path data/training/router_train.jsonl \
  --output_dir models/router \
  --epochs 3
```

---

#### 3.5 模型部署（本地 4090 推理）

**使用 vLLM 加速推理：**
```bash
# 启动 vLLM 服务
python -m vllm.entrypoints.openai.api_server \
  --model ./models/decomposer \
  --port 8000 \
  --gpu-memory-utilization 0.5  # 3 个模型共享 4090

# Tool Selector
python -m vllm.entrypoints.openai.api_server \
  --model ./models/tool_selector \
  --port 8001 \
  --gpu-memory-utilization 0.3

# Router
python -m vllm.entrypoints.openai.api_server \
  --model ./models/router \
  --port 8002 \
  --gpu-memory-utilization 0.2
```

**推理速度：**
- Decomposer: ~100 tokens/s
- Tool Selector: ~150 tokens/s
- Router: ~200 tokens/s

---

### Phase 4: 验证效果（Week 7-8）

**目标**：对比 Baseline vs Hybrid 模式

#### 4.1 实验设置

| 模式 | 描述 | 成本结构 |
|------|------|----------|
| **Baseline（纯 API）** | 所有任务都调用 DeepSeek API | 高 API 成本 |
| **Hybrid（小模型辅助）** | Decomposer/Tool Selector 用 4090，复杂推理用 API | 低 API 成本 + GPU 成本 |

**Hybrid 模式流程：**
```
用户任务
  ↓
【本地 4090】Task Decomposer → 分解子任务（~0.5s）
  ↓
【本地 4090】Tool Selector → 选择工具（~0.3s）
  ↓
【DeepSeek API】复杂推理（~2-5s）
  ↓
【本地 4090】结果聚合（~0.5s）
```

---

#### 4.2 对比指标

**1. 成功率（Task Success Rate）**
- Baseline: 85-90%
- Hybrid: 目标 90-95%（小模型提供更好的任务分解）

**2. 总执行时间**
- Baseline: 单次任务 5-10s
- Hybrid: 单次任务 3-7s（本地推理更快）

**3. API 成本**
- Baseline: 100% API 调用
- Hybrid: 减少 40-60% API 调用
  - Decomposer 和 Tool Selector 本地化
  - 只有复杂推理调用 API

**4. Token 消耗**
```
Baseline（单任务）:
  - Planner: 500 tokens (API)
  - Worker: 1000 tokens (API)
  - Reviewer: 300 tokens (API)
  - 总计: 1800 tokens ≈ ¥0.38

Hybrid（单任务）:
  - Decomposer: 200 tokens (本地 4090，免费)
  - Tool Selector: 100 tokens (本地 4090，免费)
  - 复杂推理: 800 tokens (API)
  - 总计: 800 tokens ≈ ¥0.17

节省: 55% 成本
```

---

#### 4.3 Benchmark 任务集

**测试任务类型（50 个任务）：**
1. **系统设计**（10 个）
   - 设计分布式缓存
   - 设计消息队列
   - 设计推荐系统

2. **代码审查**（15 个）
   - Python 项目安全审查
   - TypeScript 代码优化
   - SQL 查询性能分析

3. **数据分析**（10 个）
   - 用户行为分析
   - A/B 测试结果评估
   - 时间序列预测

4. **文档生成**（15 个）
   - API 文档生成
   - 技术方案设计文档
   - 项目 README

---

#### 4.4 最终对比报告

**输出内容：**

```markdown
# Agent 系统性能对比报告

## 1. 执行模式对比

| 模式 | 成功率 | 平均耗时 | API 调用 | Token 消耗 | 成本 |
|------|--------|----------|----------|------------|------|
| Single Agent | 82% | 8.2s | 1200 | 2100 | ¥0.44 |
| Fixed Pipeline | 88% | 6.5s | 900 | 1800 | ¥0.38 |
| Multi-Agent | 91% | 5.1s | 850 | 1700 | ¥0.36 |
| **Hybrid (小模型辅助)** | **94%** | **3.8s** | **400** | **800** | **¥0.17** |

## 2. 改进效果

vs Baseline (Multi-Agent):
- ✅ 成功率提升: +3%
- ✅ 速度提升: 25% 更快
- ✅ 成本降低: 53% 节省
- ✅ API 调用减少: 53%

## 3. 小模型贡献

- Task Decomposer: 提升任务分解质量，减少无效子任务
- Tool Selector: 更准确的工具选择，减少重试
- Router: 更智能的路由决策，提高缓存命中率

## 4. ROI 分析

训练成本: ¥100 (5h GPU)
单任务节省: ¥0.19
回本所需: 526 次调用
预期月调用: 10,000 次
月节省: ¥1,900
年度 ROI: 228x
```

---

## 🏗️ 项目结构（最终版）

```
agent-distributed-infra/
├── src/
│   ├── agents/                    # Agent 核心
│   │   ├── multi_agent.py         # Multi-Agent 协作
│   │   ├── agent_worker.py        # 任务消费者
│   │   └── agent_pool.py          # Agent 池管理
│   │
│   ├── infra/                     # 基础设施
│   │   ├── communication/
│   │   │   ├── message_protocol.py
│   │   │   └── message_queue.py   # RabbitMQ
│   │   ├── inference/
│   │   │   └── router.py          # 模型路由
│   │   └── storage/
│   │       ├── redis_cache.py     # Redis 缓存
│   │       └── postgres_store.py  # PostgreSQL
│   │
│   ├── orchestration/             # 工作流编排
│   │   ├── task_dag.py            # DAG 引擎
│   │   └── workflow.py            # 并行执行
│   │
│   ├── monitoring/                # 监控系统 ⭐
│   │   ├── metrics.py             # Prometheus 指标
│   │   ├── prometheus_server.py   # HTTP 服务
│   │   └── trajectory_collector.py  # 轨迹收集 ⭐ 新增
│   │
│   ├── experiments/               # 实验评测 ⭐
│   │   └── agent_comparison.py    # 对比框架
│   │
│   └── training/                  # 训练模块 ⭐ 新增
│       ├── data_generator.py      # 训练数据生成
│       ├── train_decomposer.py    # 任务分解器训练
│       ├── train_tool_selector.py # 工具选择器训练
│       └── train_router.py        # 路由器训练
│
├── data/                          # 数据目录 ⭐ 新增
│   ├── trajectories/              # 执行轨迹
│   │   └── 2026-10-29/
│   │       ├── single_agent_trajectories.jsonl
│   │       ├── fixed_pipeline_trajectories.jsonl
│   │       └── multi_agent_trajectories.jsonl
│   └── training/                  # 训练数据
│       ├── decomposer_train.jsonl
│       ├── tool_selector_train.jsonl
│       └── router_train.jsonl
│
├── models/                        # 训练好的模型 ⭐ 新增
│   ├── decomposer/
│   ├── tool_selector/
│   └── router/
│
├── infra/
│   ├── monitoring/
│   │   ├── prometheus.yml
│   │   ├── grafana-datasources.yaml
│   │   └── grafana-dashboard.json
│   └── docker-compose.simple.yaml
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── scripts/
│   ├── start_all.sh              # 一键启动所有服务
│   ├── collect_trajectories.py   # 收集轨迹脚本 ⭐ 新增
│   └── benchmark.py              # 性能测试 ⭐ 新增
│
├── docs/
│   ├── development-plan.md
│   ├── architecture.md
│   └── training-guide.md         # 训练指南 ⭐ 新增
│
├── requirements.txt
├── .env.example
└── README.md
```

---

## 💰 成本预算（更新）

| 阶段 | 任务 | 成本估算 |
|------|------|----------|
| Week 1-2 | 基础设施开发 | ¥50-100（Docker 镜像、测试 API） |
| Week 3-4 | 对比实验（300 轨迹） | ¥200-300（DeepSeek API） |
| **Week 5-6** | **4090 训练（5h GPU）** | **¥50-100（本地 4090 免费 / 云 GPU）** |
| Week 7-8 | Benchmark 测试（50 任务 × 2 模式） | ¥50-100（API 成本） |
| **总计** | | **¥350-600** |

**ROI 分析：**
- 一次性投入: ¥350-600
- 单任务节省: ¥0.19
- 回本所需: ~2000 次调用
- 长期价值: 持续降低 API 成本 + 可发论文

---

## 📊 技术亮点

### 1. 开发能力
- ✅ 分布式 Agent 系统（RabbitMQ + Redis + PostgreSQL）
- ✅ 工作流 DAG 引擎（并行执行、依赖管理）
- ✅ 监控系统（Prometheus + Grafana）
- ✅ 单元测试 + 集成测试

### 2. 算法能力 ⭐
- ✅ 多 Agent 协作策略设计
- ✅ 轨迹数据收集与处理
- ✅ 小模型训练（LoRA 微调）
- ✅ 策略优化（Decomposer, Tool Selector, Router）

### 3. 工程能力
- ✅ Docker 容器化部署
- ✅ 消息队列 + 缓存 + 数据库
- ✅ Prometheus 监控 + Grafana 可视化
- ✅ 完整的 CI/CD 流程

---

## 📝 可发表论文方向

**论文标题（示例）：**
> "Hybrid Multi-Agent System with Learned Task Decomposition: Reducing API Costs via Local Model Specialization"

**核心贡献：**
1. **Multi-Agent 协作框架**：对比 3 种执行模式
2. **轨迹驱动训练**：从执行轨迹中学习策略
3. **混合推理架构**：本地小模型 + 云端大模型
4. **成本优化**：降低 50%+ API 成本，保持/提升性能

**实验结果（预期）：**
- 成功率提升 3-5%
- 速度提升 20-30%
- 成本降低 50-60%

---

## 🚀 下一步行动

### 立即任务（Week 3 开始）

#### 1. 创建轨迹收集模块
```bash
# 创建文件
src/monitoring/trajectory_collector.py
src/monitoring/postgres_trajectory_store.py

# 测试
python test_trajectory_collection.py
```

#### 2. 集成到对比实验
```python
# 修改 agent_comparison.py
framework = AgentComparisonFramework(router)
framework.enable_trajectory_collection(
    collector=TrajectoryCollector(),
    store=PostgresTrajectoryStore()
)
```

#### 3. 运行对比实验 + 收集轨迹
```bash
# 100 个任务，生成 300 条轨迹
python scripts/collect_trajectories.py \
  --num_tasks 100 \
  --output_dir data/trajectories/2026-10-29
```

#### 4. 生成训练数据
```bash
# 从轨迹生成训练集
python src/training/data_generator.py \
  --trajectory_dir data/trajectories \
  --output_dir data/training
```

**预计时间**：Week 3（5-7 天）

---

## ✅ 总结

**这个技术路线的优势：**

1. **完整闭环**：从开发 → 评测 → 训练 → 验证
2. **体现能力**：开发 + 算法 + 工程，三位一体
3. **实际价值**：降低 API 成本，提升性能
4. **4090 有用**：训练策略模型（不是摆设）
5. **可发论文**：Hybrid Multi-Agent + 轨迹训练

**当前进度：**
- Week 1-2: 85% ✅
- Week 3-8: 待开始

**关键路径：**
```
Week 3: 轨迹收集 → Week 4: 对比实验 → Week 5-6: 4090 训练 → Week 7-8: 验证
```

---

**准备好了吗？明天开始 Week 3！** 🚀
