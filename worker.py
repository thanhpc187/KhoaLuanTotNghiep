"""Local queue worker. No target actions run in the Streamlit process."""
import argparse
import os
import time
from contextlib import contextmanager
from pathlib import Path

# Force external trace exporters off, even if inherited from the user's shell.
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGSMITH_OTEL_ENABLED"] = "false"

from agent_pentest.control.catalogue import Catalogue
from agent_pentest.control.workflow import run_campaign
from agent_pentest.evidence.reporting import generate_reports
from agent_pentest.models.schemas import Profile
from agent_pentest.service import project_root, runtime_path, submit_campaign
from agent_pentest.storage.database import Database


@contextmanager
def worker_lock(runtime: Path):
    """OS releases this lock when the process dies. No expiry-based replay."""
    runtime.mkdir(parents=True, exist_ok=True)
    handle = (runtime / "worker.lock").open("a+b")
    handle.seek(0, 2)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError("Another worker owns this runtime directory.") from None
    try:
        yield
    finally:
        handle.seek(0)
        if os.name == "nt":
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def process_next(db: Database, adapter_factory=None) -> str | None:
    campaign = db.claim()
    if campaign is None:
        return None
    kwargs = {"adapter_factory": adapter_factory} if adapter_factory else {}
    try:
        run_campaign(db, campaign, **kwargs)
    except Exception:
        # Keep target lock on unexpected failure. Explicit recovery requires OS worker ownership.
        previous = db.detail(campaign.id)["error"]
        message = "Unexpected workflow/storage failure; target lock retained."
        db.finish(campaign.id, "FAILED", f"{previous} | {message}" if previous else message, release=False)
        raise
    return campaign.id


def recover(db: Database):
    # Invoked under worker_lock; remote jobs must confirm termination before release.
    for campaign_id in db.interrupted():
        detail = db.detail(campaign_id)
        if detail["campaign"]["target"]["adapter"] == "langgraph_runtime":
            from agent_pentest.models.schemas import Campaign
            from agent_pentest.control.registry import RuntimeClient
            campaign = Campaign.model_validate(detail["campaign"])
            try:
                confirmed = RuntimeClient(campaign.target.registration, campaign.scope.allowed_endpoints).request(
                    "/reconcile", {"instance_id": campaign.target.registration.runtime_instance, "campaign_id": campaign_id})["confirmed"]
            except Exception:
                confirmed = False
            if not confirmed:
                db.finish(campaign_id, "FAILED", (detail["error"] or "") + " | STOP_UNCONFIRMED: target remains locked.", release=False)
                continue
        error_msg = db.abandon_interrupted(campaign_id)
        reports = generate_reports(db, campaign_id)
        db.finish(campaign_id, "FAILED", error_msg, reports, release=True)
        print(f"{detail['campaign']['mode']} recovered {campaign_id}: FAILED, no replay", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Controlled AI Agent pentest worker")
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--init-db", action="store_true")
    parser.add_argument("--once", action="store_true", help="Process at most one queued Campaign")
    parser.add_argument("--recover-interrupted", action="store_true", help="Reconcile interrupted lab campaigns without replay")
    parser.add_argument("--enqueue", choices=[p.value for p in Profile], help="Queue a campaign, then exit")
    parser.add_argument("--target", default="fake-hma")
    parser.add_argument("--testspec", default="ASI02-HMA-001")
    parser.add_argument("--testspecs", nargs="+")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--paired", action="store_true", help="Include matched clean controls and compare independent Attempts")
    parser.add_argument("--check-targets", action="store_true")
    parser.add_argument("--register-target", type=Path)
    parser.add_argument("--roles-config", type=Path)
    parser.add_argument("--request-key", help="Required with --enqueue; repeated keys are idempotent")
    args = parser.parse_args()
    db = Database(args.runtime or runtime_path())
    db.initialize()
    if args.init_db:
        print(f"Initialized {db.path}")
        return
    if args.check_targets:
        from agent_pentest.control.registry import process_registry_checks
        process_registry_checks(db, project_root())
        return
    if args.register_target:
        import yaml
        from agent_pentest.control.registry import register_target
        from agent_pentest.models.schemas import RegisteredTarget
        reg = RegisteredTarget.model_validate(yaml.safe_load(args.register_target.read_text(encoding="utf-8")))
        register_target(db, project_root(), reg)
        print(f"Registered {reg.target_id}; run --check-targets.")
        return
    if args.enqueue:
        import yaml
        roles = yaml.safe_load(args.roles_config.read_text(encoding="utf-8")) if args.roles_config else None
        if not args.request_key:
            parser.error("--enqueue requires --request-key")
        campaign_id, created = submit_campaign(db, Catalogue(project_root()), args.target, args.enqueue,
                                               args.testspec, args.request_key, test_ids=args.testspecs or (), paired=args.paired,
                                               repetitions=args.repetitions, role_config=roles,
                                               timeout_seconds=180 if args.target not in ("fake-hma", "langchain-email-assistant") else None)
        print(f"{db.detail(campaign_id)['campaign']['mode']} {campaign_id} created={created}")
        return
    try:
        with worker_lock(db.runtime):
            if args.recover_interrupted:
                recover(db)
                return
            if db.interrupted():
                raise RuntimeError("Interrupted campaigns found; run --recover-interrupted before continuing.")
            while True:
                from agent_pentest.control.registry import process_registry_checks
                process_registry_checks(db, project_root())
                db.heartbeat()
                campaign_id = process_next(db)
                if campaign_id:
                    detail = db.detail(campaign_id)
                    print(f"{detail['campaign']['mode']} {campaign_id}: {detail['status']}", flush=True)
                if args.once:
                    return
                if not campaign_id:
                    time.sleep(0.5)
    except KeyboardInterrupt:
        print("Worker stopped. Recover any RUNNING campaign before restarting.")


if __name__ == "__main__":
    main()

