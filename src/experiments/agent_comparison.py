"""
Agent Comparison Framework
Compare three agent execution modes:
1. Single Agent - one agent does everything
2. Fixed Pipeline - Planner → Worker → Reviewer (sequential)
3. Multi-Agent - dynamic collaboration with parallelism

Metrics tracked:
- Success rate
- Execution time
- API cost (call count, token usage)
"""
import asyncio
import logging
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json

from agents.multi_agent import MultiAgentOrchestrator, AgentRole
from infra.inference.router import ModelRouter
from monitoring.metrics import get_metrics_collector


logger = logging.getLogger(__name__)


@dataclass
class ExecutionMetrics:
    """Metrics for a single execution"""
    mode: str  # single, fixed_pipeline, multi_agent
    task_id: str
    success: bool
    execution_time: float
    api_calls: int = 0
    tokens_used: int = 0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "mode": self.mode,
            "task_id": self.task_id,
            "success": self.success,
            "execution_time": self.execution_time,
            "api_calls": self.api_calls,
            "tokens_used": self.tokens_used,
            "error": self.error,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class ComparisonResults:
    """Aggregated comparison results"""
    single_agent: List[ExecutionMetrics] = field(default_factory=list)
    fixed_pipeline: List[ExecutionMetrics] = field(default_factory=list)
    multi_agent: List[ExecutionMetrics] = field(default_factory=list)

    def get_summary(self) -> Dict:
        """Get summary statistics"""
        return {
            "single_agent": self._summarize(self.single_agent),
            "fixed_pipeline": self._summarize(self.fixed_pipeline),
            "multi_agent": self._summarize(self.multi_agent)
        }

    def _summarize(self, metrics: List[ExecutionMetrics]) -> Dict:
        """Summarize metrics for one mode"""
        if not metrics:
            return {
                "count": 0,
                "success_rate": 0.0,
                "avg_time": 0.0,
                "total_api_calls": 0,
                "total_tokens": 0,
                "cost_estimate": 0.0
            }

        successful = [m for m in metrics if m.success]

        return {
            "count": len(metrics),
            "success_rate": len(successful) / len(metrics) * 100,
            "avg_time": sum(m.execution_time for m in metrics) / len(metrics),
            "min_time": min(m.execution_time for m in metrics),
            "max_time": max(m.execution_time for m in metrics),
            "total_api_calls": sum(m.api_calls for m in metrics),
            "total_tokens": sum(m.tokens_used for m in metrics),
            "cost_estimate": self._estimate_cost(metrics)
        }

    def _estimate_cost(self, metrics: List[ExecutionMetrics]) -> float:
        """Estimate cost based on token usage"""
        # DeepSeek pricing: ~$0.14/1M input tokens, ~$0.28/1M output tokens
        # Simplified: assume 50/50 input/output
        total_tokens = sum(m.tokens_used for m in metrics)
        return total_tokens / 1_000_000 * 0.21  # Average cost


class AgentComparisonFramework:
    """Framework for comparing agent execution modes"""

    def __init__(self, router: ModelRouter):
        self.router = router
        self.results = ComparisonResults()
        self.logger = logging.getLogger("AgentComparison")
        self.metrics_collector = get_metrics_collector()

    async def run_single_agent(self, task: Dict) -> ExecutionMetrics:
        """
        Run task with single agent (no role separation)

        Args:
            task: Task definition with 'description' and 'parameters'
        """
        start_time = time.time()
        task_id = task.get('id', f"task-{int(time.time())}")

        try:
            self.logger.info(f"[Single Agent] Processing: {task_id}")

            # Single agent does everything: plan + execute + review
            prompt = f"""You are a general-purpose agent. Complete this task:

Task: {task['description']}
Parameters: {json.dumps(task.get('parameters', {}), indent=2)}

Steps:
1. Plan the approach
2. Execute the task
3. Review your work

Provide the final result."""

            api_calls_before = self.router.stats['total_requests']

            # Execute with router
            result = await self.router.route_request(
                prompt=prompt,
                agent_id="single-agent"
            )

            api_calls = self.router.stats['total_requests'] - api_calls_before
            execution_time = time.time() - start_time

            # Estimate tokens (rough approximation)
            tokens_used = len(prompt.split()) * 1.3 + len(result.split()) * 1.3

            metric = ExecutionMetrics(
                mode="single_agent",
                task_id=task_id,
                success=True,
                execution_time=execution_time,
                api_calls=api_calls,
                tokens_used=int(tokens_used)
            )

            self.results.single_agent.append(metric)
            self.logger.info(f"[Single Agent] ✓ Completed in {execution_time:.2f}s")

            return metric

        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"[Single Agent] ✗ Failed: {e}")

            metric = ExecutionMetrics(
                mode="single_agent",
                task_id=task_id,
                success=False,
                execution_time=execution_time,
                error=str(e)
            )

            self.results.single_agent.append(metric)
            return metric

    async def run_fixed_pipeline(self, task: Dict) -> ExecutionMetrics:
        """
        Run task with fixed pipeline: Planner → Worker → Reviewer (sequential)

        Args:
            task: Task definition
        """
        start_time = time.time()
        task_id = task.get('id', f"task-{int(time.time())}")

        try:
            self.logger.info(f"[Fixed Pipeline] Processing: {task_id}")

            api_calls_before = self.router.stats['total_requests']
            total_tokens = 0

            # Step 1: Planner
            plan_prompt = f"""You are a Planner. Create an execution plan for:

Task: {task['description']}
Parameters: {json.dumps(task.get('parameters', {}), indent=2)}

Provide a step-by-step plan."""

            plan = await self.router.route_request(
                prompt=plan_prompt,
                agent_id="planner"
            )
            total_tokens += len(plan_prompt.split()) * 1.3 + len(plan.split()) * 1.3

            self.logger.debug(f"[Fixed Pipeline] Plan created")

            # Step 2: Worker (execute plan)
            work_prompt = f"""You are a Worker. Execute this plan:

Plan:
{plan}

Task: {task['description']}

Provide the execution result."""

            result = await self.router.route_request(
                prompt=work_prompt,
                agent_id="worker"
            )
            total_tokens += len(work_prompt.split()) * 1.3 + len(result.split()) * 1.3

            self.logger.debug(f"[Fixed Pipeline] Work completed")

            # Step 3: Reviewer
            review_prompt = f"""You are a Reviewer. Review this work:

Original Task: {task['description']}
Result:
{result}

Is this correct? Provide feedback and final approval."""

            review = await self.router.route_request(
                prompt=review_prompt,
                agent_id="reviewer"
            )
            total_tokens += len(review_prompt.split()) * 1.3 + len(review.split()) * 1.3

            self.logger.debug(f"[Fixed Pipeline] Review completed")

            api_calls = self.router.stats['total_requests'] - api_calls_before
            execution_time = time.time() - start_time

            metric = ExecutionMetrics(
                mode="fixed_pipeline",
                task_id=task_id,
                success=True,
                execution_time=execution_time,
                api_calls=api_calls,
                tokens_used=int(total_tokens)
            )

            self.results.fixed_pipeline.append(metric)
            self.logger.info(f"[Fixed Pipeline] ✓ Completed in {execution_time:.2f}s")

            return metric

        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"[Fixed Pipeline] ✗ Failed: {e}")

            metric = ExecutionMetrics(
                mode="fixed_pipeline",
                task_id=task_id,
                success=False,
                execution_time=execution_time,
                error=str(e)
            )

            self.results.fixed_pipeline.append(metric)
            return metric

    async def run_multi_agent(self, task: Dict) -> ExecutionMetrics:
        """
        Run task with multi-agent collaboration (parallel where possible)

        Args:
            task: Task definition
        """
        start_time = time.time()
        task_id = task.get('id', f"task-{int(time.time())}")

        try:
            self.logger.info(f"[Multi-Agent] Processing: {task_id}")

            api_calls_before = self.router.stats['total_requests']

            # Use orchestrator for dynamic collaboration
            orchestrator = MultiAgentOrchestrator()

            # Execute with parallel subtask handling
            result = await orchestrator.execute_task(
                task_description=task['description'],
                parameters=task.get('parameters', {})
            )

            api_calls = self.router.stats['total_requests'] - api_calls_before
            execution_time = time.time() - start_time

            # Estimate tokens from orchestrator stats
            tokens_used = orchestrator.get_token_usage()

            metric = ExecutionMetrics(
                mode="multi_agent",
                task_id=task_id,
                success=True,
                execution_time=execution_time,
                api_calls=api_calls,
                tokens_used=tokens_used
            )

            self.results.multi_agent.append(metric)
            self.logger.info(f"[Multi-Agent] ✓ Completed in {execution_time:.2f}s")

            return metric

        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"[Multi-Agent] ✗ Failed: {e}")

            metric = ExecutionMetrics(
                mode="multi_agent",
                task_id=task_id,
                success=False,
                execution_time=execution_time,
                error=str(e)
            )

            self.results.multi_agent.append(metric)
            return metric

    async def run_comparison(self, tasks: List[Dict]) -> ComparisonResults:
        """
        Run all three modes on the same tasks and compare

        Args:
            tasks: List of tasks to run
        """
        self.logger.info(f"Starting comparison with {len(tasks)} tasks")

        for task in tasks:
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"Task: {task['description']}")
            self.logger.info(f"{'='*60}\n")

            # Run all three modes
            await self.run_single_agent(task)
            await asyncio.sleep(0.5)  # Small delay between modes

            await self.run_fixed_pipeline(task)
            await asyncio.sleep(0.5)

            await self.run_multi_agent(task)
            await asyncio.sleep(1)  # Delay between tasks

        return self.results

    def print_results(self):
        """Print comparison results"""
        summary = self.results.get_summary()

        print("\n" + "="*80)
        print(" "*25 + "AGENT COMPARISON RESULTS")
        print("="*80 + "\n")

        modes = [
            ("Single Agent", summary["single_agent"]),
            ("Fixed Pipeline", summary["fixed_pipeline"]),
            ("Multi-Agent", summary["multi_agent"])
        ]

        for mode_name, stats in modes:
            print(f"{'='*80}")
            print(f" {mode_name}")
            print(f"{'='*80}")
            print(f"  Tasks:          {stats['count']}")
            print(f"  Success Rate:   {stats['success_rate']:.1f}%")
            print(f"  Avg Time:       {stats['avg_time']:.2f}s")
            print(f"  Min/Max Time:   {stats['min_time']:.2f}s / {stats['max_time']:.2f}s")
            print(f"  API Calls:      {stats['total_api_calls']}")
            print(f"  Tokens Used:    {stats['total_tokens']:,}")
            print(f"  Cost Estimate:  ${stats['cost_estimate']:.4f}")
            print()

        # Comparison
        print(f"{'='*80}")
        print(" Comparison (vs Single Agent)")
        print(f"{'='*80}")

        single = summary["single_agent"]

        for mode_name, stats in [("Fixed Pipeline", summary["fixed_pipeline"]),
                                  ("Multi-Agent", summary["multi_agent"])]:
            if single['count'] > 0:
                time_diff = ((stats['avg_time'] - single['avg_time']) / single['avg_time'] * 100)
                cost_diff = ((stats['cost_estimate'] - single['cost_estimate']) / single['cost_estimate'] * 100) if single['cost_estimate'] > 0 else 0

                print(f"\n  {mode_name}:")
                print(f"    Time:  {time_diff:+.1f}%")
                print(f"    Cost:  {cost_diff:+.1f}%")
                print(f"    Success: {stats['success_rate']:.1f}% (vs {single['success_rate']:.1f}%)")

        print("\n" + "="*80 + "\n")

    def save_results(self, filename: str = "comparison_results.json"):
        """Save results to JSON file"""
        with open(filename, 'w') as f:
            json.dump({
                "summary": self.results.get_summary(),
                "single_agent": [m.to_dict() for m in self.results.single_agent],
                "fixed_pipeline": [m.to_dict() for m in self.results.fixed_pipeline],
                "multi_agent": [m.to_dict() for m in self.results.multi_agent]
            }, f, indent=2)

        self.logger.info(f"Results saved to {filename}")
