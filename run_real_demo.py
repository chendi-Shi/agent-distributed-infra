"""
使用真实 DeepSeek API 的快速演示
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from experiments.comparison_framework import ExperimentRunner


async def main():
    """主函数 - 使用真实 DeepSeek API"""
    print("="*60)
    print("ReAct Agent 快速演示 - 使用真实 DeepSeek API")
    print("="*60)
    print()

    # 初始化（使用真实 LLM）
    runner = ExperimentRunner(use_real_llm=True)

    # 运行 3 个系统设计任务（节省 API 调用）
    print("运行 3 个系统设计任务...")
    results = await runner.run_comparison("system_design", num_tasks=3)

    print("\n" + "="*60)
    print("实验结果")
    print("="*60)
    print(f"\nBaseline Agent（传统方式）:")
    print(f"  成功率: {results['baseline']['success_rate']:.1%}")
    print(f"  平均耗时: {results['baseline']['avg_execution_time']:.2f}s")
    print(f"  反思次数: {results['baseline']['avg_reflection_count']:.1f}")

    print(f"\nReAct Agent（动态反思）:")
    print(f"  成功率: {results['react']['success_rate']:.1%}")
    print(f"  平均耗时: {results['react']['avg_execution_time']:.2f}s")
    print(f"  反思次数: {results['react']['avg_reflection_count']:.1f}")

    print(f"\n改进:")
    print(f"  成功率提升: {results['improvement']['success_rate']:+.1f}%")
    print(f"  耗时优化: {results['improvement']['execution_time']:+.1f}%")

    print(f"\n结果已保存到: experiments/results/")
    print()


if __name__ == "__main__":
    asyncio.run(main())
