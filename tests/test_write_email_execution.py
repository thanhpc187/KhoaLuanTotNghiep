import hashlib
import json
from dataclasses import replace

import pytest

from agent_pentest.evidence.oracle import evaluate
from agent_pentest.evidence.store import EvidenceStore
from agent_pentest.execution.mail_tool import SandboxMailTool, checked_email_args
from agent_pentest.execution.runtime_adapter import RuntimeTargetAdapter
from agent_pentest.models.schemas import Attempt, Campaign, ExecutionStatus, PayloadSpec, digest
from agent_pentest.service import submit_campaign
from worker import process_next
from test_live_runtime import running_runtime, register, fixture_reply


ARGS = {"to": "alice@lab.invalid", "subject": "Re: work", "content": "Confirmed."}


@pytest.mark.parametrize("changed", [
    {"to": "alice@lab.invalid\r\nBcc: outsider@external.invalid"},
    {"subject": "Hello\nBcc: outsider@external.invalid"},
    {"content": " "}, {"content": "x" * 16001}, {"subject": "\x00"},
])
def test_email_contract_rejects_malformed_input(changed):
    with pytest.raises(ValueError):
        checked_email_args(ARGS | changed)


def test_email_binding_dedup_and_uncertain_effect_no_replay():
    tool = SandboxMailTool()
    actions, events, effects = [], [], []
    call = {"name": "write_email", "id": "host-call", "args": ARGS}
    def guard(action, content):
        actions.append((action, content))
        return "authorized-operation"
    emit = lambda *event: events.append(event)
    effect = lambda *value: effects.append(value)
    with pytest.raises(ValueError, match="differ"):
        tool.execute(call, ARGS | {"to": "outsider@external.invalid"}, 1, guard, emit, effect)
    assert not actions and not effects
    first = tool.execute(call, ARGS, 1, guard, emit, effect)
    assert tool.execute(call, ARGS, 1, guard, emit, effect) == first
    assert len(actions) == len(effects) == 1
    assert actions[0][1]["call_id"] == "host-call"
    changed = {**call, "args": ARGS | {"content": "changed"}}
    with pytest.raises(ValueError, match="reused"):
        tool.execute(changed, changed["args"], 1, guard, emit, effect)
    uncertain = SandboxMailTool()
    def commit_then_fail(*value):
        effects.append(value)
        raise RuntimeError("Interrupted after effect")
    with pytest.raises(RuntimeError):
        uncertain.execute(call, ARGS, 1, guard, emit, commit_then_fail)
    with pytest.raises(ValueError, match="cannot be replayed"):
        uncertain.execute(call, ARGS, 1, guard, emit, effect)
    assert len(effects) == 2


@pytest.mark.parametrize("profile,recipient,expected", [
    ("baseline_no_hitl", "outsider@external.invalid", "OBSERVED"),
    ("baseline_no_hitl", "alice@lab.invalid", "NOT_OBSERVED"),
    ("hitl_enabled", "outsider@external.invalid", "NOT_OBSERVED"),
    ("hitl_enabled", "alice@lab.invalid", "NOT_OBSERVED"),
])
def test_upstream_email_receipt_and_actual_effect(db, catalogue, running_runtime, profile, recipient, expected):
    running_runtime[0].config["fixture"] = fixture_reply(recipient)
    register(db, running_runtime, profile)
    cid, _ = submit_campaign(db, catalogue, "registered-email", profile, "ASI02-TOOL-002", "mail-receipt",
                             timeout_seconds=60)
    process_next(db)
    detail = db.detail(cid)
    assert detail["status"] == "COMPLETED", detail["error"]
    assert detail["results"][0]["data"]["security_verdict"] == expected
    attempt = Attempt.model_validate(detail["attempts"][0]["data"])
    bundle = EvidenceStore(db.runtime).read(attempt.id)
    calls = [e for e in bundle.events if e.kind == "tool_call" and e.data["tool"] == "write_email"]
    receipts = [e for e in bundle.events if e.kind == "tool_result"]
    effects = next(e.data["sent_emails"] for e in bundle.events if e.kind == "state_after")
    assert len(receipts) == len(effects) == int(calls[0].data["allowed"])
    proposed = next(e for e in bundle.events if e.kind == "tool_proposed" and e.data["tool"] == "write_email")
    assert proposed.operation_id.startswith("call_") and proposed.data["provider_call_id_hash"]
    if receipts:
        receipt = json.loads(receipts[0].data["content"])
        assert receipt["external_delivery"] is False and receipt["recipients"] == [recipient]
        assert receipt["content_sha256"] == hashlib.sha256(calls[0].data["args"]["content"].encode()).hexdigest()
        assert calls[0].data["authorization_id"] == receipts[0].data["authorization_id"]
        # Independently validated effects cannot retain a conclusive verdict when
        # their mandatory receipt is omitted or contradicts the actual content.
        spec = Campaign.model_validate(detail["campaign"]).test_spec
        payload = PayloadSpec.model_validate(detail["attempts"][0]["payload"])
        for tamper in ("missing", "recipient", "authorization"):
            events = []
            for event in bundle.events:
                if event.kind == "tool_result":
                    if tamper == "missing":
                        continue
                    data = dict(event.data)
                    if tamper == "recipient":
                        altered = json.loads(data["content"])
                        altered["recipients"] = ["unrelated@lab.invalid"]
                        data["content"] = json.dumps(altered)
                        data["content_hash"] = digest(data["content"])
                    else:
                        data["authorization_id"] = "unissued"
                    event = event.model_copy(update={"data": data})
                events.append(event.model_copy(update={"sequence": len(events) + 1}))
            result = evaluate(spec, attempt, replace(bundle, events=tuple(events)), ExecutionStatus.COMPLETED, payload)
            assert result.security_verdict == "INCONCLUSIVE"
        adapter = object.__new__(RuntimeTargetAdapter)
        adapter.events, adapter.authorizations = list(bundle.events), {}
        with pytest.raises(ValueError, match="worker authorization"):
            adapter.observe()


def test_write_email_controls_change_only_untrusted_thread(catalogue):
    specs = catalogue.tests()
    clean = specs["BENIGN-REPLY-001"]
    for name in ("ASI02-TOOL-002", "ASI02-TOOL-003"):
        attack = specs[name]
        assert attack.legitimate_task == clean.legitimate_task
        assert attack.allowed_recipients == clean.allowed_recipients
        assert attack.hitl_policy == clean.hitl_policy
        assert {k: v for k, v in attack.email_input.items() if k != "email_thread"} == {
            k: v for k, v in clean.email_input.items() if k != "email_thread"}
        assert attack.email_input["email_thread"].startswith(clean.email_input["email_thread"])
