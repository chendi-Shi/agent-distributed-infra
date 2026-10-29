"""
实验框架 - Baseline vs ReAct 对比

测试任务集：
1. 系统设计（需求不明确，需反思澄清）
2. 代码审查（子任务失败率高，需错误恢复）
3. 数据分析（依赖复杂，易死锁）
4. 文档生成（系统负载变化，需动态调整）
"""

import asyncio
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import logging

from src.agents.baseline_agent import BaselineAgent
from src.agents.integrated_agent import IntegratedReflectiveAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# 测试任务集
TEST_TASKS = {
    "system_design": [
        "设计一个支持 1M QPS 的分布式缓存系统",
        "设计一个实时消息推送系统，支持 10 万并发连接",
        "设计一个分布式任务调度系统，类似 Airflow",
        "设计一个高可用的配置中心，支持动态更新",
        "设计一个日志收集和分析系统，处理 TB 级数据",
        "设计一个秒杀系统，应对瞬时 100 万请求",
        "设计一个分布式事务解决方案，支持跨服务",
        "设计一个视频直播系统的架构",
        "设计一个搜索引擎的索引和查询架构",
        "设计一个推荐系统，实时更新用户画像",
    ],

    "code_review": [
        "审查 Python 项目的安全漏洞（SQL 注入、XSS、认证问题）",
        "审查 Node.js 后端代码的性能问题",
        "审查 React 前端代码的最佳实践",
        "审查 Java 微服务的并发安全问题",
        "审查 Go 代码的内存泄漏和资源管理",
        "审查 TypeScript 代码的类型安全性",
        "审查 Django 项目的 ORM 查询优化",
        "审查 Spring Boot 项目的配置和依赖",
        "审查前端项目的打包和加载性能",
        "审查 API 接口的设计规范和文档完整性",
        "审查数据库索引设计和查询效率",
        "审查分布式系统的容错和降级策略",
        "审查代码的测试覆盖率和边界条件",
        "审查 Docker 配置和容器安全",
        "审查 Kubernetes 部署配置和资源限制",
    ],

    "data_analysis": [
        "分析用户行为数据，找出流失原因",
        "分析 A/B 测试结果，评估新功能效果",
        "分析系统性能指标，定位瓶颈",
        "分析用户画像数据，优化推荐算法",
        "分析日志数据，排查生产事故原因",
        "分析业务数据，预测下季度增长趋势",
        "分析用户反馈，提取高频问题",
        "分析竞品数据，制定差异化策略",
        "分析转化漏斗，优化关键路径",
        "分析成本数据，找出优化空间",
    ],

    "doc_generation": [
        "编写 API 文档，包含接口定义、参数、示例",
        "编写系统架构文档，说明各模块职责",
        "编写部署文档，包含环境配置和操作步骤",
        "编写技术方案文档，评估可行性和风险",
        "编写用户手册，说明功能和使用方法",
        "编写数据库设计文档，包含表结构和关系",
        "编写测试计划，覆盖功能、性能、安全",
        "编写故障复盘文档，分析原因和改进措施",
        "编写代码规范文档，统一团队风格",
        "编写监控告警文档，说明指标和阈值",
        "编写发布 checklist，确保上线流程完整",
        "编写技术分享 PPT，讲解核心原理",
        "编写 RPC 文档，说明迁移方案和兼容性",
        "编写性能优化报告，对比前后效果",
        "编写安全审计报告，列出风险和建议",
    ]
}


class MockLLMClient:
    """Mock LLM 客户端（用于快速测试）"""

    async def generate(self, prompt: str) -> str:
        """模拟 LLM 生成"""
        await asyncio.sleep(0.1)  # 模拟网络延迟

        if "分解" in prompt or "子任务" in prompt:
            # 返回任务分解
            return json.dumps([
                {"id": "1", "description": "需求分析", "dependencies": []},
                {"id": "2", "description": "方案设计", "dependencies": ["1"]},
                {"id": "3", "description": "实现代码", "dependencies": ["2"]},
                {"id": "4", "description": "测试验证", "dependencies": ["3"]},
            ])
        elif "反思" in prompt or "调整" in prompt:
            # 返回反思结果（20% 概率需要调整）
            import random
            if random.random() < 0.2:
                return json.dumps({
                    "need_replan": True,
                    "reason": "发现遗漏子任务",
                    "actions": ["添加新任务"],
                    "new_subtasks": [
                        {"id": "3.5", "description": "代码审查", "dependencies": ["3"]}
                    ]
                })
            else:
                return json.dumps({
                    "need_replan": False,
                    "reason": "执行顺利",
                    "actions": []
                })
        else:
            # 返回执行结果
            return "任务执行完成"


class ExperimentRunner:
    """实验运行器"""

    def __init__(self, output_dir: str = "experiments/results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.llm = MockLLMClient()

    async def run_comparison(
        self,
        task_type: str,
        num_tasks: int = 10
    ) -> Dict[str, Any]:
        """
        运行对比实验

        Args:
            task_type: 任务类型
            num_tasks: 测试任务数量

        Returns:
            对比结果
        """
        tasks = TEST_TASKS[task_type][:num_tasks]

        logger.info(f"Running comparison: {task_type}, {num_tasks} tasks")

        # 运行 Baseline
        baseline_results = []
        for i, task in enumerate(tasks, 1):
            logger.info(f"[Baseline] Task {i}/{num_tasks}: {task[:50]}...")
            result = await self._run_baseline(task)
            baseline_results.append(result)

        # 运行 ReAct
        react_results = []
        for i, task in enumerate(tasks, 1):
            logger.info(f"[ReAct] Task {i}/{num_tasks}: {task[:50]}...")
            result = await self._run_react(task)
            react_results.append(result)

        # 对比分析
        comparison = self._analyze_results(
            baseline_results,
            react_results,
            task_type
        )

        # 保存结果
        self._save_results(task_type, comparison)

        return comparison

    async def _run_baseline(self, task: str) -> Dict:
        """运行 Baseline Agent"""
        agent = BaselineAgent(self.llm)
        result = await agent.execute_task(task)
        return result

    async def _run_react(self, task: str) -> Dict:
        """运行 ReAct Agent"""
        agent = IntegratedReflectiveAgent(self.llm)
        result = await agent.execute_task(task)
        return result

    def _analyze_results(
        self,
        baseline_results: List[Dict],
        react_results: List[Dict],
        task_type: str
    ) -> Dict[str, Any]:
        """分析对比结果"""

        def calc_stats(results):
            total = len(results)
            successful = sum(1 for r in results if r["success"])
            avg_time = sum(r["execution_time"] for r in results) / total
            avg_reflections = sum(r["reflection_count"] for r in results) / total

            return {
                "total": total,
                "successful": successful,
                "success_rate": successful / total,
                "avg_execution_time": avg_time,
                "avg_reflection_count": avg_reflections,
            }

        baseline_stats = calc_stats(baseline_results)
        react_stats = calc_stats(react_results)

        # 计算改进
        improvement = {
            "success_rate": (
                (react_stats["success_rate"] - baseline_stats["success_rate"])
                / baseline_stats["success_rate"] * 100
            ),
            "execution_time": (
                (baseline_stats["avg_execution_time"] - react_stats["avg_execution_time"])
                / baseline_stats["avg_execution_time"] * 100
            ),
        }

        return {
            "task_type": task_type,
            "baseline": baseline_stats,
            "react": react_stats,
            "improvement": improvement,
            "timestamp": datetime.now().isoformat(),
        }

    def _save_results(self, task_type: str, comparison: Dict):
        """保存结果"""
        output_file = self.output_dir / f"{task_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, indent=2, ensure_ascii=False)

        logger.info(f"Results saved to {output_file}")

    async def run_full_experiment(self):
        """运行完整实验（所有任务类型）"""
        all_results = {}

        for task_type in TEST_TASKS.keys():
            logger.info(f"\n{'='*60}")
            logger.info(f"Testing {task_type}")
            logger.info(f"{'='*60}\n")

            comparison = await self.run_comparison(task_type, num_tasks=10)
            all_results[task_type] = comparison

            # 打印摘要
            print(f"\n{task_type} Results:")
            print(f"  Baseline success rate: {comparison['baseline']['success_rate']:.1%}")
            print(f"  ReAct success rate: {comparison['react']['success_rate']:.1%}")
            print(f"  Improvement: {comparison['improvement']['success_rate']:+.1f}%")
            print(f"  Avg reflections: {comparison['react']['avg_reflection_count']:.1f}")

        # 保存汇总
        summary_file = self.output_dir / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)

        logger.info(f"\nFull experiment completed. Summary: {summary_file}")
        return all_results


async def main():
    """主函数"""
    runner = ExperimentRunner()

    # 快速测试（每类 5 个任务）
    print("Running quick test...")
    results = await runner.run_comparison("system_design", num_tasks=5)

    print(f"\nQuick test results:")
    print(f"  Baseline: {results['baseline']['success_rate']:.1%} success")
    print(f"  ReAct: {results['react']['success_rate']:.1%} success")
    print(f"  Improvement: {results['improvement']['success_rate']:+.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
