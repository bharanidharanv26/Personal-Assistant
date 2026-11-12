import asyncio
import time

import pytest
from sqlalchemy import select

from nila.automation.tools import ToolRegistry
from nila.core.errors import DomainError
from nila.core.runtime import build_services
from nila.core.schemas import ConsentRequest, ObservationRequest, TaskRequest
from nila.storage.models import Action, Approval, Consent, Episode, Task


async def planned(runtime):
    task = await runtime.tasks.plan(TaskRequest(objective="Simulate a tea break"))
    return task, task.actions[0]


async def test_unapproved_and_replayed_actions_cannot_execute(runtime):
    task, action = await planned(runtime)
    with pytest.raises(DomainError, match="unused approval"):
        await runtime.executor.execute(action.id)
    runtime.permissions.approve(action.id, action.digest)
    await runtime.executor.execute(action.id)
    assert runtime.tasks.get(task.id).status == "succeeded"
    with pytest.raises(DomainError):
        await runtime.executor.execute(action.id)
    with pytest.raises(DomainError):
        runtime.permissions.approve(action.id, action.digest)


async def test_expired_approval_can_only_run_after_fresh_approval(runtime):
    _, action = await planned(runtime)
    runtime.permissions.approve(action.id, action.digest)
    with runtime.db.transaction() as session:
        approval = session.scalar(select(Approval).where(Approval.action_id == action.id))
        approval.expires_at = time.time() - 1
    with pytest.raises(DomainError, match="expired"):
        await runtime.executor.execute(action.id)
    assert runtime.executor.get_action(action.id).status == "expired"
    runtime.permissions.approve(action.id, action.digest)
    assert (await runtime.executor.execute(action.id)).result["simulated"] is True


@pytest.mark.parametrize("change", ["arguments", "tool", "revision", "position"])
async def test_altered_action_invalidates_approval(runtime, change):
    task, action = await planned(runtime)
    runtime.permissions.approve(action.id, action.digest)
    with runtime.db.transaction() as session:
        stored = session.get(Action, action.id)
        if change == "arguments":
            stored.arguments = {"description": "a different action"}
        elif change == "tool":
            stored.tool = "unregistered_shell"
        elif change == "position":
            stored.position += 1
        else:
            session.get(Task, task.id).revision += 1
    with pytest.raises(DomainError, match="changed after approval"):
        await runtime.executor.execute(action.id)
    assert runtime.executor.get_action(action.id).status == "invalid"


@pytest.mark.parametrize("decision", ["deny", "revoke", "cancel"])
async def test_refused_or_cancelled_action_cannot_execute(runtime, decision):
    task, action = await planned(runtime)
    if decision != "deny":
        runtime.permissions.approve(action.id, action.digest)
    if decision == "cancel":
        runtime.tasks.cancel(task.id)
    else:
        runtime.permissions.refuse(action.id, revoke=decision == "revoke")
    with pytest.raises(DomainError):
        await runtime.executor.execute(action.id)
    assert runtime.tasks.get(task.id).status == "cancelled"


class SlowTools(ToolRegistry):
    def __init__(self):
        self.calls = 0

    async def execute(self, tool, arguments):
        self.calls += 1
        await asyncio.sleep(0.05)
        return await super().execute(tool, arguments)


async def test_concurrent_requests_consume_approval_once(config):
    tools = SlowTools()
    runtime = build_services(config, tools=tools)
    try:
        _, action = await planned(runtime)
        runtime.permissions.approve(action.id, action.digest)
        results = await asyncio.gather(
            runtime.executor.execute(action.id), runtime.executor.execute(action.id),
            return_exceptions=True,
        )
        assert sum(isinstance(result, DomainError) for result in results) == 1
        assert tools.calls == 1
    finally:
        await runtime.close()


async def test_restart_marks_unknown_execution_interrupted(config):
    runtime = build_services(config)
    task, action = await planned(runtime)
    runtime.permissions.approve(action.id, action.digest)
    with runtime.db.transaction() as session:
        session.get(Action, action.id).status = "running"
        session.get(Task, task.id).status = "running"
        approval = session.scalar(select(Approval).where(Approval.action_id == action.id))
        approval.consumed_at = time.time()
        session.add(Episode(
            kind="action", resource_id=action.id, status="running", provider="dry_run"
        ))
    await runtime.close()
    restarted = build_services(config)
    try:
        assert restarted.tasks.get(task.id).status == "interrupted"
        assert restarted.executor.get_action(action.id).status == "interrupted"
        with pytest.raises(DomainError):
            await restarted.executor.execute(action.id)
        with restarted.db.sessions() as session:
            assert session.scalar(select(Episode).where(
                Episode.kind == "action"
            )).status == "interrupted"
    finally:
        await restarted.close()


@pytest.mark.parametrize("invalidity", ["revoked", "expired", "wrong_scope"])
async def test_observation_requires_active_scoped_consent(runtime, invalidity):
    consent = runtime.permissions.grant_consent(ConsentRequest())
    runtime.observations.create(ObservationRequest(consent_id=consent.id, content="Manual note"))
    if invalidity == "revoked":
        runtime.permissions.revoke_consent(consent.id)
    else:
        with runtime.db.transaction() as session:
            stored = session.get(Consent, consent.id)
            if invalidity == "expired":
                stored.expires_at = time.time() - 1
            else:
                stored.scope = "something_else"
    with pytest.raises(DomainError, match="consent is required"):
        runtime.observations.create(ObservationRequest(consent_id=consent.id, content="Blocked"))
    assert len(runtime.observations.list()) == 1
