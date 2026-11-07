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
from agent_pentest.control.workflow import CampaignWorkflow
from agent_pentest.evidence.reporting import generate_reports
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
        CampaignWorkflow(db, campaign, **kwargs).invoke()
    except Exception:
        # Keep target lock on unexpected failure. Explicit recovery requires OS worker ownership.
        db.finish(campaign.id, "FAILED", "Unexpected workflow/storage failure; target lock retained.", release=False)
        raise
    return campaign.id


def recover(db: Database):
    # This function is invoked only under worker_lock in main(). Fake has no external state.
    for campaign_id in db.interrupted():
        db.abandon_interrupted(campaign_id)
        reports = generate_reports(db, campaign_id)
        db.finish(campaign_id, "FAILED", "Worker interrupted; no action replayed.", reports)
        print(f"SIMULATION recovered {campaign_id}: FAILED, no replay", flush=True)


def main():
    parser = argparse.ArgumentParser(description="SIMULATION-only AI Agent pentest worker")
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--init-db", action="store_true")
    parser.add_argument("--once", action="store_true", help="Process at most one queued Campaign")
    parser.add_argument("--recover-interrupted", action="store_true", help="Close interrupted Fake campaigns without replay")
    parser.add_argument("--enqueue", choices=["vulnerable", "protected"], help="Queue a campaign, then exit")
    parser.add_argument("--request-key", help="Required with --enqueue; repeated keys are idempotent")
    args = parser.parse_args()
    db = Database(args.runtime or runtime_path())
    db.initialize()
    if args.init_db:
        print(f"Initialized {db.path}")
        return
    if args.enqueue:
        if not args.request_key:
            parser.error("--enqueue requires --request-key")
        campaign_id, created = submit_campaign(db, Catalogue(project_root()), "fake-hma", args.enqueue,
                                               "ASI02-HMA-001", args.request_key)
        print(f"SIMULATION {campaign_id} created={created}")
        return
    try:
        with worker_lock(db.runtime):
            if args.recover_interrupted:
                recover(db)
                return
            if db.interrupted():
                raise RuntimeError("Interrupted campaigns found; run --recover-interrupted before continuing.")
            while True:
                db.heartbeat()
                campaign_id = process_next(db)
                if campaign_id:
                    print(f"SIMULATION {campaign_id}: {db.detail(campaign_id)['status']}", flush=True)
                if args.once:
                    return
                if not campaign_id:
                    time.sleep(0.5)
    except KeyboardInterrupt:
        print("Worker stopped. Recover any RUNNING campaign before restarting.")


if __name__ == "__main__":
    main()

