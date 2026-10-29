# 轨迹标注工作流程

## 📋 概述

本文档说明如何收集轨迹、进行人工标注、生成训练数据的完整流程。

---

## 🚀 快速开始

### 1. 环境准备

确保服务已启动：
```bash
# PostgreSQL（存储轨迹）
docker-compose -f docker-compose.simple.yaml up -d postgres

# 安装依赖
pip install flask scikit-learn psycopg2-binary
```

### 2. 收集轨迹（自动化）

运行 Multi-Agent 系统收集执行轨迹：

```bash
# 收集 100 条轨迹
python scripts/collect_trajectories.py --num_tasks 100 --modes multi_agent
```

**输出位置**：
- JSONL 文件：`data/trajectories/2026-10-29/multi_agent_trajectories.jsonl`
- PostgreSQL：`trajectories` 表

### 3. 主动学习选择样本

系统会自动计算每条轨迹的标注优先级：

```python
from src.monitoring.postgres_trajectory_store import PostgresTrajectoryStore

store = PostgresTrajectoryStore()
store.compute_annotation_priorities()  # 计算优先级
```

**优先级策略**：
- ✅ 成功的轨迹（失败的难学习）
- ✅ 子任务数量适中（3-7 个）
- ✅ 执行时间适中（5-30s）
- ✅ 随机扰动（避免同质化）

### 4. 人工标注

启动 Web 标注界面：

```bash
python scripts/annotation_ui.py

# 访问 http://localhost:5000
```

**标注流程**：
1. 选择标注策略（推荐：混合策略）
2. 设定标注数量（建议第一轮：50 条）
3. 系统自动选出最有价值的样本
4. 逐条标注：
   - 任务分解质量评分（1-5）
   - 改进建议
   - 工具选择建议
   - 整体质量评分
5. 提交保存到数据库

**时间估算**：
- 单条标注：2-3 分钟
- 50 条：2.5-4 小时（可分多次完成）

### 5. 生成训练数据

从已标注数据生成训练集：

```bash
python src/training/data_generator.py \
  --input postgres \
  --output data/training
```

**输出文件**：
- `data/training/decomposer_train.jsonl`
- `data/training/tool_selector_train.jsonl`
- `data/training/router_train.jsonl`

---

## 📊 标注指南

### 任务分解质量评分

| 分数 | 标准 | 示例 |
|------|------|------|
| 5 | 完美：子任务清晰、可并行、覆盖全面 | ✅ |
| 4 | 良好：略有冗余或遗漏，但整体合理 | |
| 3 | 及格：能完成任务，但效率不高 | |
| 2 | 较差：有明显问题，需要大幅调整 | |
| 1 | 失败：无法完成任务 | ❌ |

### 改进建议示例

**原始分解**：
1. 分析需求
2. 设计架构
3. 选技术
4. 写文档

**改进建议**：
> 缺少"容量规划和成本估算"这一步，建议在步骤 2 和 3 之间加入

**修正后**：
1. 分析需求
2. 设计架构
3. **容量规划和成本估算** ← 新增
4. 选技术
5. 写文档

### 工具选择标注

为每个子任务标注最优工具：

| 子任务 | 候选工具 | 最优选择 | 理由 |
|--------|----------|----------|------|
| 分析代码安全 | code_review, static_analysis, web_search | **static_analysis** | 全面快速 |
| 设计架构图 | design_tool, llm_generate | **design_tool** | 专业工具 |
| 查行业标准 | web_search, doc_search | **web_search** | 最新信息 |

---

## 🔄 迭代标注（第二轮）

训练初版模型后，再进行一轮主动学习：

```bash
# 1. 部署初版模型
python scripts/deploy_model.py --model models/decomposer

# 2. 收集新轨迹（用初版模型辅助）
python scripts/collect_trajectories.py --num_tasks 50 --use_model

# 3. 主动学习选择最不确定的 20-30 条
python scripts/annotation_ui.py  # 标注第二轮

# 4. 重新训练
python scripts/train_decomposer.py --data data/training/decomposer_train_v2.jsonl
```

---

## 📈 数据统计

查看标注进度：

```python
from src.monitoring.postgres_trajectory_store import PostgresTrajectoryStore

store = PostgresTrajectoryStore()
stats = store.get_stats()

print(f"总轨迹：{stats['total']}")
print(f"待标注：{stats['pending']}")
print(f"已标注：{stats['annotated']}")
print(f"标注进度：{stats['annotated']/stats['total']*100:.1f}%")
```

---

## ⚠️ 注意事项

1. **标注一致性**：尽量保持评分标准一致
2. **备份数据**：定期备份 PostgreSQL（`pg_dump agent_state`）
3. **质量优于数量**：50 条高质量标注 > 200 条低质量
4. **及时保存**：每标注 10 条休息一次，避免疲劳

---

## 🎯 下一步

标注完成后：
- Week 5-6：在 4090 上训练 Qwen2.5-7B（LoRA）
- Week 7-8：部署验证，对比 Baseline vs Trained

完整计划见：`docs/TECHNICAL_ROADMAP.md`
