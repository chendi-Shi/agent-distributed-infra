"""
快速运行脚本
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from experiments.comparison_framework import ExperimentRunner


async def quick_demo():
    """快速演示"""
    print("="*60)
    print("ReAct Agent 快速演示")
    print("="*60)
    print()

    runner = ExperimentRunner()

    # 运行系统设计任务对比
    print("运行 5 个系统设计任务...")
    results = await runner.run_comparison("system_design", num_tasks=5)

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


async def full_experiment():
    """完整实验"""
    print("="*60)
    print("完整对比实验 - 所有任务类型")
    print("="*60)
    print()

    runner = ExperimentRunner()
    results = await runner.run_full_experiment()

    print("\n" + "="*60)
    print("实验汇总")
    print("="*60)

    for task_type, comparison in results.items():
        print(f"\n{task_type}:")
        print(f"  成功率改进: {comparison['improvement']['success_rate']:+.1f}%")
        print(f"  平均反思: {comparison['react']['avg_reflection_count']:.1f} 次")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "full":
        asyncio.run(full_experiment())
    else:
        asyncio.run(quick_demo())
