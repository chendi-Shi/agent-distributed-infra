"""
ReAct + 反思机制的 Agent

核心算法：
1. Plan（规划）：LLM 分解任务为初始子任务列表
2. Act（执行）：执行当前子任务
3. Observe（观察）：检查执行结果和系统状态
4. Reflect（反思）：判断是否需要调整计划
5. Replan（重新规划）：动态插入/删除/修改子任务
6. Loop：重复 2-5 直到完成

与传统分解的区别：
- 传统：分解 → 全部执行 → 结束
- ReAct：分解 → 执行一步 → 反思 → 调整 → 执行下一步 → ...
"""

import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import time
import json


class SubTaskStatus(Enum):
    """子任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SubTask:
    """子任务"""
    id: str
    description: str
    status: SubTaskStatus = SubTaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    dependencies: List[str] = field(default_factory=list)
    retry_count: int = 0


@dataclass
class ReflectionResult:
    """反思结果"""
    need_replan: bool  # 是否需要重新规划
    reason: str  # 反思理由
    actions: List[str]  # 建议的调整动作
    new_subtasks: List[SubTask] = field(default_factory=list)  # 新增子任务
    remove_subtask_ids: List[str] = field(default_factory=list)  # 删除子任务
    modify_subtasks: Dict[str, str] = field(default_factory=dict)  # 修改子任务 {id: new_description}


@dataclass
class SystemState:
    """系统状态"""
    queue_length: int
    cpu_utilization: float
    memory_usage: float
    recent_success_rate: float
    avg_execution_time: float

    def is_overloaded(self) -> bool:
        """系统是否过载"""
        return (
            self.queue_length > 10 or
            self.cpu_utilization > 0.9 or
            self.memory_usage > 0.85
        )

    def is_idle(self) -> bool:
        """系统是否空闲"""
        return (
            self.queue_length < 3 and
            self.cpu_utilization < 0.5
        )


class ReflectiveAgent:
    """
    反思型 Agent

    核心能力：
    1. 动态调整计划：根据执行结果修改后续步骤
    2. 错误恢复：失败时自动重新规划
    3. 资源感知：根据系统负载调整并行度
    4. 依赖管理：动态添加/删除子任务依赖
    """

    def __init__(
        self,
        llm_client,
        max_reflections: int = 5,  # 最大反思次数
        reflection_interval: int = 1,  # 每执行几个子任务反思一次
    ):
        self.llm = llm_client
        self.max_reflections = max_reflections
        self.reflection_interval = reflection_interval

        self.reflection_count = 0
        self.execution_history: List[Dict] = []

    async def execute_task(
        self,
        task_description: str,
        system_state: SystemState,
    ) -> Dict:
        """
        执行任务（主入口）

        Returns:
            {
                "success": bool,
                "result": str,
                "subtasks": List[SubTask],
                "reflections": List[ReflectionResult],
                "total_time": float,
            }
        """
        start_time = time.time()

        # 1. 初始规划
        subtasks = await self._initial_plan(task_description, system_state)

        reflections = []
        completed_count = 0

        # 2. 执行-反思循环
        while not self._all_done(subtasks):
            # 2.1 执行下一个可执行的子任务
            next_task = self._get_next_executable(subtasks)

            if next_task is None:
                # 没有可执行的任务（可能都在等待依赖）
                if self._has_pending(subtasks):
                    # 有待执行但依赖未满足 → 可能死锁
                    reflection = await self._reflect_on_deadlock(
                        task_description, subtasks, system_state
                    )
                    reflections.append(reflection)

                    if reflection.need_replan:
                        self._apply_replan(subtasks, reflection)
                    else:
                        break  # 无法恢复，退出
                else:
                    break  # 全部完成或失败
            else:
                # 执行子任务
                await self._execute_subtask(next_task)
                completed_count += 1

                # 2.2 定期反思
                if completed_count % self.reflection_interval == 0:
                    reflection = await self._reflect(
                        task_description, subtasks, system_state
                    )
                    reflections.append(reflection)

                    if reflection.need_replan:
                        self._apply_replan(subtasks, reflection)
                        self.reflection_count += 1

                        if self.reflection_count >= self.max_reflections:
                            break  # 防止无限反思

        # 3. 最终反思
        final_reflection = await self._final_reflect(task_description, subtasks)
        reflections.append(final_reflection)

        total_time = time.time() - start_time

        success = all(
            t.status in [SubTaskStatus.SUCCESS, SubTaskStatus.SKIPPED]
            for t in subtasks
        )

        result = self._aggregate_results(subtasks) if success else "Task failed"

        return {
            "success": success,
            "result": result,
            "subtasks": subtasks,
            "reflections": reflections,
            "total_time": total_time,
            "reflection_count": self.reflection_count,
        }

    async def _initial_plan(
        self, task_description: str, system_state: SystemState
    ) -> List[SubTask]:
        """初始规划"""
        prompt = f"""
任务：{task_description}

系统状态：
- 队列长度：{system_state.queue_length}
- CPU 利用率：{system_state.cpu_utilization:.1%}
- 内存使用：{system_state.memory_usage:.1%}
- 最近成功率：{system_state.recent_success_rate:.1%}

请将任务分解为 3-7 个子任务，格式：
[
  {{"id": "1", "description": "...", "dependencies": []}},
  {{"id": "2", "description": "...", "dependencies": ["1"]}},
  ...
]

要求：
1. 子任务应该具体可执行
2. 合理设置依赖关系
3. 考虑系统负载（当前{'过载' if system_state.is_overloaded() else '正常'}）
4. 粒度适中（每个子任务 5-30 秒）
"""

        response = await self.llm.generate(prompt)

        # 解析 LLM 输出（简化，实际需要更健壮的解析）
        try:
            parsed = json.loads(response)
            subtasks = [
                SubTask(
                    id=item["id"],
                    description=item["description"],
                    dependencies=item.get("dependencies", [])
                )
                for item in parsed
            ]
            return subtasks
        except:
            # 解析失败，返回简单分解
            return [
                SubTask(id="1", description=task_description)
            ]

    def _get_next_executable(self, subtasks: List[SubTask]) -> Optional[SubTask]:
        """获取下一个可执行的子任务（依赖已满足）"""
        for task in subtasks:
            if task.status != SubTaskStatus.PENDING:
                continue

            # 检查依赖是否全部完成
            deps_satisfied = all(
                any(t.id == dep_id and t.status == SubTaskStatus.SUCCESS for t in subtasks)
                for dep_id in task.dependencies
            )

            if deps_satisfied:
                return task

        return None

    async def _execute_subtask(self, subtask: SubTask):
        """执行单个子任务"""
        subtask.status = SubTaskStatus.RUNNING
        subtask.start_time = time.time()

        try:
            # 调用实际执行逻辑（这里简化为 LLM 生成）
            prompt = f"执行子任务：{subtask.description}\n请给出执行结果。"
            result = await self.llm.generate(prompt)

            subtask.status = SubTaskStatus.SUCCESS
            subtask.result = result
        except Exception as e:
            subtask.status = SubTaskStatus.FAILED
            subtask.error = str(e)
        finally:
            subtask.end_time = time.time()

    async def _reflect(
        self,
        task_description: str,
        subtasks: List[SubTask],
        system_state: SystemState,
    ) -> ReflectionResult:
        """
        反思：检查执行情况，决定是否调整计划

        反思维度：
        1. 执行结果：是否符合预期
        2. 系统负载：是否需要调整并行度
        3. 依赖关系：是否有遗漏或错误
        4. 任务覆盖：是否有遗漏的子任务
        """
        # 统计当前状态
        total = len(subtasks)
        success = sum(1 for t in subtasks if t.status == SubTaskStatus.SUCCESS)
        failed = sum(1 for t in subtasks if t.status == SubTaskStatus.FAILED)
        pending = sum(1 for t in subtasks if t.status == SubTaskStatus.PENDING)

        # 构造反思提示
        subtask_summary = "\n".join([
            f"- [{t.status.value}] {t.id}: {t.description}"
            + (f" (错误: {t.error})" if t.error else "")
            for t in subtasks
        ])

        prompt = f"""
原始任务：{task_description}

当前执行情况（{success}/{total} 成功，{failed} 失败，{pending} 待执行）：
{subtask_summary}

系统状态：
- 队列长度：{system_state.queue_length}
- CPU 利用率：{system_state.cpu_utilization:.1%}
- {'⚠️ 系统过载' if system_state.is_overloaded() else '✅ 系统正常'}

请反思以下问题：
1. 执行结果是否符合预期？
2. 是否有子任务失败需要重试或替代方案？
3. 剩余子任务是否足够完成原始任务？
4. 是否需要根据系统负载调整并行度？
5. 依赖关系是否合理？

如果需要调整计划，请给出：
{{
  "need_replan": true/false,
  "reason": "反思理由",
  "actions": ["动作1", "动作2"],
  "new_subtasks": [{{"id": "...", "description": "...", "dependencies": []}}],
  "remove_subtask_ids": ["..."],
  "modify_subtasks": {{"id": "新描述"}}
}}

如果无需调整：
{{
  "need_replan": false,
  "reason": "执行顺利，继续执行"
}}
"""

        response = await self.llm.generate(prompt)

        # 解析反思结果
        try:
            parsed = json.loads(response)
            return ReflectionResult(
                need_replan=parsed["need_replan"],
                reason=parsed["reason"],
                actions=parsed.get("actions", []),
                new_subtasks=[
                    SubTask(**item) for item in parsed.get("new_subtasks", [])
                ],
                remove_subtask_ids=parsed.get("remove_subtask_ids", []),
                modify_subtasks=parsed.get("modify_subtasks", {}),
            )
        except:
            # 解析失败，默认不重新规划
            return ReflectionResult(
                need_replan=False,
                reason="反思解析失败，继续执行",
                actions=[],
            )

    async def _reflect_on_deadlock(
        self,
        task_description: str,
        subtasks: List[SubTask],
        system_state: SystemState,
    ) -> ReflectionResult:
        """死锁反思：有待执行任务但依赖未满足"""
        pending_tasks = [t for t in subtasks if t.status == SubTaskStatus.PENDING]

        prompt = f"""
⚠️ 检测到可能的死锁：

任务：{task_description}

待执行的子任务（依赖未满足）：
{chr(10).join([f"- {t.id}: {t.description} (依赖: {t.dependencies})" for t in pending_tasks])}

已完成的子任务：
{chr(10).join([f"- {t.id}: {t.description}" for t in subtasks if t.status == SubTaskStatus.SUCCESS])}

失败的子任务：
{chr(10).join([f"- {t.id}: {t.description} ({t.error})" for t in subtasks if t.status == SubTaskStatus.FAILED])}

请分析：
1. 为什么会出现死锁？
2. 如何打破死锁（移除依赖、跳过失败任务、重试等）？

给出调整方案（JSON）。
"""

        response = await self.llm.generate(prompt)

        try:
            parsed = json.loads(response)
            return ReflectionResult(**parsed)
        except:
            # 默认：移除所有依赖，强行执行
            return ReflectionResult(
                need_replan=True,
                reason="死锁，移除依赖关系",
                actions=["remove_all_dependencies"],
            )

    async def _final_reflect(
        self, task_description: str, subtasks: List[SubTask]
    ) -> ReflectionResult:
        """最终反思：评估整体完成质量"""
        prompt = f"""
任务：{task_description}

最终执行结果：
{chr(10).join([f"- [{t.status.value}] {t.id}: {t.description}" for t in subtasks])}

请评估：
1. 任务是否完整完成？
2. 结果质量如何？
3. 有哪些可以改进的地方？

给出最终反思（JSON，need_replan 应为 false）。
"""

        response = await self.llm.generate(prompt)

        try:
            parsed = json.loads(response)
            parsed["need_replan"] = False  # 强制不重新规划
            return ReflectionResult(**parsed)
        except:
            return ReflectionResult(
                need_replan=False,
                reason="任务执行完毕",
                actions=[],
            )

    def _apply_replan(self, subtasks: List[SubTask], reflection: ReflectionResult):
        """应用重新规划"""
        # 1. 删除子任务
        for remove_id in reflection.remove_subtask_ids:
            subtasks[:] = [t for t in subtasks if t.id != remove_id]

        # 2. 修改子任务
        for task_id, new_desc in reflection.modify_subtasks.items():
            for task in subtasks:
                if task.id == task_id:
                    task.description = new_desc

        # 3. 添加新子任务
        subtasks.extend(reflection.new_subtasks)

        # 4. 特殊动作
        if "remove_all_dependencies" in reflection.actions:
            for task in subtasks:
                task.dependencies = []

    def _all_done(self, subtasks: List[SubTask]) -> bool:
        """是否全部完成"""
        return all(
            t.status in [SubTaskStatus.SUCCESS, SubTaskStatus.FAILED, SubTaskStatus.SKIPPED]
            for t in subtasks
        )

    def _has_pending(self, subtasks: List[SubTask]) -> bool:
        """是否有待执行任务"""
        return any(t.status == SubTaskStatus.PENDING for t in subtasks)

    def _aggregate_results(self, subtasks: List[SubTask]) -> str:
        """聚合结果"""
        results = [
            f"{t.id}. {t.description}\n   结果：{t.result}"
            for t in subtasks
            if t.status == SubTaskStatus.SUCCESS and t.result
        ]
        return "\n\n".join(results)


# Mock LLM Client
class MockLLMClient:
    """模拟 LLM 客户端"""
    async def generate(self, prompt: str) -> str:
        # 简单模拟
        await asyncio.sleep(0.1)

        if "分解为" in prompt or "子任务" in prompt:
            return json.dumps([
                {"id": "1", "description": "分析需求", "dependencies": []},
                {"id": "2", "description": "设计方案", "dependencies": ["1"]},
                {"id": "3", "description": "实现代码", "dependencies": ["2"]},
            ])
        elif "反思" in prompt or "调整" in prompt:
            return json.dumps({
                "need_replan": False,
                "reason": "执行顺利",
                "actions": []
            })
        else:
            return "执行完成"


# 使用示例
async def main():
    llm = MockLLMClient()
    agent = ReflectiveAgent(llm, reflection_interval=2)

    task = "设计一个支持 1M QPS 的分布式缓存系统"
    system_state = SystemState(
        queue_length=5,
        cpu_utilization=0.6,
        memory_usage=0.5,
        recent_success_rate=0.9,
        avg_execution_time=8.0,
    )

    result = await agent.execute_task(task, system_state)

    print(f"✅ 任务完成：{result['success']}")
    print(f"⏱️  总耗时：{result['total_time']:.2f}s")
    print(f"🔄 反思次数：{result['reflection_count']}")
    print(f"\n子任务执行情况：")
    for st in result['subtasks']:
        print(f"  [{st.status.value}] {st.id}: {st.description}")

    print(f"\n反思记录：")
    for i, refl in enumerate(result['reflections'], 1):
        print(f"  {i}. {refl.reason}")
        if refl.need_replan:
            print(f"     动作：{', '.join(refl.actions)}")


if __name__ == "__main__":
    asyncio.run(main())
