"""Opt-in support automation and a durable, independently retried CRM outbox."""
import hashlib
import re
from email.utils import parseaddr
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.business import decode, digest, pause, profile, public_connector
from app.db import BusinessConfig, Connector, CrmDelivery, Job, Message, MessageOrigin, Send, audit, now


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    acknowledgement: bool = False
    allowed_senders: list[str] = Field(default_factory=list, max_length=100)
    hourly_limit: int = Field(default=10, ge=1, le=100)
    crm_providers: list[Literal["salesforce", "netsuite"]] = Field(default_factory=list, max_length=2)

    @field_validator("allowed_senders")
    @classmethod
    def addresses(cls, values):
        from app.policy import valid_recipient
        if any(not valid_recipient(v) or parseaddr(v)[1] != v for v in values):
            raise ValueError("Use exact sender email addresses")
        return sorted(set(v.casefold() for v in values))


def policy(session):
    row = session.get(BusinessConfig, "automation")
    return Policy.model_validate(row.value if row else {}).model_dump()


def sender_allowed(settings, sender):
    return not settings["allowed_senders"] or parseaddr(sender)[1].casefold() in settings["allowed_senders"]


def fresh_email(headers, since):
    from datetime import datetime, timezone
    from app.db import now
    try:
        received = datetime.fromtimestamp(int(headers["x-supportflow-internal-date"]) / 1000, timezone.utc).replace(tzinfo=None)
        return datetime.fromisoformat(since) <= received <= now()
    except (KeyError, ValueError, OverflowError, OSError):
        return False


def queue_crm(session, message_id):
    from app.service import enqueue
    delivery = session.get(Send, message_id)
    if not delivery or delivery.state != "sent":
        return
    for provider in policy(session)["crm_providers"]:
        if not session.get(CrmDelivery, (message_id, provider)):
            session.add(CrmDelivery(message_id=message_id, provider=provider))
        enqueue(session, f"crm:{provider}:{message_id}", "crm_sync", {"message_id": message_id, "provider": provider})


def sync(factory, base, message_id, provider):
    from app.crm import client_for
    with factory() as session:
        row = session.scalar(select(CrmDelivery).where(CrmDelivery.message_id == message_id,
                                                      CrmDelivery.provider == provider).with_for_update())
        if not row or row.status == "done":
            return
        sent, message = session.get(Send, message_id), session.get(Message, message_id)
        business, origin = profile(session), session.get(MessageOrigin, message_id)
        if (not sent or sent.state != "sent" or not message or message.status == "purged"
                or not business or not origin or origin.origin != "google:" + business["support_email"]):
            row.status, row.error = "needs_review", "UnconfirmedOrWrongMailbox"
            session.commit()
            return
        if provider not in policy(session)["crm_providers"]:
            row.status, row.error = "paused", "ProviderDisabled"
            session.commit()
            return
        if row.activity_state == "reserved" or row.case_state == "reserved":
            row.status, row.error = "needs_review", "UncertainExternalWrite"
            session.commit()
            return  # A timeout/crash is never permission to repeat a POST.
        connector = session.get(Connector, provider)
        if (not connector or not connector.enabled or not connector.verified_at
                or connector.verified_digest != digest(decode(connector, base))):
            raise ValueError("Verify CRM connection before syncing")
        client = client_for(session, provider, base)
        expected_config = digest(decode(session.get(Connector, provider), base))
        client.verify()
        client.verify_writes()
        session.expire_all()
        connector = session.scalar(select(Connector).where(Connector.id == provider).with_for_update())
        if not connector or not connector.enabled or digest(decode(connector, base)) != expected_config:
            raise ValueError("CRM configuration changed during verification")
        connector.verified_at = now()
        session.commit()
        row = session.scalar(select(CrmDelivery).where(CrmDelivery.message_id == message_id,
                               CrmDelivery.provider == provider).with_for_update())
        if row.status == "done" or "reserved" in (row.activity_state, row.case_state):
            return
        if row.target_origin and row.target_origin != client.origin:
            row.status, row.error = "needs_review", "OrganizationChanged"
            session.commit()
            return
        row.target_origin = client.origin
        if not row.customer_id:
            match = client.lookup(parseaddr(message.sender)[1])
            if match["status"] != "matched":
                row.status, row.error = "needs_review", "Customer_" + match["status"]
                session.commit()
                return
            row.customer_id = match["records"][0]["record_id"]
        if not row.case_id:
            references = set(re.findall(r"\b(?:case|ticket)\s*[:#-]?\s*(\d{1,20})\b", message.subject, re.I))
            if len(references) > 1:
                row.status, row.error = "needs_review", "AmbiguousCaseReference"
                session.commit()
                return
            cases = (client.support_cases(row.customer_id, next(iter(references)))
                     if references else client.support_cases(row.customer_id))
            if len(cases) != 1:
                row.status, row.error = "needs_review", "CaseMissingOrAmbiguous"
                session.commit()
                return
            row.case_id = cases[0]
        marker = hashlib.sha256((base.mailbox + ":" + message_id).encode()).hexdigest()[:32]
        body = f"SupportFlow delivery {marker}\nOutcome: email sent\nCase: {row.case_id}\nTo: {parseaddr(message.sender)[1]}\nSubject: {message.subject}\nGmail ID: {sent.outbound_id}\n\n{message.response}"
        # Bind the customer's case immediately before each write, including retries.
        client.validate_case(row.case_id, row.customer_id)
        session.flush()
        session.refresh(row, with_for_update=True)
        if "reserved" in (row.activity_state, row.case_state) or row.status == "done":
            return
        if row.activity_state != "done":
            row.activity_state, row.status = "reserved", "working"
            session.commit()
            row.activity_id = client.log_activity(row.customer_id, row.case_id, marker, body)
            row.activity_state = "done"
            session.commit()
        if row.case_state != "done":
            client.validate_case(row.case_id, row.customer_id)
            session.refresh(row, with_for_update=True)
            if row.case_state in {"reserved", "done"}:
                return
            row.case_state = "reserved"
            session.commit()
            client.log_case(row.case_id, marker, body)
            row.case_state = "done"
        row.status, row.error = "done", ""
        audit(session, "crm_delivery_completed", message_id, provider=provider)
        session.commit()


def install_routes(app, base, factory, operator):
    from fastapi import Depends
    from app.service import Conflict
    secured = [Depends(operator)]

    @app.get("/api/automation", dependencies=secured)
    def get_policy():
        with factory() as session:
            return policy(session)

    @app.put("/api/automation", dependencies=secured)
    def save_policy(data: Policy):
        if data.enabled and not data.acknowledgement:
            raise Conflict("Acknowledge automatic sending and CRM writes first")
        if data.enabled and base.workspace == "personal_test" and not data.allowed_senders:
            raise Conflict("Personal automatic tests require at least one exact test sender")
        with factory() as session:
            if data.enabled:
                for provider in data.crm_providers:
                    row = session.get(Connector, provider)
                    if not public_connector(row, base)["verified"]:
                        raise Conflict("Connect and verify each selected CRM first")
                    if provider == "netsuite" and not decode(row, base).get("netsuite_case_reply_field"):
                        raise Conflict("Configure the NetSuite case reply custom field first")
                    try:
                        from app.crm import client_for
                        client_for(session, provider, base).verify_writes()
                    except Exception:
                        raise Conflict("CRM write verification failed; check Task/case permissions and NetSuite metadata/custom field") from None
            row = session.get(BusinessConfig, "automation")
            if row:
                row.value = data.model_dump()
            else:
                session.add(BusinessConfig(key="automation", value=data.model_dump()))
            pause(session)
            audit(session, "automation_policy_saved", "automation", actor="operator", enabled=data.enabled)
            session.commit()
        return {"status": "saved", "activation_required": True}

    @app.get("/api/automation/deliveries", dependencies=secured)
    def deliveries():
        with factory() as session:
            return [{"message_id": r.message_id, "provider": r.provider, "status": r.status,
                     "activity_state": r.activity_state, "case_state": r.case_state, "error": r.error, "case_id": r.case_id}
                    for r in session.scalars(select(CrmDelivery).limit(200))]

    @app.post("/api/automation/deliveries/{message_id}/{provider}/retry", dependencies=secured)
    def retry(message_id: str, provider: str):
        from app.db import now
        with factory() as session:
            job = session.scalar(select(Job).where(Job.id == f"crm:{provider}:{message_id}").with_for_update())
            row = session.scalar(select(CrmDelivery).where(CrmDelivery.message_id == message_id, CrmDelivery.provider == provider).with_for_update())
            if not row or row.status == "done" or "reserved" in (row.activity_state, row.case_state):
                raise Conflict("Completed or uncertain external writes cannot be blindly repeated")
            if not job or job.status == "working":
                raise Conflict("CRM job is absent or still running")
            row.status, row.error = "pending", ""
            job.status, job.attempts, job.available_at, job.error = "pending", 0, now(), ""
            session.commit()
        return {"status": "queued", "email_resend": False}

    class CaseInput(BaseModel):
        case_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9]+$")

    @app.put("/api/automation/deliveries/{message_id}/{provider}/case", dependencies=secured)
    def bind_case(message_id: str, provider: str, data: CaseInput):
        from app.crm import client_for
        with factory() as session:
            row = session.get(CrmDelivery, (message_id, provider))
            message, sent = session.get(Message, message_id), session.get(Send, message_id)
            business, source = profile(session), session.get(MessageOrigin, message_id)
            job = session.get(Job, f"crm:{provider}:{message_id}")
            if (not row or not message or not sent or sent.state != "sent" or not business or not source
                    or source.origin != "google:" + business["support_email"]
                    or row.case_state == "done" or "reserved" in (row.activity_state, row.case_state)
                    or (job and job.status == "working")):
                raise Conflict("This delivery cannot be remapped while working, completed or uncertain")
            if not public_connector(session.get(Connector, provider), base)["verified"]:
                raise Conflict("Verify the CRM connection first")
            client = client_for(session, provider, base)
            match = client.lookup(parseaddr(message.sender)[1])
            if match["status"] != "matched":
                raise Conflict("The sender must match exactly one customer")
            customer = match["records"][0]["record_id"]
            if row.customer_id and row.customer_id != customer:
                raise Conflict("Customer identity changed")
            if row.activity_state == "done" and row.case_id != data.case_id:
                raise Conflict("An existing activity cannot be moved to a different case")
            if row.target_origin and row.target_origin != client.origin:
                raise Conflict("CRM organization changed")
            try:
                client.validate_case(data.case_id, customer)
            except Exception:
                raise Conflict("Case could not be verified as belonging to this customer") from None
            session.expire_all()
            job = session.scalar(select(Job).where(Job.id == f"crm:{provider}:{message_id}").with_for_update())
            row = session.scalar(select(CrmDelivery).where(CrmDelivery.message_id == message_id, CrmDelivery.provider == provider).with_for_update())
            if (not row or (job and job.status == "working") or row.case_state == "done"
                    or "reserved" in (row.activity_state, row.case_state)
                    or (row.activity_state == "done" and row.case_id != data.case_id)):
                raise Conflict("Delivery changed during case verification")
            row.customer_id, row.case_id = customer, data.case_id
            row.status, row.error = "pending", ""
            audit(session, "crm_case_mapped", message_id, actor="operator", provider=provider)
            session.commit()
        return retry(message_id, provider)

    class ReconcileInput(BaseModel):
        external_id: str = Field(default="", max_length=100, pattern=r"^[A-Za-z0-9]*$")

    @app.post("/api/automation/deliveries/{message_id}/{provider}/reconcile", dependencies=secured)
    def reconcile(message_id: str, provider: str, data: ReconcileInput):
        from app.crm import client_for
        with factory() as session:
            row = session.get(CrmDelivery, (message_id, provider))
            job = session.get(Job, f"crm:{provider}:{message_id}")
            sent, source = session.get(Send, message_id), session.get(MessageOrigin, message_id)
            business = profile(session)
            if (not row or not sent or sent.state != "sent" or not source or not business
                    or source.origin != "google:" + business["support_email"] or (job and job.status == "working")):
                raise Conflict("Inspect a confirmed, idle delivery in this workspace")
            stage = "activity" if row.activity_state == "reserved" else "case" if row.case_state == "reserved" else ""
            if not stage or not public_connector(session.get(Connector, provider), base)["verified"]:
                raise Conflict("A verified connector and uncertain write are required")
            client = client_for(session, provider, base)
            if client.origin != row.target_origin:
                raise Conflict("CRM organization changed")
            marker = hashlib.sha256((business["support_email"] + ":" + message_id).encode()).hexdigest()[:32]
            try:
                client.validate_case(row.case_id, row.customer_id)
                confirmed = client.confirm_write(stage, row.customer_id, row.case_id, marker, data.external_id)
            except Exception:
                confirmed = False
            if not confirmed:
                raise Conflict("External write could not be confirmed; no repeat write was attempted")
            session.expire_all()
            job = session.scalar(select(Job).where(Job.id == f"crm:{provider}:{message_id}").with_for_update())
            row = session.scalar(select(CrmDelivery).where(CrmDelivery.message_id == message_id, CrmDelivery.provider == provider).with_for_update())
            if not row or (job and job.status == "working") or getattr(row, stage + "_state") != "reserved":
                raise Conflict("Delivery changed during external verification")
            if stage == "activity":
                row.activity_state, row.activity_id = "done", data.external_id
            else:
                row.case_state = "done"
            row.status, row.error = ("done" if row.activity_state == row.case_state == "done" else "pending"), ""
            if row.status == "done" and job:
                job.status = "done"
            audit(session, "crm_write_reconciled", message_id, actor="operator", provider=provider, stage=stage)
            session.commit()
            completed = row.status == "done"
        return {"status": "confirmed"} if completed else retry(message_id, provider)
