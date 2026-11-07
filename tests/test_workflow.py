import json
import socket
from concurrent.futures import ThreadPoolExecutor

import pytest

from agent_pentest.evidence.reporting import generate_reports
from agent_pentest.evidence.store import EvidenceStore
from agent_pentest.execution.fake_hma import FakeHMA
from agent_pentest.models.schemas import Campaign, digest
from agent_pentest.service import submit_campaign
from worker import process_next, recover, worker_lock


@pytest.mark.parametrize("profile, verdict, findings", [("vulnerable", "OBSERVED", 1), ("protected", "NOT_OBSERVED", 0)])
def test_full_workflow_smoke(db, submit, profile, verdict, findings):
    campaign_id = submit(profile)
    assert process_next(db) == campaign_id
    detail = db.detail(campaign_id)
    assert detail["status"] == "COMPLETED", detail["error"]
    result = detail["results"][0]["data"]
    assert result["security_verdict"] == verdict
    assert result["execution_status"] == "COMPLETED"
    assert result["utility_result"] == "PASSED"
    assert len(detail["findings"]) == findings
    assert len(detail["runs"]) == len(detail["attempts"]) == 1
    assert detail["attempts"][0]["operations"] == 5
    bundle = EvidenceStore(db.runtime).read(detail["attempts"][0]["id"])
    assert bundle.valid and len(bundle.events) >= 8
    report = json.loads((db.runtime / detail["report_json"]).read_text(encoding="utf-8"))
    assert report["mode"] == "SIMULATION"
    assert report["detail"]["status"] == "COMPLETED"
    assert "SIMULATION" in (db.runtime / detail["report_html"]).read_text(encoding="utf-8")
    assert [x["stage"] for x in detail["audit"]] == [
        "validate_scope", "discover_capabilities", "select_test", "create_run_attempt", "prepare_reset",
        "validate_payload", "safety_authorization", "execute", "collect_evidence", "deterministic_oracle",
        "finding_builder", "generate_report"]
    assert process_next(db) is None


def test_no_public_network_during_workflow(db, submit, monkeypatch):
    campaign_id = submit()
    def denied(*args, **kwargs):
        raise AssertionError("Network access is forbidden in SIMULATION")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    assert process_next(db) == campaign_id
    assert db.detail(campaign_id)["status"] == "COMPLETED"


def test_repeated_submission_and_concurrent_claims(db, catalogue):
    def enqueue(_):
        return submit_campaign(db, catalogue, "fake-hma", "vulnerable", "ASI02-HMA-001", "same-key")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(enqueue, range(16)))
    assert len({r[0] for r in results}) == 1
    assert sum(created for _, created in results) == 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: db.claim(), range(8)))
    assert sum(c is not None for c in claims) == 1


def test_same_key_different_configuration_rejected(db, catalogue, submit):
    submit(request_key="fixed")
    with pytest.raises(ValueError, match="different configuration"):
        submit_campaign(db, catalogue, "fake-hma", "protected", "ASI02-HMA-001", "fixed")


def test_target_lock_blocks_another_campaign(db, submit):
    first = submit(request_key="one")
    second = submit(request_key="two")
    assert db.claim().id == first
    assert db.claim() is None
    db.finish(first, "FAILED")
    assert db.claim().id == second


def test_not_applicable_has_no_run_or_attempt(db, submit):
    class NoTool(FakeHMA):
        def discover(self):
            return super().discover().model_copy(update={"tools": ()})
    campaign_id = submit()
    process_next(db, NoTool)
    detail = db.detail(campaign_id)
    assert detail["results"][0]["data"]["security_verdict"] == "NOT_APPLICABLE"
    assert not detail["attempts"] and not detail["runs"]
    assert detail["report_json"]


def test_unknown_observation_is_not_not_applicable(db, submit):
    class NoObservation(FakeHMA):
        def discover(self):
            return super().discover().model_copy(update={"observable": False})
    campaign_id = submit()
    process_next(db, NoObservation)
    detail = db.detail(campaign_id)
    assert detail["results"][0]["data"]["security_verdict"] == "INCONCLUSIVE"
    assert not detail["attempts"]


def test_scope_rejection_before_attempt(db, submit):
    campaign_id = submit()
    original = Campaign.model_validate(db.detail(campaign_id)["campaign"])
    # Create an independent immutable snapshot with an out-of-scope target.
    bad = original.model_copy(update={"id": "rejected-campaign", "request_key": "outside",
        "scope": original.scope.model_copy(update={"allowed_targets": ("different-target",)})})
    db.finish(campaign_id, "SKIPPED")
    db.enqueue(bad, digest(bad))
    process_next(db)
    detail = db.detail(bad.id)
    assert detail["status"] == "REJECTED"
    assert not detail["attempts"]
    assert detail["results"][0]["data"]["security_verdict"] == "INCONCLUSIVE"


def test_worker_recovery_does_not_replay(db, submit):
    campaign_id = submit()
    assert db.claim().id == campaign_id
    with worker_lock(db.runtime):
        recover(db)
    assert db.detail(campaign_id)["status"] == "FAILED"
    assert db.detail(campaign_id)["report_json"]
    assert process_next(db) is None


def test_recover_failed_campaign_with_retained_lock(db, submit):
    campaign_id = submit()
    db.claim()
    db.finish(campaign_id, "FAILED", release=False)
    assert db.interrupted() == [campaign_id]
    with worker_lock(db.runtime):
        recover(db)
    assert not db.interrupted()
    assert db.detail(campaign_id)["report_json"]


def test_impact_before_timeout_remains_observed(db, submit):
    from agent_pentest.control.safety import AttemptTimeout
    class TimeoutAfterImpact(FakeHMA):
        def execute(self, operation_id, guard):
            super().execute(operation_id, guard)
            raise AttemptTimeout("SIMULATION deadline exceeded after impact")
    campaign_id = submit()
    process_next(db, TimeoutAfterImpact)
    detail = db.detail(campaign_id)
    assert detail["status"] == "TIMED_OUT"
    assert detail["results"][0]["data"]["security_verdict"] == "OBSERVED"
    assert len(detail["findings"]) == 1


def test_worker_os_lock_excludes_second_worker(db):
    with worker_lock(db.runtime):
        with pytest.raises(RuntimeError, match="Another worker"):
            with worker_lock(db.runtime):
                pytest.fail("second worker acquired lock")


def test_reviewer_failure_still_exports_report(db, submit):
    campaign_id = submit()
    process_next(db)
    class BrokenReviewer:
        def explain(self, result):
            raise RuntimeError("untrusted error text")
    json_ref, _ = generate_reports(db, campaign_id, BrokenReviewer())
    report = json.loads((db.runtime / json_ref).read_text(encoding="utf-8"))
    assert "Reviewer unavailable" in report["reviewer_notes"][0]
    assert "untrusted error text" not in json.dumps(report)


def test_report_html_escapes_untrusted_content(db, submit):
    campaign_id = submit()
    process_next(db)
    class HtmlReviewer:
        def explain(self, result):
            return '<script>alert(1)</script> password=should-not-leak'
    json_ref, html_ref = generate_reports(db, campaign_id, HtmlReviewer())
    html = (db.runtime / html_ref).read_text(encoding="utf-8")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "should-not-leak" not in html
    assert "should-not-leak" not in (db.runtime / json_ref).read_text(encoding="utf-8")


def test_profile_comparison_has_same_fixed_bundle(db, submit):
    a, b = submit("vulnerable", "a"), submit("protected", "b")
    assert db.detail(a)["campaign"]["bundle_hash"] == db.detail(b)["campaign"]["bundle_hash"]
    process_next(db)
    process_next(db)
    left, right = db.detail(a)["attempts"][0], db.detail(b)["attempts"][0]
    assert left["id"] != right["id"]
    assert left["payload"]["body"] == right["payload"]["body"]

