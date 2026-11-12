import asyncio

import pytest
from sqlalchemy import func, select

from nila.automation.tools import ToolRegistry
from nila.core.errors import DomainError
from nila.core.runtime import build_services
from nila.core.schemas import DryRunArguments, PlanDraft, PlanStep, TaskRequest
from nila.llm.providers import DemoProvider
from nila.storage.models import Action, Approval, Episode


class GatedTools(ToolRegistry):
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, tool, arguments):
        self.entered.set()
        await self.release.wait()
        return await super().execute(tool, arguments)


class SlowTools(ToolRegistry):
    def __init__(self):
        self.calls = 0

    async def execute(self, tool, arguments):
        self.calls += 1
        await asyncio.sleep(0.05)
        return await super().execute(tool, arguments)


class TwoStepProvider(DemoProvider):
    async def plan(self, prompt):
        return PlanDraft(title="Two steps", steps=[
            PlanStep(tool="dry_run", arguments=DryRunArguments(description="first")),
            PlanStep(tool="dry_run", arguments=DryRunArguments(description="second")),
        ])


async def test_claim_is_committed_before_the_tool_runs(config):
    tools = GatedTools()
    runtime = build_services(config, tools=tools)
    try:
        task = await runtime.tasks.plan(TaskRequest(objective="gated action"))
        action = task.actions[0]
        runtime.permissions.approve(action.id, action.digest)
        execution = asyncio.create_task(runtime.executor.execute(action.id))
        await asyncio.wait_for(tools.entered.wait(), timeout=2)

        with runtime.db.sessions() as session:
            stored = session.get(Action, action.id)
            approval = session.scalar(select(Approval).where(Approval.action_id == action.id))
            episodes = session.scalar(
                select(func.count()).select_from(Episode).where(
                    Episode.kind == "action", Episode.resource_id == action.id
                )
            )
            assert stored is not None and stored.status == "running"
            assert approval is not None and approval.consumed_at is not None
            assert episodes == 1

        tools.release.set()
        assert (await execution).status == "succeeded"
    finally:
        tools.release.set()
        await runtime.close()


async def test_independent_services_consume_an_approval_once(config):
    tools = SlowTools()
    first = build_services(config, tools=tools)
    second = build_services(config, tools=tools)
    try:
        task = await first.tasks.plan(TaskRequest(objective="race"))
        action = task.actions[0]
        first.permissions.approve(action.id, action.digest)
        results = await asyncio.gather(
            first.executor.execute(action.id),
            second.executor.execute(action.id),
            return_exceptions=True,
        )
        assert sum(isinstance(result, DomainError) for result in results) == 1
        assert tools.calls == 1
        assert first.tasks.get(task.id).status == "succeeded"
    finally:
        await first.close()
        await second.close()


async def test_actions_must_execute_in_plan_order(config):
    runtime = build_services(config, provider=TwoStepProvider())
    try:
        task = await runtime.tasks.plan(TaskRequest(objective="ordered"))
        for action in task.actions:
            runtime.permissions.approve(action.id, action.digest)
        with pytest.raises(DomainError, match="Earlier steps"):
            await runtime.executor.execute(task.actions[1].id)
        assert (await runtime.executor.execute(task.actions[0].id)).status == "succeeded"
        assert (await runtime.executor.execute(task.actions[1].id)).status == "succeeded"
    finally:
        await runtime.close()


async def test_recovery_blocks_a_stale_completion(config):
    tools = GatedTools()
    first = build_services(config, tools=tools)
    second = None
    try:
        task = await first.tasks.plan(TaskRequest(objective="stale completion"))
        action = task.actions[0]
        first.permissions.approve(action.id, action.digest)
        execution = asyncio.create_task(first.executor.execute(action.id))
        await asyncio.wait_for(tools.entered.wait(), timeout=2)

        second = build_services(config)
        tools.release.set()

        with pytest.raises(DomainError, match="no longer current"):
            await execution
        assert first.tasks.get(task.id).status == "interrupted"
        assert first.executor.get_action(action.id).status == "interrupted"
    finally:
        tools.release.set()
        if second is not None:
            await second.close()
        await first.close()
