"""
PostgreSQL 轨迹存储

存储完整执行轨迹，用于：
1. 标注界面查询
2. 主动学习选择
3. 训练数据生成
"""

import json
from datetime import datetime
from typing import List, Dict, Optional
import psycopg2
from psycopg2.extras import execute_values, Json


class PostgresTrajectoryStore:
    """PostgreSQL 轨迹存储"""

    def __init__(self, connection_string: str = None):
        if connection_string is None:
            connection_string = "postgresql://agent:agent123@localhost:5432/agent_state"

        self.conn = psycopg2.connect(connection_string)
        self._init_tables()

    def _init_tables(self):
        """初始化表结构"""
        with self.conn.cursor() as cur:
            # 轨迹表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trajectories (
                    trajectory_id VARCHAR(100) PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    mode VARCHAR(20) NOT NULL,
                    task_description TEXT NOT NULL,
                    task_type VARCHAR(50),

                    -- 分解阶段
                    subtasks JSONB,
                    decompose_prompt TEXT,
                    decompose_response TEXT,

                    -- 执行阶段
                    tool_calls JSONB,
                    intermediate_states JSONB,

                    -- 输出
                    final_result TEXT,
                    success BOOLEAN,
                    error_message TEXT,

                    -- 性能指标
                    execution_time FLOAT,
                    api_calls INT,
                    tokens_used INT,
                    cost_estimate FLOAT,

                    -- 标注状态
                    annotation_status VARCHAR(20) DEFAULT 'pending',  -- pending / annotated / skipped
                    annotation_priority FLOAT DEFAULT 0.0,  -- 主动学习打分
                    annotated_at TIMESTAMP,
                    annotator VARCHAR(100),

                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 标注表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS annotations (
                    annotation_id SERIAL PRIMARY KEY,
                    trajectory_id VARCHAR(100) REFERENCES trajectories(trajectory_id),

                    -- 任务分解标注
                    subtasks_quality INT,  -- 1-5 评分
                    subtasks_feedback TEXT,  -- 改进建议
                    subtasks_corrected JSONB,  -- 修正后的子任务列表

                    -- 工具选择标注
                    tool_choices JSONB,  -- [{"subtask_id": ..., "correct_tool": ..., "reason": ...}]

                    -- 优先级标注
                    priority_ranking JSONB,  -- 子任务的正确优先级排序

                    -- 整体评价
                    overall_quality INT,  -- 1-5
                    comments TEXT,

                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_trajectories_mode ON trajectories(mode);
                CREATE INDEX IF NOT EXISTS idx_trajectories_task_type ON trajectories(task_type);
                CREATE INDEX IF NOT EXISTS idx_trajectories_annotation_status ON trajectories(annotation_status);
                CREATE INDEX IF NOT EXISTS idx_trajectories_priority ON trajectories(annotation_priority DESC);
            """)

            self.conn.commit()

    def save_trajectory(self, trajectory: Dict):
        """保存轨迹"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO trajectories (
                    trajectory_id, timestamp, mode, task_description, task_type,
                    subtasks, decompose_prompt, decompose_response,
                    tool_calls, intermediate_states,
                    final_result, success, error_message,
                    execution_time, api_calls, tokens_used, cost_estimate
                ) VALUES (
                    %(trajectory_id)s, %(timestamp)s, %(mode)s, %(task_description)s, %(task_type)s,
                    %(subtasks)s, %(decompose_prompt)s, %(decompose_response)s,
                    %(tool_calls)s, %(intermediate_states)s,
                    %(final_result)s, %(success)s, %(error_message)s,
                    %(execution_time)s, %(api_calls)s, %(tokens_used)s, %(cost_estimate)s
                )
                ON CONFLICT (trajectory_id) DO NOTHING
            """, {
                **trajectory,
                "subtasks": Json(trajectory.get("subtasks", [])),
                "tool_calls": Json(trajectory.get("tool_calls", [])),
                "intermediate_states": Json(trajectory.get("intermediate_states", [])),
            })

            self.conn.commit()

    def get_trajectories_for_annotation(
        self,
        limit: int = 50,
        mode: Optional[str] = None,
        task_type: Optional[str] = None,
        min_priority: float = 0.0,
    ) -> List[Dict]:
        """
        获取待标注轨迹（按主动学习优先级排序）

        Args:
            limit: 返回数量
            mode: 过滤模式
            task_type: 过滤任务类型
            min_priority: 最小优先级

        Returns:
            轨迹列表
        """
        with self.conn.cursor() as cur:
            query = """
                SELECT
                    trajectory_id, timestamp, mode, task_description, task_type,
                    subtasks, tool_calls,
                    final_result, success,
                    execution_time, api_calls, tokens_used,
                    annotation_priority
                FROM trajectories
                WHERE annotation_status = 'pending'
                AND annotation_priority >= %s
            """
            params = [min_priority]

            if mode:
                query += " AND mode = %s"
                params.append(mode)

            if task_type:
                query += " AND task_type = %s"
                params.append(task_type)

            query += " ORDER BY annotation_priority DESC LIMIT %s"
            params.append(limit)

            cur.execute(query, params)

            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def save_annotation(
        self,
        trajectory_id: str,
        annotation: Dict,
        annotator: str = "human",
    ):
        """保存标注"""
        with self.conn.cursor() as cur:
            # 保存标注
            cur.execute("""
                INSERT INTO annotations (
                    trajectory_id,
                    subtasks_quality, subtasks_feedback, subtasks_corrected,
                    tool_choices, priority_ranking,
                    overall_quality, comments
                ) VALUES (
                    %(trajectory_id)s,
                    %(subtasks_quality)s, %(subtasks_feedback)s, %(subtasks_corrected)s,
                    %(tool_choices)s, %(priority_ranking)s,
                    %(overall_quality)s, %(comments)s
                )
            """, {
                "trajectory_id": trajectory_id,
                **annotation,
                "subtasks_corrected": Json(annotation.get("subtasks_corrected", [])),
                "tool_choices": Json(annotation.get("tool_choices", [])),
                "priority_ranking": Json(annotation.get("priority_ranking", [])),
            })

            # 更新轨迹状态
            cur.execute("""
                UPDATE trajectories
                SET annotation_status = 'annotated',
                    annotated_at = CURRENT_TIMESTAMP,
                    annotator = %s
                WHERE trajectory_id = %s
            """, (annotator, trajectory_id))

            self.conn.commit()

    def get_annotated_trajectories(
        self,
        limit: Optional[int] = None,
    ) -> List[Dict]:
        """获取已标注轨迹（用于训练）"""
        with self.conn.cursor() as cur:
            query = """
                SELECT
                    t.*,
                    a.subtasks_quality, a.subtasks_corrected,
                    a.tool_choices, a.priority_ranking,
                    a.overall_quality, a.comments
                FROM trajectories t
                JOIN annotations a ON t.trajectory_id = a.trajectory_id
                WHERE t.annotation_status = 'annotated'
                ORDER BY t.annotated_at DESC
            """

            if limit:
                query += f" LIMIT {limit}"

            cur.execute(query)

            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def compute_annotation_priorities(self):
        """
        计算主动学习优先级

        策略：
        1. 成功的轨迹优先（失败的难以学习）
        2. 子任务数量适中（3-7 个，太少太简单，太多太复杂）
        3. 执行时间适中（太快可能太简单）
        4. 混合不同任务类型
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE trajectories
                SET annotation_priority = (
                    CASE
                        -- 失败的轨迹降低优先级
                        WHEN NOT success THEN 0.1
                        -- 子任务数量适中
                        WHEN jsonb_array_length(subtasks) BETWEEN 3 AND 7 THEN 1.0
                        WHEN jsonb_array_length(subtasks) < 3 THEN 0.5
                        ELSE 0.3
                    END
                    *
                    CASE
                        -- 执行时间适中（5-30s）
                        WHEN execution_time BETWEEN 5 AND 30 THEN 1.0
                        WHEN execution_time < 5 THEN 0.6
                        ELSE 0.8
                    END
                    *
                    -- 随机扰动（避免同质化）
                    (0.8 + random() * 0.4)
                )
                WHERE annotation_status = 'pending'
            """)

            self.conn.commit()

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN annotation_status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN annotation_status = 'annotated' THEN 1 ELSE 0 END) as annotated,
                    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful,
                    AVG(execution_time) as avg_execution_time,
                    AVG(tokens_used) as avg_tokens
                FROM trajectories
            """)

            row = cur.fetchone()
            return {
                "total": row[0],
                "pending": row[1],
                "annotated": row[2],
                "successful": row[3],
                "avg_execution_time": float(row[4]) if row[4] else 0,
                "avg_tokens": float(row[5]) if row[5] else 0,
            }


if __name__ == "__main__":
    # 测试
    store = PostgresTrajectoryStore()

    # 初始化表
    print("✅ Tables initialized")

    # 获取统计
    stats = store.get_stats()
    print(f"\nStats: {stats}")
