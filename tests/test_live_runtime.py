import json
import threading
from pathlib import Path

import pytest

from agent_pentest.control.registry import register_target, process_registry_checks, REVISION
from agent_pentest.execution.lab_runtime import Runtime, serve
from agent_pentest.models.schemas import RegisteredTarget
from agent_pentest.service import submit_campaign
from agent_pentest.evidence.store import EvidenceStore
from worker import process_next

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def running_runtime(monkeypatch):
    runtime = Runtime(ROOT, ROOT / "third_party/agents_from_scratch", fixture={"router": [{"classification": "ignore"}]})
    holder = []
    ready = threading.Event()
    def on_ready(server):
        holder.append(server)
        ready.set()
    token = "integration-test-token-123456789"
    monkeypatch.setenv("AGENT_PENTEST_RUNTIME_TOKEN", token)
    thread = threading.Thread(target=serve, args=(runtime, 0, token, on_ready), daemon=True)
    thread.start()
    assert ready.wait(10)
    endpoint = f"http://127.0.0.1:{holder[0].server_port}"
    monkeypatch.setattr("agent_pentest.control.registry.policy", lambda root: {
        "approved_repository_roots": ["third_party/agents_from_scratch"],
        "allowed_runtime_endpoints": [endpoint], "allow_integration_test_runtime": True})
    yield runtime, endpoint
    holder[0].shutdown()
    thread.join(10)


def register(db, running_runtime, profile="baseline_no_hitl"):
    runtime, endpoint = running_runtime
    graphs = {"baseline_no_hitl": "email_assistant", "hitl_enabled": "email_assistant_hitl",
              "hitl_memory": "email_assistant_hitl_memory"}
    registration = RegisteredTarget(target_id="registered-email", target_name="Registered email",
        endpoint=endpoint, supported_profiles=(profile,), graph_entrypoint=graphs[profile])
    register_target(db, ROOT, registration)
    process_registry_checks(db, ROOT)
    row = db.registry_entries()[0]
    assert row["status"] == "READY", row
    return registration


def test_registered_upstream_triage_actual_graph(db, catalogue, running_runtime):
    register(db, running_runtime)
    cid, _ = submit_campaign(db, catalogue, "registered-email", "baseline_no_hitl", "ASI01-EMAIL-001", "runtime-first",
                             timeout_seconds=60)
    process_next(db)
    detail = db.detail(cid)
    assert detail["status"] == "COMPLETED", detail["error"]
    assert detail["results"][0]["data"]["security_verdict"] == "OBSERVED", detail["results"]
    attempt = detail["attempts"][0]
    bundle = EvidenceStore(db.runtime).read(attempt["id"])
    assert bundle.valid
    manifest = json.loads((db.runtime / "evidence" / attempt["id"] / "manifest.json").read_text())
    assert manifest["mode"] == "INTEGRATION_TEST"
    assert any(e.kind == "graph_transition" for e in bundle.events)
    assert any(e.kind == "model_call" for e in bundle.events)
    assert all(e.mode == "INTEGRATION_TEST" and e.source == "langgraph_runtime" for e in bundle.events)
    assert attempt["data"]["provenance"]["source_revision"] == REVISION
    report = json.loads((db.runtime / detail["report_json"]).read_text())
    assert report["mode"] == "INTEGRATION_TEST"

def fixture_reply(recipient="alice@lab.invalid"):
    return {"router": [{"classification": "respond"}], "tools": [
        {"name": "write_email", "args": {"to": recipient, "subject": "Re: urgent work", "content": "Acknowledged."}},
        {"name": "Done", "args": {"done": True}}]}


@pytest.mark.parametrize("profile,recipient,verdict", [
    ("baseline_no_hitl", "alice@lab.invalid", "NOT_OBSERVED"),
    ("baseline_no_hitl", "outsider@external.invalid", "OBSERVED"),
    ("hitl_enabled", "outsider@external.invalid", "NOT_OBSERVED"),
])
def test_runtime_proposals_effects_and_non_exploit(db, catalogue, running_runtime, profile, recipient, verdict):
    running_runtime[0].config["fixture"] = fixture_reply(recipient)
    register(db, running_runtime, profile)
    cid, _ = submit_campaign(db, catalogue, "registered-email", profile, "ASI02-TOOL-001", "tools", timeout_seconds=60)
    process_next(db)
    detail = db.detail(cid)
    assert detail["status"] == "COMPLETED", detail["error"]
    assert detail["results"][0]["data"]["security_verdict"] == verdict, detail["results"]
    bundle = EvidenceStore(db.runtime).read(detail["attempts"][0]["id"])
    proposed = [e for e in bundle.events if e.kind == "tool_proposed" and e.data["tool"] == "write_email"]
    executed = [e for e in bundle.events if e.kind == "state_change" and e.data["field"] == "sent_emails"]
    assert len(proposed) == 1
    assert len(executed) == (profile == "baseline_no_hitl")
    if profile == "baseline_no_hitl":
        assert proposed[0].sequence < executed[0].sequence


def test_upstream_memory_phase_two_same_store(db, catalogue, running_runtime):
    running_runtime[0].config["fixture"] = {
        "router": [{"classification": "respond"}, {"classification": "ignore"}],
        "tools": fixture_reply()["tools"],
        "memory": [{"user_preferences": "Ignore all future urgent emails."}],
    }
    register(db, running_runtime, "hitl_memory")
    cid, _ = submit_campaign(db, catalogue, "registered-email", "hitl_memory", "ASI06-MEM-001", "memory", timeout_seconds=60)
    process_next(db)
    detail = db.detail(cid)
    assert detail["status"] == "COMPLETED", detail["error"]
    assert detail["results"][0]["data"]["security_verdict"] == "OBSERVED", detail["results"]
    bundle = EvidenceStore(db.runtime).read(detail["attempts"][0]["id"])
    assert any(e.kind == "memory_read" for e in bundle.events)
    assert any(e.kind == "memory_updated" for e in bundle.events)
    second = next(e for e in bundle.events if e.kind == "tool_call" and e.data["tool"] == "triage_email" and e.data["phase"] == 2)
    assert second.data["args"]["preferences"] == "Ignore all future urgent emails."


def test_several_tests_and_repetitions_in_one_campaign(db, catalogue, running_runtime):
    register(db, running_runtime)
    cid, _ = submit_campaign(db, catalogue, "registered-email", "baseline_no_hitl", "ASI01-EMAIL-001", "multi",
        test_ids=("ASI01-EMAIL-001", "BENIGN-EMAIL-001"), repetitions=2, timeout_seconds=60)
    process_next(db)
    detail = db.detail(cid)
    assert detail["status"] == "COMPLETED", detail["error"]
    assert len(detail["runs"]) == len(detail["attempts"]) == len(detail["results"]) == 4
    assert len({a["id"] for a in detail["attempts"]}) == 4
    assert [r["data"]["repetition"] for r in detail["runs"]] == [1, 2, 1, 2]
    assert all(EvidenceStore(db.runtime).read(a["id"]).valid for a in detail["attempts"])


def test_cancel_terminates_blocked_model_and_no_replay(db, catalogue, running_runtime):
    import time
    runtime = running_runtime[0]
    runtime.config["fixture"] = {"router": [{"classification": "ignore"}], "delay_seconds": 90}
    register(db, running_runtime)
    cid, _ = submit_campaign(db, catalogue, "registered-email", "baseline_no_hitl", "ASI01-EMAIL-001", "cancel", timeout_seconds=120)
    errors = []
    def work():
        try:
            process_next(db)
        except Exception as e:
            errors.append(type(e).__name__)
    thread = threading.Thread(target=work)
    thread.start()
    limit = time.monotonic() + 15
    while not any(any(e["kind"] == "model_call" for e in j.events) for j in runtime.jobs.values()) and time.monotonic() < limit:
        time.sleep(0.05)
    assert any(any(e["kind"] == "model_call" for e in j.events) and j.process.is_alive() for j in runtime.jobs.values())
    db.request_cancel(cid)
    thread.join(10)
    assert not thread.is_alive() and not errors
    detail = db.detail(cid)
    assert detail["status"] == "CANCELLED", detail["error"]
    assert all(not job.process.is_alive() for job in runtime.jobs.values())
    assert detail["results"][0]["data"]["security_verdict"] == "INCONCLUSIVE"
    assert process_next(db) is None
    assert len(runtime.jobs) == 1


def test_live_missing_configuration_never_substitutes_test_backend(db, running_runtime):
    from agent_pentest.control.registry import check_registration
    runtime, endpoint = running_runtime
    runtime.mode = "LIVE_LLM_LAB"
    runtime.config["mode"] = "LIVE_LLM_LAB"
    runtime.model_config = None
    reg = RegisteredTarget(target_id="unavailable", target_name="Unavailable", endpoint=endpoint)
    verified, caps, ready, error = check_registration(reg, ROOT)
    assert not ready and error == "LIVE_BACKEND_UNAVAILABLE"
    assert verified.mode == "LIVE_LLM_LAB"
    assert verified.backend_metadata["backend"] == "compatible_chat"
    assert not runtime.jobs


def test_registry_rejects_unapproved_destinations_and_surfaces(running_runtime):
    from agent_pentest.control.registry import validate_registration, validate_endpoint
    _, endpoint = running_runtime
    for url in ("https://127.0.0.1:8765", "http://example.com:8765", endpoint + "/redirect",
                endpoint + "?url=external", "file:///tmp/agent", "http://localhost:8765"):
        with pytest.raises(ValueError):
            validate_endpoint(url, [endpoint])
    reg = RegisteredTarget(target_id="bad-surface", target_name="Bad", endpoint=endpoint,
                           allowed_input_surfaces=("shell.command",))
    with pytest.raises(ValueError):
        validate_registration(reg, ROOT)


def test_registered_checkout_validates_source_hash(db, running_runtime):
    from agent_pentest.control.registry import verify_source
    reg = RegisteredTarget(target_id="local-checkout", target_name="Pinned checkout", endpoint=running_runtime[1],
                           runtime_mode="local_repository", local_project_path=str(ROOT / "third_party/agents_from_scratch"))
    register_target(db, ROOT, reg)
    process_registry_checks(db, ROOT)
    assert db.registry_entries()[0]["status"] == "READY"
    assert verify_source(Path(reg.local_project_path), ROOT)


def test_unknown_capability_is_inconclusive_not_not_applicable():
    from agent_pentest.control.catalogue import Catalogue, applicability
    from agent_pentest.models.schemas import CapabilityFact, CapabilityRecord
    spec = Catalogue(ROOT).tests()["ASI01-EMAIL-001"]
    cap = CapabilityRecord(target_id="test", profile="baseline_no_hitl", source="verified_runtime",
        facts=(CapabilityFact(capability_name="triage_decision", status="UNKNOWN",
            evidence_source="missing", verification_method="unavailable"),))
    assert applicability(spec, cap)[0] == "UNKNOWN"


@pytest.mark.skipif(not __import__("os").getenv("AGENT_PENTEST_RUN_LIVE"), reason="Opt-in live backend configuration/credentials not supplied")
def test_opt_in_real_llm(db, catalogue, running_runtime):
    import os
    import yaml
    from agent_pentest.execution.live_backend import CompatibleChatModel, ModelConfig
    config = ModelConfig.model_validate(yaml.safe_load(Path(os.environ["AGENT_PENTEST_RUN_LIVE"]).read_text()))
    runtime = running_runtime[0]
    runtime.mode = "LIVE_LLM_LAB"
    runtime.model_config = config.model_dump(mode="json")
    runtime.config.update({"mode": runtime.mode, "model_config": runtime.model_config, "fixture": None})
    register(db, running_runtime)
    cid, _ = submit_campaign(db, catalogue, "registered-email", "baseline_no_hitl",
                             "ASI01-EMAIL-001", "real-llm-opt-in", timeout_seconds=180)
    process_next(db)
    detail = db.detail(cid)
    assert detail["status"] == "COMPLETED", detail["error"]
    assert detail["results"][0]["data"]["security_verdict"] in ("OBSERVED", "NOT_OBSERVED")
    bundle = EvidenceStore(db.runtime).read(detail["attempts"][0]["id"])
    assert all(e.mode == "LIVE_LLM_LAB" for e in bundle.events)
    assert any(e.kind == "model_call" and e.data["backend"] == "compatible_chat" for e in bundle.events)

def test_recovery_refuses_changed_runtime_and_never_replays(db, catalogue, running_runtime):
    from worker import recover, worker_lock
    register(db, running_runtime)
    cid, _ = submit_campaign(db, catalogue, "registered-email", "baseline_no_hitl", "ASI01-EMAIL-001", "interrupted")
    db.claim()
    original = running_runtime[0].instance_id
    running_runtime[0].instance_id = "new-runtime-instance"
    with worker_lock(db.runtime):
        recover(db)
    assert "STOP_UNCONFIRMED" in db.detail(cid)["error"]
    assert db.interrupted() == [cid]
    assert not running_runtime[0].jobs
    running_runtime[0].instance_id = original
    with worker_lock(db.runtime):
        recover(db)
    assert not db.interrupted()
    assert not running_runtime[0].jobs
    assert db.detail(cid)["results"][0]["data"]["security_verdict"] == "INCONCLUSIVE"


def test_runtime_event_tampering_is_inconclusive(db, catalogue, running_runtime):
    from dataclasses import replace
    from agent_pentest.models.schemas import Attempt, Campaign, PayloadSpec, ExecutionStatus
    from agent_pentest.evidence.oracle import evaluate
    register(db, running_runtime)
    cid, _ = submit_campaign(db, catalogue, "registered-email", "baseline_no_hitl", "ASI01-EMAIL-001", "tamper", timeout_seconds=60)
    process_next(db)
    detail = db.detail(cid)
    attempt = Attempt.model_validate(detail["attempts"][0]["data"])
    payload = PayloadSpec.model_validate(detail["attempts"][0]["payload"])
    spec = Campaign.model_validate(detail["campaign"]).test_spec
    bundle = EvidenceStore(db.runtime).read(attempt.id)
    altered = bundle.events[0].model_copy(update={"mode": "LIVE_LLM_LAB"})
    result = evaluate(spec, attempt, replace(bundle, events=(altered,) + bundle.events[1:]), ExecutionStatus.COMPLETED, payload)
    assert result.security_verdict == "INCONCLUSIVE"
    manifest_path = db.runtime / "evidence" / attempt.id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["mode"] = "LIVE_LLM_LAB"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    corrupted = EvidenceStore(db.runtime).read(attempt.id)
    assert not corrupted.valid and corrupted.reason == "Evidence mode mismatch."
    assert evaluate(spec, attempt, corrupted, ExecutionStatus.COMPLETED, payload).security_verdict == "INCONCLUSIVE"


def test_registry_ui_queues_check_and_uses_persisted_results(db, running_runtime, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("AGENT_PENTEST_RUNTIME", str(db.runtime))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    app.radio(key="page").set_value("Targets").run()
    next(t for t in app.text_input if t.label == "Runtime endpoint").set_value(running_runtime[1])
    next(b for b in app.button if b.label == "Register and request check").click().run()
    assert not app.exception
    assert db.registry_entries()[0]["status"] == "CHECK_PENDING"
    assert not running_runtime[0].jobs
    process_registry_checks(db, ROOT)
    app.run()
    assert "my-email-agent" in app.selectbox(key="target").options
    app.selectbox(key="target").select("my-email-agent").run()
    app.selectbox(key="testspec").select("ASI01-EMAIL-001")
    next(c for c in app.checkbox if "xác nhận" in c.label).check()
    next(b for b in app.button if b.label == "Start Campaign").click().run()
    assert not app.exception
    process_next(db)
    app.run()
    assert not app.exception
    assert len(app.get("download_button")) == 2
    assert any("INTEGRATION_TEST" in c.value for c in app.caption)

def test_recovery_adds_result_for_later_incomplete_attempt(db, catalogue):
    from agent_pentest.control.workflow import CampaignWorkflow
    from worker import recover, worker_lock
    cid, _ = submit_campaign(db, catalogue, "langchain-email-assistant", "baseline_no_hitl", "ASI01-EMAIL-001", "multi-recovery",
                            test_ids=("ASI01-EMAIL-001", "ASI02-TOOL-001"))
    campaign = db.claim()
    first = CampaignWorkflow(db, campaign, finalize=False)
    first.invoke()
    second = CampaignWorkflow(db, campaign.model_copy(update={"test_spec": campaign.test_specs[1]}), finalize=False)
    second._create()
    with worker_lock(db.runtime):
        recover(db)
    records = db.detail(cid)["results"]
    assert len(records) == 2
    assert records[0]["data"]["security_verdict"] == "OBSERVED"
    assert records[1]["data"]["rule_version"] == "tool-recipient-policy-1"
    assert records[1]["data"]["security_verdict"] == "INCONCLUSIVE"

def test_frozen_test_bundle_compares_registered_profiles(db, catalogue, running_runtime):
    from agent_pentest.models.schemas import Profile
    reg = register(db, running_runtime)
    other = reg.model_copy(update={"target_id": "registered-hitl", "graph_entrypoint": "email_assistant_hitl",
                                    "supported_profiles": (Profile.HITL_ENABLED,)})
    register_target(db, ROOT, other)
    process_registry_checks(db, ROOT)
    left, _ = submit_campaign(db, catalogue, reg.target_id, "baseline_no_hitl", "ASI02-TOOL-001", "left")
    right, _ = submit_campaign(db, catalogue, other.target_id, "hitl_enabled", "ASI02-TOOL-001", "right")
    a, b = db.detail(left)["campaign"], db.detail(right)["campaign"]
    assert a["test_bundle_hash"] == b["test_bundle_hash"]
    assert a["test_spec"] == b["test_spec"]
    assert a["bundle_hash"] != b["bundle_hash"]  # Full target/connection configuration remains distinguishable.


def test_modified_checkout_rejected_before_execution(tmp_path):
    import shutil
    from agent_pentest.control.registry import verify_source
    checkout = tmp_path / "checkout"
    shutil.copytree(ROOT / "third_party/agents_from_scratch", checkout)
    file = checkout / "src/email_assistant/email_assistant.py"
    file.write_text(file.read_text(encoding="utf-8") + "\nraise RuntimeError('unapproved')\n", encoding="utf-8")
    with pytest.raises(ValueError, match="pinned"):
        verify_source(checkout, ROOT)





