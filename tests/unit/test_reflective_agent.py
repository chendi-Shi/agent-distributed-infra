"""
ReflectiveAgent 单元测试
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
import json

from src.agents.reflective_agent import (
    ReflectiveAgent,
    SubTask,
    SubTaskStatus,
    SystemState,
    ReflectionResult,
)


@pytest.fixture
def mock_llm():
    """Mock LLM 客户端"""
    llm = AsyncMock()
    return llm


@pytest.fixture
def system_state():
    """正常系统状态"""
    return SystemState(
        queue_length=5,
        cpu_utilization=0.6,
        memory_usage=0.5,
        recent_success_rate=0.9,
        avg_execution_time=8.0,
    )


@pytest.fixture
def overloaded_state():
    """过载系统状态"""
    return SystemState(
        queue_length=15,
        cpu_utilization=0.95,
        memory_usage=0.9,
        recent_success_rate=0.6,
        avg_execution_time=20.0,
    )


class TestSystemState:
    """测试系统状态"""

    def test_is_overloaded(self, overloaded_state):
        assert overloaded_state.is_overloaded() is True

    def test_is_not_overloaded(self, system_state):
        assert system_state.is_overloaded() is False

    def test_is_idle(self):
        idle_state = SystemState(
            queue_length=2,
            cpu_utilization=0.3,
            memory_usage=0.4,
            recent_success_rate=0.95,
            avg_execution_time=5.0,
        )
        assert idle_state.is_idle() is True


class TestReflectiveAgent:
    """测试反思型 Agent"""

    @pytest.mark.asyncio
    async def test_initial_plan(self, mock_llm, system_state):
        """测试初始规划"""
        mock_llm.generate.return_value = json.dumps([
            {"id": "1", "description": "分析需求", "dependencies": []},
            {"id": "2", "description": "设计方案", "dependencies": ["1"]},
        ])

        agent = ReflectiveAgent(mock_llm)
        subtasks = await agent._initial_plan("测试任务", system_state)

        assert len(subtasks) == 2
        assert subtasks[0].id == "1"
        assert subtasks[1].dependencies == ["1"]

    @pytest.mark.asyncio
    async def test_get_next_executable(self, mock_llm):
        """测试获取下一个可执行任务"""
        agent = ReflectiveAgent(mock_llm)

        subtasks = [
            SubTask(id="1", description="任务1", status=SubTaskStatus.SUCCESS),
            SubTask(id="2", description="任务2", dependencies=["1"]),
            SubTask(id="3", description="任务3", dependencies=["2"]),
        ]

        next_task = agent._get_next_executable(subtasks)
        assert next_task.id == "2"

        # 标记任务2完成
        subtasks[1].status = SubTaskStatus.SUCCESS
        next_task = agent._get_next_executable(subtasks)
        assert next_task.id == "3"

    @pytest.mark.asyncio
    async def test_execute_subtask_success(self, mock_llm):
        """测试子任务执行成功"""
        mock_llm.generate.return_value = "执行成功"

        agent = ReflectiveAgent(mock_llm)
        subtask = SubTask(id="1", description="测试任务")

        await agent._execute_subtask(subtask)

        assert subtask.status == SubTaskStatus.SUCCESS
        assert subtask.result == "执行成功"
        assert subtask.start_time is not None
        assert subtask.end_time is not None

    @pytest.mark.asyncio
    async def test_execute_subtask_failure(self, mock_llm):
        """测试子任务执行失败"""
        mock_llm.generate.side_effect = Exception("执行错误")

        agent = ReflectiveAgent(mock_llm)
        subtask = SubTask(id="1", description="测试任务")

        await agent._execute_subtask(subtask)

        assert subtask.status == SubTaskStatus.FAILED
        assert "执行错误" in subtask.error

    @pytest.mark.asyncio
    async def test_reflect_no_replan(self, mock_llm, system_state):
        """测试反思（无需重新规划）"""
        mock_llm.generate.return_value = json.dumps({
            "need_replan": False,
            "reason": "执行顺利",
            "actions": []
        })

        agent = ReflectiveAgent(mock_llm)
        subtasks = [
            SubTask(id="1", description="任务1", status=SubTaskStatus.SUCCESS),
        ]

        reflection = await agent._reflect("测试任务", subtasks, system_state)

        assert reflection.need_replan is False
        assert "执行顺利" in reflection.reason

    @pytest.mark.asyncio
    async def test_reflect_with_replan(self, mock_llm, system_state):
        """测试反思（需要重新规划）"""
        mock_llm.generate.return_value = json.dumps({
            "need_replan": True,
            "reason": "发现遗漏子任务",
            "actions": ["添加新任务"],
            "new_subtasks": [
                {"id": "3", "description": "补充任务", "dependencies": []}
            ]
        })

        agent = ReflectiveAgent(mock_llm)
        subtasks = [
            SubTask(id="1", description="任务1", status=SubTaskStatus.SUCCESS),
        ]

        reflection = await agent._reflect("测试任务", subtasks, system_state)

        assert reflection.need_replan is True
        assert len(reflection.new_subtasks) == 1
        assert reflection.new_subtasks[0].id == "3"

    @pytest.mark.asyncio
    async def test_apply_replan_add_tasks(self, mock_llm):
        """测试应用重新规划（添加任务）"""
        agent = ReflectiveAgent(mock_llm)
        subtasks = [
            SubTask(id="1", description="任务1"),
        ]

        reflection = ReflectionResult(
            need_replan=True,
            reason="添加任务",
            actions=[],
            new_subtasks=[
                SubTask(id="2", description="新任务")
            ]
        )

        agent._apply_replan(subtasks, reflection)

        assert len(subtasks) == 2
        assert subtasks[1].id == "2"

    @pytest.mark.asyncio
    async def test_apply_replan_remove_tasks(self, mock_llm):
        """测试应用重新规划（删除任务）"""
        agent = ReflectiveAgent(mock_llm)
        subtasks = [
            SubTask(id="1", description="任务1"),
            SubTask(id="2", description="任务2"),
        ]

        reflection = ReflectionResult(
            need_replan=True,
            reason="删除任务",
            actions=[],
            remove_subtask_ids=["2"]
        )

        agent._apply_replan(subtasks, reflection)

        assert len(subtasks) == 1
        assert subtasks[0].id == "1"

    @pytest.mark.asyncio
    async def test_apply_replan_modify_tasks(self, mock_llm):
        """测试应用重新规划（修改任务）"""
        agent = ReflectiveAgent(mock_llm)
        subtasks = [
            SubTask(id="1", description="原始描述"),
        ]

        reflection = ReflectionResult(
            need_replan=True,
            reason="修改任务",
            actions=[],
            modify_subtasks={"1": "新描述"}
        )

        agent._apply_replan(subtasks, reflection)

        assert subtasks[0].description == "新描述"

    @pytest.mark.asyncio
    async def test_deadlock_detection(self, mock_llm, system_state):
        """测试死锁检测"""
        mock_llm.generate.return_value = json.dumps({
            "need_replan": True,
            "reason": "检测到依赖死锁",
            "actions": ["remove_all_dependencies"]
        })

        agent = ReflectiveAgent(mock_llm)
        subtasks = [
            SubTask(id="1", description="任务1", status=SubTaskStatus.FAILED),
            SubTask(id="2", description="任务2", dependencies=["1"]),  # 依赖失败任务
        ]

        reflection = await agent._reflect_on_deadlock(
            "测试任务", subtasks, system_state
        )

        assert reflection.need_replan is True
        assert "remove_all_dependencies" in reflection.actions

    def test_all_done(self, mock_llm):
        """测试任务是否全部完成"""
        agent = ReflectiveAgent(mock_llm)

        # 全部完成
        subtasks = [
            SubTask(id="1", description="任务1", status=SubTaskStatus.SUCCESS),
            SubTask(id="2", description="任务2", status=SubTaskStatus.SUCCESS),
        ]
        assert agent._all_done(subtasks) is True

        # 有待执行
        subtasks.append(SubTask(id="3", description="任务3"))
        assert agent._all_done(subtasks) is False

    def test_has_pending(self, mock_llm):
        """测试是否有待执行任务"""
        agent = ReflectiveAgent(mock_llm)

        subtasks = [
            SubTask(id="1", description="任务1", status=SubTaskStatus.SUCCESS),
            SubTask(id="2", description="任务2"),
        ]
        assert agent._has_pending(subtasks) is True

        subtasks[1].status = SubTaskStatus.SUCCESS
        assert agent._has_pending(subtasks) is False

    @pytest.mark.asyncio
    async def test_full_execution_flow(self, mock_llm, system_state):
        """测试完整执行流程"""
        # Mock 初始规划
        mock_llm.generate.side_effect = [
            # 初始规划
            json.dumps([
                {"id": "1", "description": "任务1", "dependencies": []},
                {"id": "2", "description": "任务2", "dependencies": ["1"]},
            ]),
            # 执行任务1
            "任务1完成",
            # 第一次反思（无需调整）
            json.dumps({"need_replan": False, "reason": "顺利", "actions": []}),
            # 执行任务2
            "任务2完成",
            # 第二次反思（完成）
            json.dumps({"need_replan": False, "reason": "完成", "actions": []}),
            # 最终反思
            json.dumps({"need_replan": False, "reason": "全部完成", "actions": []}),
        ]

        agent = ReflectiveAgent(mock_llm, reflection_interval=1)
        result = await agent.execute_task("测试任务", system_state)

        assert result["success"] is True
        assert len(result["subtasks"]) == 2
        assert result["reflections"]
        assert result["reflection_count"] == 0  # 无需重新规划


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
