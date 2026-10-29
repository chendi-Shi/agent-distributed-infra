"""
轨迹收集脚本

自动运行 Multi-Agent 系统，收集完整执行轨迹用于标注和训练
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import asyncio

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.multi_agent import MultiAgentSystem
from src.infra.inference.router import InferenceRouter
from src.experiments.agent_comparison import AgentComparisonFramework


# 任务模板库
TASK_TEMPLATES = {
    "code_review": [
        "审查这个 Python 项目的安全漏洞，重点关注 SQL 注入和 XSS",
        "分析这段代码的性能瓶颈，给出优化建议",
        "检查这个 API 的错误处理是否完整",
    ],
    "system_design": [
        "设计一个支持 100 万 QPS 的分布式缓存系统",
        "设计一个秒杀系统，处理高并发库存扣减",
        "设计一个推荐系统的实时特征计算架构",
    ],
    "data_analysis": [
        "分析用户留存数据，找出流失的关键节点",
        "评估 A/B 测试结果，判断新功能是否上线",
        "分析服务器日志，定位性能下降的原因",
    ],
    "doc_generation": [
        "为这个 REST API 生成 OpenAPI 文档",
        "写一份技术方案设计文档：分布式事务解决方案",
        "生成项目 README，包含安装、使用和贡献指南",
    ],
}


class TrajectoryCollector:
    """轨迹收集器"""

    def __init__(self, output_dir: str = "data/trajectories"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 按日期创建子目录
        today = datetime.now().strftime("%Y-%m-%d")
        self.session_dir = self.output_dir / today
        self.session_dir.mkdir(exist_ok=True)

    def collect_trajectory(
        self,
        task_description: str,
        mode: str,  # "single" / "pipeline" / "multi_agent"
        result: Dict,
    ) -> Dict:
        """
        收集单条轨迹

        Args:
            task_description: 任务描述
            mode: 执行模式
            result: 执行结果（包含子任务、工具调用等）

        Returns:
            完整轨迹数据
        """
        trajectory = {
            "trajectory_id": f"{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "timestamp": datetime.now().isoformat(),
            "mode": mode,

            # 输入
            "task_description": task_description,
            "task_type": self._infer_task_type(task_description),

            # 分解阶段
            "subtasks": result.get("subtasks", []),
            "decompose_prompt": result.get("decompose_prompt", ""),
            "decompose_response": result.get("decompose_response", ""),

            # 执行阶段
            "tool_calls": result.get("tool_calls", []),
            "intermediate_states": result.get("intermediate_states", []),

            # 输出
            "final_result": result.get("final_result", ""),
            "success": result.get("success", False),
            "error_message": result.get("error_message"),

            # 性能指标
            "execution_time": result.get("execution_time", 0),
            "api_calls": result.get("api_calls", 0),
            "tokens_used": result.get("tokens_used", 0),
            "cost_estimate": result.get("cost_estimate", 0),
        }

        return trajectory

    def _infer_task_type(self, description: str) -> str:
        """从描述推断任务类型"""
        keywords = {
            "code_review": ["审查", "review", "代码", "安全", "漏洞", "优化"],
            "system_design": ["设计", "design", "架构", "系统", "分布式"],
            "data_analysis": ["分析", "analysis", "数据", "评估", "日志"],
            "doc_generation": ["文档", "documentation", "README", "API", "生成"],
        }

        desc_lower = description.lower()
        for task_type, words in keywords.items():
            if any(word in desc_lower for word in words):
                return task_type

        return "other"

    def save_trajectory(self, trajectory: Dict, mode: str):
        """保存轨迹到 JSONL 文件"""
        output_file = self.session_dir / f"{mode}_trajectories.jsonl"

        with open(output_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(trajectory, ensure_ascii=False) + "\n")

        print(f"✅ Saved trajectory: {trajectory['trajectory_id']}")

    def save_summary(self, stats: Dict):
        """保存收集统计"""
        summary_file = self.session_dir / "summary.json"

        with open(summary_file, "w", encoding="utf-8") as f:
            json.dumps(stats, indent=2, ensure_ascii=False, f=f)


async def run_collection(
    num_tasks_per_mode: int = 30,
    modes: List[str] = None,
):
    """
    运行轨迹收集

    Args:
        num_tasks_per_mode: 每种模式收集多少条
        modes: 要测试的模式列表
    """
    if modes is None:
        modes = ["single", "pipeline", "multi_agent"]

    print(f"=== 轨迹收集开始 ===")
    print(f"模式: {modes}")
    print(f"每种模式任务数: {num_tasks_per_mode}\n")

    # 初始化
    router = InferenceRouter()
    framework = AgentComparisonFramework(router)
    collector = TrajectoryCollector()

    # 生成任务列表（混合不同类型）
    tasks = []
    for task_type, templates in TASK_TEMPLATES.items():
        tasks.extend(templates * (num_tasks_per_mode // len(TASK_TEMPLATES) + 1))

    # 只取需要的数量
    import random
    random.shuffle(tasks)
    tasks = tasks[:num_tasks_per_mode]

    # 统计
    stats = {
        "total_trajectories": 0,
        "successful": 0,
        "failed": 0,
        "by_mode": {mode: {"total": 0, "success": 0} for mode in modes},
        "by_task_type": {},
    }

    # 收集轨迹
    for mode in modes:
        print(f"\n--- 模式: {mode} ---")

        for i, task_desc in enumerate(tasks, 1):
            print(f"[{i}/{num_tasks_per_mode}] {task_desc[:50]}...")

            try:
                # 运行任务
                result = await framework.run_task(task_desc, mode=mode)

                # 收集轨迹
                trajectory = collector.collect_trajectory(task_desc, mode, result)

                # 保存
                collector.save_trajectory(trajectory, mode)

                # 更新统计
                stats["total_trajectories"] += 1
                stats["by_mode"][mode]["total"] += 1

                if result.get("success"):
                    stats["successful"] += 1
                    stats["by_mode"][mode]["success"] += 1
                else:
                    stats["failed"] += 1

                task_type = trajectory["task_type"]
                if task_type not in stats["by_task_type"]:
                    stats["by_task_type"][task_type] = {"total": 0, "success": 0}
                stats["by_task_type"][task_type]["total"] += 1
                if result.get("success"):
                    stats["by_task_type"][task_type]["success"] += 1

            except Exception as e:
                print(f"❌ Error: {e}")
                stats["failed"] += 1

    # 保存统计
    collector.save_summary(stats)

    # 打印总结
    print(f"\n=== 收集完成 ===")
    print(f"总轨迹数: {stats['total_trajectories']}")
    print(f"成功: {stats['successful']} ({stats['successful']/stats['total_trajectories']*100:.1f}%)")
    print(f"失败: {stats['failed']}")
    print(f"\n各模式统计:")
    for mode, mode_stats in stats["by_mode"].items():
        success_rate = mode_stats["success"] / mode_stats["total"] * 100 if mode_stats["total"] > 0 else 0
        print(f"  {mode}: {mode_stats['success']}/{mode_stats['total']} ({success_rate:.1f}%)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="收集 Agent 执行轨迹")
    parser.add_argument("--num_tasks", type=int, default=30, help="每种模式的任务数")
    parser.add_argument("--modes", nargs="+", default=["multi_agent"], help="执行模式")

    args = parser.parse_args()

    asyncio.run(run_collection(
        num_tasks_per_mode=args.num_tasks,
        modes=args.modes,
    ))
