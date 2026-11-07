from dataclasses import replace

import pytest
from pydantic import ValidationError

from agent_pentest.ai.planner import FixedPlanner
from agent_pentest.ai.testing_agent import FixedTestingAgent
from agent_pentest.control.safety import (
    AttemptTimeout, OperationLimit, SafetyDenied, SafetySupervisor, validate_payload,
)
from agent_pentest.models.schemas import Attempt, Campaign
from worker import process_next


@pytest.fixture
def context(db, submit):
    campaign_id = submit()
    c = Campaign.model_validate(db.detail(campaign_id)["campaign"])
    a = Attempt(campaign_id=c.id, run_id="run", target_id=c.target.id, profile=c.profile)
    return c, a


def test_permit_replay_and_tampering_rejected(context):
    c, a = context
    safety = SafetySupervisor(c, a)
    permit = safety.authorize("deliver", {"body": "approved"})
    with pytest.raises(SafetyDenied):
        safety.consume(permit, "deliver", {"body": "changed"})
    with pytest.raises(SafetyDenied):
        safety.consume(replace(permit, attempt_id="foreign-attempt"), "deliver", {"body": "approved"})
    safety.consume(permit, "deliver", {"body": "approved"})
    with pytest.raises(SafetyDenied):
        safety.consume(permit, "deliver", {"body": "approved"})


def test_timeout_blocks_mutation(context):
    c, a = context
    time = [0.0]
    safety = SafetySupervisor(c, a, clock=lambda: time[0])
    permit = safety.authorize("reset", {})
    time[0] = c.scope.timeout_seconds
    with pytest.raises(AttemptTimeout):
        safety.consume(permit, "reset", {})
    assert safety.operations == 0


def test_operation_limit_and_revoke(context):
    c, a = context
    c = c.model_copy(update={"scope": c.scope.model_copy(update={"max_operations": 1})})
    safety = SafetySupervisor(c, a)
    safety.authorize_and_consume("reset", {})
    with pytest.raises(OperationLimit):
        safety.authorize("deliver", {})
    safety.revoke()
    with pytest.raises(SafetyDenied):
        safety.authorize("reset", {})


def test_arbitrary_shell_action_denied(context):
    c, a = context
    with pytest.raises(SafetyDenied):
        SafetySupervisor(c, a).authorize("shell", {"command": "anything"})


def test_payload_bindings_and_immutable_policy(context):
    c, _ = context
    plan = FixedPlanner().plan(c)
    payload = FixedTestingAgent().payload(c, plan)
    validate_payload(payload, plan, c)
    for change in ({"target_id": "external"}, {"body": "arbitrary"}, {"plan_id": "other"}):
        with pytest.raises(SafetyDenied):
            validate_payload(payload.model_copy(update=change), plan, c)
    with pytest.raises(ValidationError):
        c.scope.max_operations = 100
    with pytest.raises(ValidationError):
        type(payload).model_validate({**payload.model_dump(), "scope": "override"})


def test_budget_interrupt_records_evidence_without_false_negative(db, submit):
    original_id = submit()
    original = Campaign.model_validate(db.detail(original_id)["campaign"])
    db.finish(original_id, "SKIPPED")
    limited = original.model_copy(update={"id": "limited", "request_key": "limited",
        "scope": original.scope.model_copy(update={"max_operations": 4})})
    db.enqueue(limited, "limited")
    process_next(db)
    detail = db.detail(limited.id)
    assert detail["status"] == "BUDGET_EXCEEDED"
    assert detail["results"][0]["data"]["security_verdict"] == "INCONCLUSIVE"
    assert not detail["findings"]
    assert detail["attempts"][0]["operations"] == 4

