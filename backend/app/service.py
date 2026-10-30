import hashlib
import re
from datetime import timedelta
from email.utils import parseaddr

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import Connector, DriveApproval, MessageOrigin, Conversation, Document, Job, Message, Send, State, audit, now
from app.google import DemoMail, Drive, Gmail
from app.policy import (SAFETY, classify, current, excluded, safe_response,
                        valid_recipient, validate_grounding)
from app.providers import DemoModel, GeminiModel
from app.business import origin, origin_matches


class Conflict(Exception):
    pass


def enqueue(session, key, kind, payload):
    try:
        with session.begin_nested():
            session.add(Job(id=key, kind=kind, payload=payload))
            session.flush()
        return True
    except IntegrityError:
        return False


def ingest(session, email, config):
    if session.get(Message, email.id):
        return False
    if not session.get(Conversation, email.thread_id):
        try:
            with session.begin_nested():
                session.add(Conversation(id=email.thread_id))
                session.flush()
        except IntegrityError:
            pass
    try:
        with session.begin_nested():
            message = Message(**email.model_dump())
            if excluded(email, config.mailbox):
                message.status = "excluded"
                message.disposition = "excluded"
            session.add(message)
            session.flush()
            session.add(MessageOrigin(message_id=email.id, origin=origin(config)))
            session.flush()
    except IntegrityError:
        return False
    if message.status != "excluded":
        enqueue(session, "process:" + email.id, "process", {"message_id": email.id})
    audit(session, "message_ingested", email.id, excluded=message.status == "excluded")
    return True


def upsert_document(session, data):
    fields = data.model_dump()
    fields["checksum"] = hashlib.sha256(data.content.encode()).hexdigest()
    doc = session.get(Document, data.id)
    if doc:
        for key, value in fields.items():
            setattr(doc, key, value)
    else:
        session.add(Document(**fields))
    audit(session, "knowledge_updated", data.id, revision=data.revision, approved=data.approved)


def retrieve(session, email, config=None):
    docs = [d for d in session.scalars(select(Document).where(
        Document.brand == email.brand, Document.language == email.language)) if current(d) and (not config or not config.configured_business or not d.id.startswith("demo-"))]
    text = f"{email.subject}\n{email.body}".casefold()
    models = {d.model for d in docs if re.search(r"(?<!\w)" + re.escape(d.model.casefold()) + r"(?!\w)", text)}
    if not models and any(d.model == "general" for d in docs):
        models = {"general"}
    if len(models) != 1:
        email.model = "unknown"
        return []
    email.model = next(iter(models))
    docs = [d for d in docs if d.model == email.model]
    words = set(re.findall(r"\w{3,}", text))
    docs.sort(key=lambda d: len(words & set(re.findall(r"\w{3,}", d.content.casefold()))), reverse=True)
    # Bounded context: no arbitrary folder dump to model.
    selected = []
    total = 0
    for doc in docs:
        from types import SimpleNamespace
        blocks = [doc.content[index:index + 4000] for index in range(0, len(doc.content), 4000)]
        ranked = sorted(range(len(blocks)), key=lambda i: len(words & set(re.findall(r"\w{3,}", blocks[i].casefold()))), reverse=True)
        indexes = sorted(ranked[:4])
        excerpt = "\n\n".join(blocks[i] for i in indexes)
        if total + len(excerpt) > 60000:
            continue
        evidence = SimpleNamespace(**{column.name: getattr(doc, column.name) for column in Document.__table__.columns})
        evidence.full_content, evidence.content = doc.content, excerpt
        selected.append(evidence)
        total += len(excerpt)
        if len(selected) == 5:
            break
    return selected


class Workflow:
    def __init__(self, config, factory, mail=None, model=None):
        self.config, self.factory = config, factory
        self.mail = mail or (DemoMail() if config.connector_mode == "demo" else Gmail(config))
        self.model = model or (DemoModel() if config.connector_mode == "demo" else GeminiModel(config))

    def process(self, message_id):
        with self.factory() as session:
            email = session.scalar(select(Message).where(Message.id == message_id).with_for_update())
            if email is None or email.status != "queued":
                return
            if not origin_matches(session, email, self.config):
                email.status, email.disposition = "archived", "excluded"
                session.commit()
                return
            conversation = session.get(Conversation, email.thread_id)
            brand_query = select(Document.brand).distinct()
            if self.config.configured_business:
                brand_query = brand_query.where(~Document.id.like("demo-%"))
            brands = list(session.scalars(brand_query)) or ["ABL", "Wallbox"]
            email.language, email.brand, email.risk_tags = classify(email, brands)
            knowledge_state = session.get(State, "knowledge_sync")
            if knowledge_state and knowledge_state.value != "current":
                email.risk_tags = email.risk_tags + ["knowledge_sync_uncertain"]
            if email.language not in self.config.supported_languages:
                email.risk_tags = email.risk_tags + ["unsupported_language"]
            if any(word in (email.subject + " " + email.body).casefold() for word in self.config.escalation_keywords):
                email.risk_tags = email.risk_tags + ["business_escalation"]
            if (self.config.configured_business and email.brand == "unknown"
                    and self.config.business_name in brands):
                email.brand = self.config.business_name
            docs = retrieve(session, email, self.config)
            if conversation.paused or email.risk_tags:
                email.response = safe_response(email.language)
                email.disposition = "escalate" if set(email.risk_tags) & {
                    "electrical_safety", "human_requested"} else "review"
                if conversation.paused:
                    email.risk_tags = email.risk_tags + ["human_owned"]
                email.category = "unknown"
                email.citations = []
            else:
                proposal = self.model.propose(email, docs)
                grounded = validate_grounding(proposal, docs)
                email.response = proposal.response
                email.category = proposal.category
                email.citations = [{**c.model_dump(), "title": next(d.title for d in docs if d.id == c.document_id),
                                    "url": next(d.url for d in docs if d.id == c.document_id),
                                    "checksum": next(d.checksum for d in docs if d.id == c.document_id),
                                    "customer_url": next(d.customer_url for d in docs if d.id == c.document_id)}
                                   for c in proposal.citations] if grounded else []
                email.disposition = "review"
                if not grounded:
                    email.risk_tags = email.risk_tags + ["ungrounded"]
                    email.response = (
                        ("Bitte nennen Sie die Marke, das genaue Modell und den Fehlercode."
                         if email.language == "de" else "Please share the brand, exact model, and error code.")
                        if proposal.category == "clarification" else safe_response(email.language)
                    )
                if proposal.uncertain:
                    email.risk_tags = email.risk_tags + ["model_uncertain"]
                if SAFETY.search(proposal.response):
                    email.response = safe_response(email.language)
                    email.risk_tags = email.risk_tags + ["unsafe_output"]
                    email.disposition = "escalate"
                # No LLM-generated prose is automatically sent in this pilot. The eligible
                # category only sends a backend-owned link template after all gates pass.
                if (grounded and not email.risk_tags and proposal.category == "manual_link"
                        and email.model != "unknown"
                        and all(d.customer_url for d in docs if d.id in {c.document_id for c in proposal.citations})):
                    email.disposition = "eligible"
                    urls = list(dict.fromkeys(d.customer_url for d in docs
                                              if d.id in {c["document_id"] for c in email.citations}))
                    email.response = (("Die freigegebene Dokumentation für Ihr Modell: "
                                       if email.language == "de" else
                                       "The approved documentation for your model: ") + "\n".join(urls))
            email.provider_version = self.model.version
            email.status = "ready"
            audit(session, "decision_created", email.id, disposition=email.disposition,
                  risk_tags=email.risk_tags, model=email.provider_version,
                  source_revisions=[{"id": c["document_id"], "revision": c["revision"]} for c in email.citations])
            session.commit()
        self.create_draft(message_id)
        if self.config.auto_send_enabled and self.config.production_approved:
            try:
                self.deliver(message_id, automatic=True)
            except Conflict:
                pass

    def create_draft(self, message_id):
        with self.factory() as session:
            email = session.scalar(select(Message).where(Message.id == message_id).with_for_update())
            if not origin_matches(session, email, self.config):
                raise Conflict("Message belongs to another provider context")
            if email.status != "ready":
                return
            conversation = session.get(Conversation, email.thread_id)
            if conversation.paused:
                email.status = "review"
                session.commit()
                return
            # Persist reservation before network I/O. Crash/timeout cannot create a second draft.
            email.status = "draft_creating"
            session.commit()
            try:
                draft_id = self.mail.draft(email, email.response, self.rfc_id(email.id))
            except Exception:
                email.status = "draft_uncertain"
                audit(session, "draft_uncertain", email.id)
                session.commit()
                raise
            email.draft_id, email.status = draft_id, "draft"
            audit(session, "draft_created", email.id)
            session.commit()

    @staticmethod
    def rfc_id(message_id):
        return "<supportflow-" + hashlib.sha256(message_id.encode()).hexdigest() + "@supportflow.invalid>"

    def sources_current(self, session, email):
        if not email.citations:
            return False
        for citation in email.citations:
            doc = session.get(Document, citation["document_id"])
            if (not doc or not current(doc) or doc.revision != citation["revision"]
                    or doc.checksum != citation["checksum"] or doc.customer_url != citation["customer_url"]
                    or doc.url != citation["url"] or doc.brand != email.brand
                    or doc.model != email.model or doc.language != email.language):
                return False
        return True

    def deliver(self, message_id, automatic=False):
        if self.config.review_only:
            raise Conflict("Business onboarding is draft-only; send through your human support process")
        with self.factory() as session:
            # Serialize rate-limit, kill-switch and reservation checks across workers.
            controls = session.scalar(select(State).where(State.key == "kill_switch").with_for_update())
            email = session.scalar(select(Message).where(Message.id == message_id).with_for_update())
            if not email:
                raise Conflict("Message not found")
            if not origin_matches(session, email, self.config):
                raise Conflict("Message belongs to another provider context")
            conversation = session.scalar(select(Conversation).where(
                Conversation.id == email.thread_id).with_for_update())
            sync_state = session.get(State, "knowledge_sync")
            if sync_state is None or sync_state.value != "current":
                raise Conflict("Knowledge synchronization is uncertain")
            if controls is None or controls.value != "off":
                raise Conflict("Kill switch is enabled")
            if conversation.paused or self.mail.human_owned(email):
                conversation.paused = True
                audit(session, "human_takeover", email.thread_id)
                session.commit()
                raise Conflict("Thread is owned by a human")
            if email.status != "draft" or not email.draft_id:
                raise Conflict("A confirmed draft is required")
            if not valid_recipient(email.sender) or parseaddr(email.sender)[1].casefold() == self.config.mailbox.casefold():
                raise Conflict("Recipient validation failed")
            if email.risk_tags or email.disposition == "escalate":
                raise Conflict("Risk-tagged cases must be handled in the existing human support route")
            if not self.sources_current(session, email):
                raise Conflict("Current approved source evidence is required")
            if automatic:
                if (not self.config.auto_send_enabled or not self.config.production_approved
                        or email.disposition != "eligible" or email.category != "manual_link"
                        or email.category not in self.config.auto_send_categories.split(",")):
                    raise Conflict("Automatic sending is not authorized")
            elif email.disposition != "approved":
                raise Conflict("An operator must approve the exact response first")
            if not self.mail.verify_draft(email.draft_id, email, email.response, self.rfc_id(email.id)):
                raise Conflict("Gmail draft changed since review; sending blocked")
            sent = len(list(session.scalars(select(Send).where(Send.created_at > now() - timedelta(hours=1)))))
            if sent >= self.config.hourly_send_limit:
                raise Conflict("Hourly send limit reached")
            if session.get(Send, email.id):
                raise Conflict("A send was already reserved; reconcile it before any further action")
            session.add(Send(message_id=email.id, state="reserved", rfc_message_id=self.rfc_id(email.id)))
            audit(session, "send_reserved", email.id, actor="worker" if automatic else "operator")
            session.commit()
            # Any failure from this point is uncertain, including a crash before the call.
            # Never blindly retry an external send. Reconcile by deterministic Message-ID.
            try:
                outbound = self.mail.send(email.draft_id)
            except Exception:
                record = session.get(Send, email.id)
                record.state = "uncertain"
                email.status = "send_uncertain"
                audit(session, "send_uncertain", email.id)
                session.commit()
                raise
            record = session.get(Send, email.id)
            record.state, record.outbound_id = "sent", outbound
            email.status = "sent"
            audit(session, "reply_sent", email.id, automatic=automatic)
            session.commit()

    def approve(self, message_id, response, reason):
        with self.factory() as session:
            email = session.scalar(select(Message).where(Message.id == message_id).with_for_update())
            if email and not origin_matches(session, email, self.config):
                raise Conflict("Message belongs to another provider context")
            if not email or email.status != "draft" or session.get(Send, message_id):
                raise Conflict("A confirmed, unsent draft is required")
            if email.risk_tags or email.disposition == "escalate" or SAFETY.search(response):
                raise Conflict("Risk-tagged cases require the existing human support route")
            if not self.sources_current(session, email):
                raise Conflict("Current approved source evidence is required")
            email.response = response
            email.disposition = "review"
            email.status = "draft_updating"
            audit(session, "review_started", message_id, actor="operator", reason=reason)
            session.commit()
            try:
                draft_id = self.mail.update_draft(email.draft_id, email, response, self.rfc_id(email.id))
            except Exception:
                email.status = "draft_uncertain"
                session.commit()
                raise
            email.draft_id, email.status, email.disposition = draft_id, "draft", "approved"
            audit(session, "response_approved", message_id, actor="operator", reason=reason,
                  response_checksum=hashlib.sha256(response.encode()).hexdigest())
            session.commit()

    def reconcile(self, message_id):
        if not isinstance(self.mail, Gmail):
            raise Conflict("Reconciliation requires Google mode")
        self.mail.verify_mailbox()
        with self.factory() as session:
            email = session.get(Message, message_id)
            if not email:
                raise Conflict("Message not found")
            record = session.get(Send, message_id)
            sent = self.mail.find_sent(self.rfc_id(message_id))
            if sent and record:
                record.state, record.outbound_id, email.status = "sent", sent, "sent"
            elif not record and email.status in {"draft_uncertain", "draft_creating"}:
                draft = self.mail.find_draft(self.rfc_id(message_id))
                if not draft:
                    raise Conflict("Draft not found; absence is not proof of failure. Inspect Gmail manually")
                email.draft_id, email.status = draft, "draft"
            else:
                raise Conflict("No confirmed send found; automatic retry remains blocked")
            audit(session, "operation_reconciled", message_id, actor="operator")
            session.commit()

    def sync_gmail(self):
        gmail = self.mail
        if not isinstance(gmail, Gmail):
            return
        profile = gmail.verify_mailbox()
        with self.factory() as session:
            cursor = session.get(State, "gmail_history")
            start = cursor.value if cursor else ""
        try:
            history = gmail.changes(start)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            history = None  # Expired cursor: bounded 7-day inbox reconciliation.
        ids = gmail.recent_ids() if history is None else list(dict.fromkeys(
            item["message"]["id"] for page in history for item in page.get("messagesAdded", [])
        ))
        with self.factory() as session:
            for message_id in ids:
                if session.get(Message, message_id):
                    continue
                email = gmail.fetch(message_id)
                if email:
                    ingest(session, email, self.config)
            value = profile["historyId"]  # Captured BEFORE fetch: concurrent arrivals replay safely.
            cursor = session.get(State, "gmail_history")
            if cursor:
                # Never move backward if duplicate sync jobs overlap.
                cursor.value = str(max(int(cursor.value), int(value)))
            else:
                session.add(State(key="gmail_history", value=value))
            audit(session, "gmail_sync_completed", "mailbox", fetched=len(ids))
            session.commit()

    def sync_drive(self):
        if self.config.configured_business and not self.config.drive_folder_id:
            return
        from app.business import active, decode, digest
        config_digest = None
        # Bind the in-flight index to one configuration while marking it uncertain.
        with self.factory() as session:
            if self.config.configured_business:
                record = session.scalar(select(Connector).where(Connector.id == "google").with_for_update())
                fields = decode(record, self.config) if record else {}
                if not active(session) or not record or any(getattr(self.config, k, None) != v for k, v in fields.items()):
                    raise Conflict("Google settings changed before sync")
                config_digest = digest(fields)
            state = session.get(State, "knowledge_sync")
            if state:
                state.value = "uncertain"
            else:
                session.add(State(key="knowledge_sync", value="uncertain"))
            session.commit()
        with self.factory() as session:
            approvals = {a.file_id: {"revision": a.revision, "modified_time": a.modified_time,
                                    "approved": a.approved, "metadata": a.source_metadata}
                         for a in session.scalars(select(DriveApproval))}
        inventory = Drive(self.config, approvals).documents()
        with self.factory() as session:
            if config_digest is not None:
                record = session.scalar(select(Connector).where(Connector.id == "google").with_for_update())
                if not record or not active(session) or digest(decode(record, self.config)) != config_digest:
                    raise Conflict("Google settings changed during sync")
            current_approvals = {a.file_id: {"revision": a.revision, "modified_time": a.modified_time,
                                           "approved": a.approved, "metadata": a.source_metadata}
                                 for a in session.scalars(select(DriveApproval).with_for_update())}
            def unchanged(file_id):
                return current_approvals.get(file_id) == approvals.get(file_id)
            for doc in session.scalars(select(Document).where(Document.id.like("drive:%"))):
                file_id = doc.id.removeprefix("drive:")
                if unchanged(file_id) or not current_approvals.get(file_id, {}).get("approved", True):
                    doc.approved = False
            for data in inventory:
                file_id = data.id.removeprefix("drive:")
                if unchanged(file_id) and current_approvals.get(file_id, {}).get("approved", True):
                    upsert_document(session, data)
            session.get(State, "knowledge_sync").value = "current"
            audit(session, "drive_sync_completed", "knowledge", documents=len(inventory))
            session.commit()


def initialize(engine, factory):
    from app.db import Base
    Base.metadata.create_all(engine)
    with factory() as session:
        for key, value in [("kill_switch", "on"), ("knowledge_sync", "current")]:
            if session.get(State, key) is None:
                session.add(State(key=key, value=value))
        session.commit()
