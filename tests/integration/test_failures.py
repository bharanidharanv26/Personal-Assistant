import asyncio

import pytest
from sqlalchemy import select

from nila.automation.tools import ToolRegistry
from nila.core.errors import DomainError
from nila.core.runtime import build_services
from nila.core.schemas import ChatRequest, DryRunArguments, PlanDraft, PlanStep, TaskRequest
from nila.llm.providers import DemoProvider
from nila.storage.models import Episode


class FailingProvider(DemoProvider):
    async def chat(self, prompt):
        raise RuntimeError("sensitive-provider-details")

    async def plan(self, prompt):
        raise RuntimeError("sensitive-provider-details")


async def test_provider_failures_leave_inspectable_state(config):
    runtime = build_services(config, provider=FailingProvider())
    try:
        with pytest.raises(DomainError) as failure:
            await runtime.tasks.plan(TaskRequest(objective="a task"))
        assert "sensitive-provider-details" not in failure.value.detail
        task = runtime.tasks.get(failure.value.resource_id)
        assert task.status == "failed"
        assert task.actions == []
        with pytest.raises(DomainError):
            await runtime.chat.chat(ChatRequest(message="hello"))
        with runtime.db.sessions() as session:
            assert all(episode.status == "failed" for episode in session.scalars(select(Episode)))
    finally:
        await runtime.close()


class TwoStepProvider(DemoProvider):
    async def plan(self, prompt):
        return PlanDraft(title="Two steps", steps=[
            PlanStep(tool="dry_run", arguments=DryRunArguments(description="first")),
            PlanStep(tool="dry_run", arguments=DryRunArguments(description="second")),
        ])


async def test_step_budget_blocks_plan_before_any_actions_exist(config):
    config.max_steps = 1
    runtime = build_services(config, provider=TwoStepProvider())
    try:
        with pytest.raises(DomainError):
            await runtime.tasks.plan(TaskRequest(objective="two steps"))
        assert runtime.tasks.list()[0].actions == []
    finally:
        await runtime.close()


class FailingTools(ToolRegistry):
    async def execute(self, tool, arguments):
        raise RuntimeError("tool internals must not be exposed")


async def test_tool_failure_consumes_approval_and_stops_task(config):
    runtime = build_services(config, tools=FailingTools())
    try:
        task = await runtime.tasks.plan(TaskRequest(objective="a task"))
        action = task.actions[0]
        runtime.permissions.approve(action.id, action.digest)
        with pytest.raises(DomainError, match="Tool execution failed"):
            await runtime.executor.execute(action.id)
        assert runtime.tasks.get(task.id).status == "failed"
        with pytest.raises(DomainError):
            await runtime.executor.execute(action.id)
    finally:
        await runtime.close()


class BlockingTools(ToolRegistry):
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def execute(self, tool, arguments):
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return await super().execute(tool, arguments)


async def test_cancellation_between_steps_blocks_remaining_actions(config):
    tools = BlockingTools()
    runtime = build_services(config, provider=TwoStepProvider(), tools=tools)
    try:
        task = await runtime.tasks.plan(TaskRequest(objective="two steps"))
        for action in task.actions:
            runtime.permissions.approve(action.id, action.digest)
        execution = asyncio.create_task(runtime.executor.run_task(task.id))
        await asyncio.wait_for(tools.entered.wait(), timeout=2)
        runtime.tasks.cancel(task.id)
        tools.release.set()
        with pytest.raises(DomainError):
            await execution
        assert tools.calls == 1
        final = runtime.tasks.get(task.id)
        assert final.status == "cancelled"
        assert final.actions[0].status == "succeeded"
        assert final.actions[1].status == "cancelled"
    finally:
        tools.release.set()
        await runtime.close()


async def test_timeout_marks_outcome_interrupted_and_blocks_replay(config):
    config.task_timeout_seconds = 1
    runtime = build_services(config, tools=BlockingTools())
    try:
        task = await runtime.tasks.plan(TaskRequest(objective="slow task"))
        action = task.actions[0]
        runtime.permissions.approve(action.id, action.digest)
        with pytest.raises(DomainError, match="Tool timed out"):
            await runtime.executor.execute(action.id)
        assert runtime.tasks.get(task.id).status == "interrupted"
        with pytest.raises(DomainError):
            await runtime.executor.execute(action.id)
    finally:
        await runtime.close()
