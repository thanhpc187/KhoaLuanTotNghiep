import html
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent_pentest.control.workflow import CampaignWorkflow
from agent_pentest.evidence.oracle import evaluate
from agent_pentest.evidence.reporting import generate_reports
from agent_pentest.evidence.store import EvidenceStore, redact
from agent_pentest.models.schemas import Attempt, Campaign, ExecutionStatus, PayloadSpec, Verdict
from agent_pentest.service import project_root
from worker import process_next, recover, worker_lock

ROOT = Path(__file__).resolve().parents[1]


def locked(db, campaign_id):
    with db.connect() as conn:
        return bool(conn.execute("SELECT 1 FROM target_locks WHERE campaign_id=?", (campaign_id,)).fetchone())


def test_recovery_holds_lock_until_reports_succeed_preserving_error(db, submit, monkeypatch):
    cid = submit()
    db.claim()
    original = "STOP_UNCONFIRMED: target remains locked."
    db.finish(cid, "FAILED", original, release=False)
    second = submit(request_key="next")
    def broken_reports(database, campaign_id):
        assert locked(database, campaign_id)
        assert database.claim() is None
        assert original in database.detail(campaign_id)["error"]
        raise OSError("disk full")
    with monkeypatch.context() as patch:
        patch.setattr("worker.generate_reports", broken_reports)
        with worker_lock(db.runtime), pytest.raises(OSError):
            recover(db)
    assert locked(db, cid)
    assert db.detail(cid)["error"].count(original) == 1
    def checked_reports(database, campaign_id):
        assert locked(database, campaign_id)
        return generate_reports(database, campaign_id)
    monkeypatch.setattr("worker.generate_reports", checked_reports)
    with worker_lock(db.runtime):
        recover(db)
    detail = db.detail(cid)
    assert not locked(db, cid) and original in detail["error"]
    assert detail["error"].count("Interrupted worker;") == 1
    assert (db.runtime / detail["report_json"]).is_file()
    assert db.claim().id == second


@pytest.mark.parametrize("key", [
    "password", "secret", "api_key", "apikey", "authorization", "credential", "token",
    "access_token", "refresh_token", "auth_token", "bearer_token", "session_token", "secret_token",
])
def test_redact_exact_sensitive_keys(key):
    assert redact({"nested": [{key.upper(): "private"}]}) == {"nested": [{key.upper(): "[REDACTED]"}]}


def test_redact_preserves_llm_token_counts_and_non_sensitive_keys():
    counts = {key: 42 for key in ("input_tokens", "output_tokens", "total_tokens", "max_tokens",
                                  "prompt_tokens", "completion_tokens", "tokenizer", "secretary")}
    assert redact({"usage": counts, "token": "private"}) == {"usage": counts, "token": "[REDACTED]"}


def hma_evidence(db, submit):
    cid = submit()
    process_next(db)
    detail = db.detail(cid)
    return (Campaign.model_validate(detail["campaign"]).test_spec,
            Attempt.model_validate(detail["attempts"][0]["data"]),
            PayloadSpec.model_validate(detail["attempts"][0]["payload"]),
            EvidenceStore(db.runtime).read(detail["attempts"][0]["id"]))


def resequence(bundle, events):
    return replace(bundle, events=tuple(e.model_copy(update={"sequence": i}) for i, e in enumerate(events, 1)))


def remove_own_effect(bundle, spec, keep_call):
    events = []
    for e in bundle.events:
        if e.kind == "state_change" and e.data["ticket_id"] == spec.own_ticket:
            continue
        if not keep_call and e.kind == "tool_call" and e.data["ticket_id"] == spec.own_ticket:
            continue
        if e.kind == "state_after":
            data = {**e.data, "tickets": [
                {**t, "status": "open"} if t["id"] == spec.own_ticket else t for t in e.data["tickets"]]}
            e = e.model_copy(update={"data": data})
        events.append(e)
    return resequence(bundle, events)


def test_ownership_allowed_call_without_state_change_is_inconclusive(db, submit):
    spec, attempt, payload, bundle = hma_evidence(db, submit)
    changed = remove_own_effect(bundle, spec, keep_call=True)
    assert evaluate(spec, attempt, changed, ExecutionStatus.COMPLETED, payload).security_verdict == Verdict.INCONCLUSIVE


def test_ownership_observed_can_have_failed_utility(db, submit):
    spec, attempt, payload, bundle = hma_evidence(db, submit)
    changed = remove_own_effect(bundle, spec, keep_call=False)
    result = evaluate(spec, attempt, changed, ExecutionStatus.COMPLETED, payload)
    assert result.security_verdict == Verdict.OBSERVED
    assert result.utility_result == "FAILED"
    assert evaluate(spec, attempt, changed, ExecutionStatus.TIMED_OUT, payload).utility_result == "UNKNOWN"


def test_post_oracle_failure_preserves_execution_and_explains_campaign(db, submit, monkeypatch):
    def fail(*args):
        raise RuntimeError("raw target secret")
    monkeypatch.setattr("agent_pentest.control.workflow.build_finding", fail)
    cid = submit()
    process_next(db)
    detail = db.detail(cid)
    assert detail["status"] == "FAILED"
    assert detail["attempts"][0]["status"] == detail["results"][0]["data"]["execution_status"] == "COMPLETED"
    assert "finding_builder: RuntimeError" in detail["error"]
    assert not locked(db, cid)
    report = json.loads((db.runtime / detail["report_json"]).read_text(encoding="utf-8"))
    assert "after target execution" in report["outcome_context"]["explanation"]
    assert "raw target secret" not in json.dumps(report)


def test_report_paths_embedded_and_reexport_keeps_original(db, submit):
    cid = submit()
    process_next(db)
    detail = db.detail(cid)
    first = (db.runtime / detail["report_json"]).read_bytes()
    json_ref, html_ref = generate_reports(db, cid)
    report = json.loads((db.runtime / json_ref).read_text(encoding="utf-8"))
    assert (db.runtime / detail["report_json"]).read_bytes() == first
    assert report["detail"]["report_json"] == json_ref != detail["report_json"]
    assert report["detail"]["report_html"] == html_ref != detail["report_html"]
    document = html.unescape((db.runtime / html_ref).read_text(encoding="utf-8"))
    assert f'"report_json": "{json_ref}"' in document
    assert f'"report_html": "{html_ref}"' in document


def test_project_root_env_cwd_and_fallback(tmp_path, monkeypatch):
    configured, current = tmp_path / "configured", tmp_path / "current"
    current.mkdir()
    monkeypatch.chdir(current)
    monkeypatch.delenv("AGENT_PENTEST_ROOT", raising=False)
    assert project_root() == ROOT
    (current / "configs").mkdir()
    (current / "configs/scope.yaml").write_text("mode: SIMULATION")
    (current / "testspecs").mkdir()
    assert project_root() == current
    monkeypatch.setenv("AGENT_PENTEST_ROOT", str(configured))
    assert project_root() == configured


def test_ui_profile_options_follow_target(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_PENTEST_RUNTIME", str(tmp_path / "runtime"))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
    assert app.selectbox(key="profile").options == ["vulnerable", "protected"]
    app.selectbox(key="target").select("langchain-email-assistant").run()
    assert not app.exception
    assert app.selectbox(key="profile").options == ["baseline_no_hitl", "hitl_enabled", "hitl_memory"]
    assert set(app.selectbox(key="testspec").options) == {
        "BENIGN-EMAIL-001", "ASI01-EMAIL-001", "ASI02-TOOL-001", "ASI06-MEM-001",
        "BENIGN-REPLY-001", "ASI02-TOOL-002", "ASI02-TOOL-003"}
    app.selectbox(key="profile").select("hitl_memory")
    app.selectbox(key="target").select("fake-hma").run()
    assert not app.exception
    assert app.selectbox(key="profile").value == "vulnerable"


def test_ui_running_evidence_and_campaign_selection(db, submit, monkeypatch):
    monkeypatch.setenv("AGENT_PENTEST_RUNTIME", str(db.runtime))
    first = submit(request_key="one")
    flow = CampaignWorkflow(db, db.claim())
    flow._create()  # A legitimately RUNNING attempt, before the collector has produced files.
    second = submit(request_key="two")
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
    app.selectbox(key="campaign_picker").select(first).run()
    assert not app.exception
    assert app.session_state["selected_campaign"] == first
    assert any("Đang chờ thu thập bằng chứng" in message.value for message in app.info)
    assert not any("Missing or malformed" in message.value for message in app.caption)
    app.selectbox(key="campaign_picker").select(second).run()
    app.run()
    assert app.session_state["selected_campaign"] == second


def test_database_v01_migration_keeps_records_and_supports_multiple_runs(db, submit):
    cid = submit()
    process_next(db)
    before = db.detail(cid)
    # Recreate the exact v0.1 table constraints around real campaign records.
    conn = sqlite3.connect(db.path)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        for table in ("runs", "attempts", "results", "findings"):
            sql = conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
            column = "run_id" if table == "attempts" else "campaign_id"
            body = sql[sql.index("("):].rstrip().removesuffix(")") + f", UNIQUE({column}))"
            conn.execute(f"CREATE TABLE {table}_legacy {body}")
            conn.execute(f"INSERT INTO {table}_legacy SELECT * FROM {table}")
            conn.execute(f"DROP TABLE {table}")
            conn.execute(f"ALTER TABLE {table}_legacy RENAME TO {table}")
        conn.commit()
    finally:
        conn.close()
    db.initialize()
    db.initialize()  # Idempotent, including the one-time backup.
    assert db.detail(cid) == before
    assert (db.runtime / "app.pre-v0.2.sqlite3").is_file()
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        for table in ("runs", "results", "findings"):
            conn.execute(f"INSERT INTO {table} SELECT id || '-second', campaign_id, data FROM {table}")
        conn.execute("""INSERT INTO attempts SELECT id || '-second', campaign_id, run_id, data, status, payload, operations
                        FROM attempts""")
    assert len(db.detail(cid)["runs"]) == len(db.detail(cid)["attempts"]) == 2
    assert len(db.detail(cid)["results"]) == len(db.detail(cid)["findings"]) == 2

