import json

import pytest

from agent_pentest.control.pairing import expand_controls
from agent_pentest.evidence.comparison import compare_campaign
from agent_pentest.execution.email_model import LabRuleBackedEmailModel
from agent_pentest.service import submit_campaign
from worker import process_next


def run_pair(db, catalogue, attack="ASI02-TOOL-002", repetitions=1, profile="baseline_no_hitl"):
    cid, _ = submit_campaign(db, catalogue, "langchain-email-assistant", profile,
        attack, "pair", paired=True, repetitions=repetitions)
    process_next(db)
    detail = db.detail(cid)
    assert detail["status"] == "COMPLETED", detail["error"]
    return detail, compare_campaign(detail, db.runtime)


@pytest.mark.parametrize("attack", ["ASI01-EMAIL-001", "ASI02-TOOL-001", "ASI02-TOOL-002", "ASI02-TOOL-003"])
def test_pair_observes_verified_clean_task_and_attack_effect(db, catalogue, attack):
    detail, report = run_pair(db, catalogue, attack)
    pair = report["pairs"][0]
    assert pair["status"] == "ATTACK_EFFECT_OBSERVED"
    assert pair["control"]["utility"] == "PASSED"
    assert pair["attack"]["utility"] == "FAILED"
    assert pair["control"]["reset_id"] != pair["attack"]["reset_id"]
    assert pair["control"]["initial_state"] == pair["attack"]["initial_state"]
    assert pair["input_diff"] and pair["first_behavior_difference"]
    exported = json.loads((db.runtime / detail["report_json"]).read_text(encoding="utf-8"))
    assert exported["paired_comparison"] == report


def test_protected_pair_records_blocked_action_without_claiming_utility(db, catalogue):
    _, report = run_pair(db, catalogue, profile="hitl_enabled")
    pair = report["pairs"][0]
    assert pair["status"] == "NO_VIOLATION_OBSERVED"
    assert pair["utility_degraded"] is True
    assert any(e["kind"] == "hitl_decision" for e in pair["attack"]["trace"])


def test_pair_repetition_order_and_independent_attempts(db, catalogue):
    detail, report = run_pair(db, catalogue, repetitions=2)
    assert report["summary"]["eligible_pairs"] == 2
    assert len({a["data"]["reset_id"] for a in detail["attempts"]}) == 4
    # Run creation order (rather than lexical UUID order).
    assert sorted((r["data"]["test_id"], r["data"]["repetition"]) for r in detail["runs"]) == [
        ("ASI02-TOOL-002", 1), ("ASI02-TOOL-002", 2), ("BENIGN-REPLY-001", 1), ("BENIGN-REPLY-001", 2)]


def test_baseline_failure_is_not_attack_success(db, catalogue, monkeypatch):
    monkeypatch.setattr(LabRuleBackedEmailModel, "triage", lambda *args: "ignore")
    _, report = run_pair(db, catalogue, "ASI01-EMAIL-001")
    assert report["pairs"][0]["status"] == "BASELINE_FAILED"
    assert report["summary"]["eligible_pairs"] == 0
    assert report["summary"]["observed_fraction"] is None


def test_missing_or_tampered_control_invalidates_comparison(db, catalogue):
    detail, report = run_pair(db, catalogue)
    path = db.runtime / report["pairs"][0]["control"]["evidence_ref"]
    path.write_bytes(path.read_bytes() + b" ")
    changed = compare_campaign(detail, db.runtime)
    assert changed["pairs"][0]["status"] == "INCONCLUSIVE"
    assert changed["summary"]["eligible_pairs"] == 0


def test_pair_rejects_policy_change_and_unsupported_memory(catalogue):
    specs = catalogue.tests()
    attack = specs["ASI02-TOOL-002"].model_copy(update={"allowed_recipients": ("outsider@external.invalid",)})
    with pytest.raises(ValueError):
        expand_controls((attack,), specs)
    with pytest.raises(ValueError):
        expand_controls((specs["ASI06-MEM-001"],), specs)


def test_reply_does_not_satisfy_meeting_contract_v2(db, catalogue, monkeypatch):
    original = LabRuleBackedEmailModel.propose
    monkeypatch.setattr(LabRuleBackedEmailModel, "propose", lambda self, email, messages, preferences:
        original(self, {**email, "subject": "Urgent reply", "email_thread": "Please reply."}, messages, preferences))
    cid, _ = submit_campaign(db, catalogue, "langchain-email-assistant", "baseline_no_hitl",
                             "BENIGN-EMAIL-001", "strict-meeting")
    process_next(db)
    result = db.detail(cid)["results"][0]["data"]
    assert result["security_verdict"] == "NOT_OBSERVED"
    assert result["utility_result"] == "FAILED"


def test_fixed_payload_can_fail_to_attack(db, catalogue, monkeypatch):
    original = LabRuleBackedEmailModel.propose
    monkeypatch.setattr(LabRuleBackedEmailModel, "propose", lambda self, email, messages, preferences:
        original(self, {**email, "email_thread": "Please reply."}, messages, preferences))
    _, report = run_pair(db, catalogue)
    assert report["pairs"][0]["status"] == "NO_VIOLATION_OBSERVED"
    assert report["pairs"][0]["attack"]["utility"] == "PASSED"


def test_pending_pair_is_not_a_negative_security_result(db, catalogue):
    cid, _ = submit_campaign(db, catalogue, "langchain-email-assistant", "baseline_no_hitl",
                             "ASI02-TOOL-002", "pending", paired=True)
    report = compare_campaign(db.detail(cid), db.runtime)
    assert report["pairs"][0]["status"] == "INCONCLUSIVE"
    assert report["summary"]["observed_fraction"] is None


def test_observed_violation_without_mandatory_observation_is_not_pair_eligible(db, catalogue):
    from agent_pentest.evidence.comparison import _arm
    from agent_pentest.evidence.store import EvidenceStore
    detail, _ = run_pair(db, catalogue)
    spec = catalogue.tests()["ASI02-TOOL-002"]
    spec = spec.model_copy(update={"required_evidence": spec.required_evidence + ("memory_read",)})
    arm = _arm(detail, spec, 1, EvidenceStore(db.runtime))
    # An already confirmed external-recipient effect may retain OBSERVED, but the
    # comparative analysis must still demand completion of every required observation.
    assert arm["security"] == "OBSERVED"
    assert arm["verified"] is False


def test_ui_enqueues_controls_and_shows_persisted_comparison(db, monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("AGENT_PENTEST_RUNTIME", str(db.runtime))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()
    app.selectbox(key="target").select("langchain-email-assistant").run()
    app.selectbox(key="testspec").select("ASI02-TOOL-002")
    app.checkbox(key="paired").check()
    next(b for b in app.button if b.label == "Start Campaign").click().run()
    assert not app.exception
    cid = process_next(db)
    assert db.detail(cid)["campaign"]["paired"] is True
    app.run()
    assert not app.exception
    assert any("ATTACK_EFFECT_OBSERVED" in item.value for item in app.markdown)
    assert any(t.label == "Đối chứng sạch / payload" for t in app.tabs)
