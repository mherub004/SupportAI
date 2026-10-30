import argparse
import logging
import time
from datetime import timedelta

from sqlalchemy import or_, select, update

from app.config import settings
from app.business import runtime
from app.db import Job, State, audit, database, now
from app.service import Workflow, enqueue, initialize

log = logging.getLogger("supportflow.worker")


def run_one(factory, workflow):
    with factory() as session:
        job = session.scalar(select(Job).where(
            or_((Job.status == "pending") & (Job.available_at <= now()),
                (Job.status == "working") & (Job.lease_until < now()))
        ).order_by(Job.available_at).with_for_update(skip_locked=True).limit(1))
        if not job:
            return False
        job_id, kind, payload = job.id, job.kind, job.payload
        job.status, job.attempts = "working", job.attempts + 1
        job.lease_until = now() + timedelta(seconds=workflow.config.job_lease_seconds)
        session.commit()
    try:
        if kind == "process":
            with factory() as session:
                from app.db import Message
                email = session.get(Message, payload["message_id"])
                status = email.status if email else "missing"
            if status == "ready":
                workflow.create_draft(payload["message_id"])
            else:
                workflow.process(payload["message_id"])
        elif kind == "gmail_sync":
            workflow.sync_gmail()
        elif kind == "drive_sync":
            workflow.sync_drive()
        elif kind == "watch":
            result = workflow.mail.watch()
            with factory() as session:
                record = session.get(State, "watch_expiration")
                if record:
                    record.value = str(result["expiration"])
                else:
                    session.add(State(key="watch_expiration", value=str(result["expiration"])))
                session.commit()
        else:
            raise ValueError("Unknown job kind")
    except Exception as exc:
        # Error TYPE only: provider response bodies and customer data stay out of logs.
        log.warning("Job %s failed: %s", kind, type(exc).__name__)
        with factory() as session:
            job = session.get(Job, job_id)
            job.error = type(exc).__name__
            job.status = "failed" if job.attempts >= 5 else "pending"
            job.available_at = now() + timedelta(seconds=min(300, 2 ** job.attempts))
            audit(session, "job_failed", job_id, error=job.error, attempts=job.attempts)
            session.commit()
    else:
        with factory() as session:
            session.execute(update(Job).where(Job.id == job_id).values(status="done", lease_until=None))
            session.commit()
    return True


def schedule(factory, config):
    if config.connector_mode != "google":
        return
    tick = int(time.time())
    with factory() as session:
        enqueue(session, f"gmail_sync:{tick // 60}", "gmail_sync", {})
        if config.drive_folder_id:
            enqueue(session, f"drive_sync:{tick // 3600}", "drive_sync", {})
        if config.gmail_topic:
            enqueue(session, f"watch:{tick // 86400}", "watch", {})
        session.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config = settings()
    engine, factory = database(config.database_url)
    initialize(engine, factory)
    logging.basicConfig(level=logging.INFO)
    while True:
        effective = runtime(config, factory)
        if effective.configured_business and not effective.business_active:
            if args.once:
                break
            time.sleep(2)
            continue
        workflow = Workflow(effective, factory)
        schedule(factory, effective)
        ran = run_one(factory, workflow)
        if args.once:
            break
        if not ran:
            time.sleep(2)


if __name__ == "__main__":
    main()
