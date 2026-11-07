from dataclasses import replace

import pytest

from agent_pentest.evidence.findings import build_finding
from agent_pentest.evidence.oracle import evaluate
from agent_pentest.evidence.store import EvidenceStore
from agent_pentest.models.schemas import Attempt, Campaign, ExecutionStatus, PayloadSpec, Verdict
from worker import process_next


@pytest.fixture
def evidence(db, submit):
    campaign_id = submit()
    process_next(db)
    detail = db.detail(campaign_id)
    campaign = Campaign.model_validate(detail["campaign"])
    attempt = Attempt.model_validate(detail["attempts"][0]["data"])
    payload = PayloadSpec.model_validate(detail["attempts"][0]["payload"])
    bundle = EvidenceStore(db.runtime).read(attempt.id)
    return campaign.test_spec, attempt, payload, bundle


def verdict(evidence, bundle=None, status=ExecutionStatus.COMPLETED):
    spec, attempt, payload, original = evidence
    return evaluate(spec, attempt, bundle or original, status, payload)


def test_observed_depends_on_state_not_llm_claims(evidence):
    result = verdict(evidence)
    assert result.security_verdict == Verdict.OBSERVED
    assert len(result.evidence_ids) == 5


def test_missing_evidence_is_inconclusive_and_cannot_build_finding(evidence):
    spec, attempt, payload, bundle = evidence
    incomplete = replace(bundle, events=tuple(e for e in bundle.events if e.kind != "state_after"))
    assert verdict(evidence, incomplete).security_verdict == Verdict.INCONCLUSIVE
    assert build_finding(verdict(evidence), spec, attempt, incomplete, payload) is None


def test_attempt_identity_mismatch_is_inconclusive(evidence):
    bundle = evidence[-1]
    altered = bundle.events[0].model_copy(update={"attempt_id": "wrong-attempt"})
    assert verdict(evidence, replace(bundle, events=(altered,) + bundle.events[1:])).security_verdict == Verdict.INCONCLUSIVE


def test_valid_impact_survives_execution_timeout(evidence):
    result = verdict(evidence, status=ExecutionStatus.TIMED_OUT)
    assert result.execution_status == ExecutionStatus.TIMED_OUT
    assert result.security_verdict == Verdict.OBSERVED


def test_unmatched_state_change_is_inconclusive(evidence):
    bundle = evidence[-1]
    events = tuple(e.model_copy(update={"operation_id": "unmatched"}) if e.kind == "state_change" else e for e in bundle.events)
    assert verdict(evidence, replace(bundle, events=events)).security_verdict == Verdict.INCONCLUSIVE


def test_store_detects_tampering_and_refuses_overwrite(db, evidence):
    _, attempt, _, bundle = evidence
    store = EvidenceStore(db.runtime)
    with pytest.raises(FileExistsError):
        store.write(attempt.id, bundle.events)
    path = store.directory(attempt.id) / "events.jsonl"
    path.write_bytes(path.read_bytes().replace(b"bob@lab.invalid", b"eve@lab.invalid"))
    assert not store.read(attempt.id).valid
    assert verdict(evidence, store.read(attempt.id)).security_verdict == Verdict.INCONCLUSIVE


def test_protected_missing_completion_is_not_a_negative(db, submit):
    campaign_id = submit("protected")
    process_next(db)
    detail = db.detail(campaign_id)
    attempt = Attempt.model_validate(detail["attempts"][0]["data"])
    spec = Campaign.model_validate(detail["campaign"]).test_spec
    payload = PayloadSpec.model_validate(detail["attempts"][0]["payload"])
    bundle = EvidenceStore(db.runtime).read(attempt.id)
    assert evaluate(spec, attempt, bundle, ExecutionStatus.COMPLETED, payload).security_verdict == Verdict.NOT_OBSERVED
    partial = replace(bundle, events=tuple(e for e in bundle.events if e.kind != "completed"))
    assert evaluate(spec, attempt, partial, ExecutionStatus.COMPLETED, payload).security_verdict == Verdict.INCONCLUSIVE

