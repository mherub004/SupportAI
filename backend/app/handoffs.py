"""Durable human handoff, independent from customer reply and CRM delivery."""
import hashlib
from datetime import timedelta
from email.utils import parseaddr
from urllib.parse import quote

from sqlalchemy import select

from app.business import decode, profile
from app.db import Connector, Conversation, HumanHandoff, Job, Message, MessageOrigin, State, audit, now
from app.google import Gmail


class AlertDeferred(Exception):
    def __init__(self, until):
        self.until = until


def rfc_id(message_id):
    return "<supportflow-human-" + hashlib.sha256(message_id.encode()).hexdigest() + "@supportflow.invalid>"


def queue(session, message, config, reasons=None):
    from app.service import enqueue
    conversation = session.scalar(select(Conversation).where(Conversation.id == message.thread_id).with_for_update())
    previous = session.scalar(select(HumanHandoff).where(HumanHandoff.message_id == message.id).with_for_update())
    if previous and not previous.active:
        return  # A person's completed handoff is not reopened by an old CRM retry.
    conversation.paused, conversation.owner = True, "human"
    reasons = reasons if reasons is not None else message.risk_tags
    existing = session.scalar(select(HumanHandoff).where(HumanHandoff.thread_id == message.thread_id, HumanHandoff.active))
    if existing:
        existing.reasons = sorted(set(existing.reasons + reasons))
        return
    session.add(HumanHandoff(message_id=message.id, thread_id=message.thread_id,
                            recipient=config.escalation_email, reasons=reasons))
    enqueue(session, "human_alert:" + message.id, "human_alert", {"message_id": message.id})
    audit(session, "human_handoff_requested", message.id, reasons=reasons)


def context(session, base, row, check_recipient=True):
    from app.service import Conflict
    company, message, source = profile(session), session.get(Message, row.message_id), session.get(MessageOrigin, row.message_id)
    if (not company or not message or message.status == "purged" or not source
            or source.origin != "google:" + company["support_email"]):
        raise Conflict("Handoff does not belong to this live mailbox")
    if check_recipient and row.recipient != company["escalation_email"]:
        raise Conflict("Escalation recipient changed; review the pending handoff")
    record = session.get(Connector, "google")
    if not record or not record.enabled:
        raise Conflict("Connect Google before notifying the human agent")
    fields = decode(record, base)
    if fields.get("mailbox") != company["support_email"]:
        raise Conflict("Google mailbox changed")
    return base.model_copy(update={**fields, "connector_mode": "google"}), message


def notify(factory, base, message_id, mail=None):
    with factory() as session:
        # The same mailbox mutex serializes the notification quota across workers.
        session.scalar(select(State).where(State.key == "kill_switch").with_for_update())
        row = session.scalar(select(HumanHandoff).where(HumanHandoff.message_id == message_id).with_for_update())
        if not row or not row.active or row.status in {"sent", "resolved", "uncertain"}:
            return
        if row.status == "reserved":
            row.status, row.error = "uncertain", "InspectGmailBeforeRetry"
            session.commit()
            return
        config, message = context(session, base, row)
        attempts = list(session.scalars(select(HumanHandoff).where(
            HumanHandoff.attempted_at > now() - timedelta(hours=1))))
        if len(attempts) >= max(1, base.human_alert_hourly_limit):
            raise AlertDeferred(min(r.attempted_at for r in attempts) + timedelta(hours=1, seconds=1))
        link = "https://mail.google.com/mail/u/?authuser=" + quote(config.mailbox, safe="") + "#all/" + quote(message.thread_id, safe="")
        body = ("A customer conversation needs your attention. AI replies for this thread are paused.\n\n"
                + "Sender: " + parseaddr(message.sender)[1] + "\nSubject: " + message.subject[:1000]
                + "\nReasons: " + ", ".join(row.reasons) + "\n\nOpen the original Gmail conversation: " + link
                + "\nReview the original conversation and approved knowledge in SupportFlow before responding.\n"
                + "Use Resume agent only when human handling is complete.")
        recipient = row.recipient
        row.status, row.attempted_at = "reserved", now()
        session.commit()
        try:
            outbound = (mail or Gmail(config)).alert(recipient, body, rfc_id(message_id))
        except Exception:
            row.status, row.error = "uncertain", "InspectGmailBeforeRetry"
            session.commit()
            raise
        row.status, row.outbound_id, row.error = "sent", outbound, ""
        audit(session, "human_agent_notified", message_id)
        session.commit()


def install_routes(app, base, factory, operator):
    from fastapi import Depends
    from app.service import Conflict
    secured = [Depends(operator)]

    @app.get("/api/handoffs", dependencies=secured)
    def handoffs():
        with factory() as session:
            return [{"message_id": r.message_id, "thread_id": r.thread_id, "recipient": r.recipient,
                     "reasons": r.reasons, "active": r.active, "status": r.status, "error": r.error,
                     "subject": subject, "sender": sender}
                    for r, subject, sender in session.execute(select(HumanHandoff, Message.subject, Message.sender)
                        .join(Message, Message.id == HumanHandoff.message_id)
                        .order_by(HumanHandoff.created_at.desc()).limit(200))]

    @app.post("/api/handoffs/{message_id}/retry", dependencies=secured)
    def retry(message_id: str):
        with factory() as session:
            job = session.scalar(select(Job).where(Job.id == "human_alert:" + message_id).with_for_update())
            row = session.scalar(select(HumanHandoff).where(HumanHandoff.message_id == message_id).with_for_update())
            if not row or not job or not row.active or row.status in {"sent", "reserved", "uncertain"} or job.status == "working":
                raise Conflict("Only a confirmed unsent, idle alert can be retried")
            company = profile(session)
            if company:
                row.recipient = company["escalation_email"]
            context(session, base, row)
            row.status, row.error = "pending", ""
            job.status, job.available_at, job.attempts, job.error = "pending", now(), 0, ""
            session.commit()
        return {"status": "queued"}

    @app.post("/api/handoffs/{message_id}/reconcile", dependencies=secured)
    def reconcile(message_id: str):
        with factory() as session:
            row = session.get(HumanHandoff, message_id)
            if not row or row.status not in {"reserved", "uncertain"}:
                raise Conflict("No uncertain notification to reconcile")
            config, _ = context(session, base, row, check_recipient=False)
        client = Gmail(config)
        client.verify_mailbox()
        sent = client.find_sent(rfc_id(message_id))
        if not sent:
            raise Conflict("No sent notification confirmed. No repeat email was attempted")
        with factory() as session:
            row = session.scalar(select(HumanHandoff).where(HumanHandoff.message_id == message_id).with_for_update())
            row.status, row.outbound_id, row.error = "sent", sent, ""
            audit(session, "human_notification_reconciled", message_id, actor="operator")
            session.commit()
        return {"status": "confirmed", "email_resend": False}
