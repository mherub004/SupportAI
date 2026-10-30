import base64
import hmac
import json
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, select, text

from app.config import settings
from app.business import runtime, install_routes
from app.db import MessageOrigin, Audit, Conversation, Document, Job, Message, Send, State, audit, database, now
from app.schemas import ControlsInput, EmailInput, KnowledgeInput, OwnershipInput, ReviewInput
from app.service import Conflict, Workflow, enqueue, ingest, initialize, upsert_document


def create_app(config=None, db=None, workflow=None):
    config = config or settings()
    engine, factory = db or database(config.database_url)

    @asynccontextmanager
    async def lifespan(app):
        initialize(engine, factory)
        yield

    app = FastAPI(title="SupportFlow AI", version="0.1.0", lifespan=lifespan)
    app.state.factory = factory
    app.state.config = config

    def flow():
        return workflow or Workflow(runtime(config, factory), factory)

    def operator(authorization: str = Header(default="")):
        if not hmac.compare_digest(authorization, "Bearer " + config.operator_token):
            raise HTTPException(401, "Operator authentication required")

    def session_dep():
        with factory() as session:
            yield session

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse(status_code=422, content={
            "detail": "Invalid request fields. Check required values, formats and length limits.",
            "fields": [".".join(map(str, item["loc"])) for item in exc.errors()],
        })

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.middleware("http")
    async def redacted_failures(request, call_next):
        try:
            return await call_next(request)
        except Exception:
            # Catch before the server logger: DB/provider exception tracebacks can include PII.
            # Expected conflicts are handled separately and remain actionable to the operator.
            return JSONResponse(status_code=503, content={
                "detail": "Operation failed; inspect audit metadata and connector configuration"
            })

    @app.get("/health")
    def health():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    secured = [Depends(operator)]

    @app.get("/api/overview", dependencies=secured)
    def overview(session=Depends(session_dep)):
        effective = runtime(config, factory)
        count_query = select(Message.status, func.count()).group_by(Message.status)
        if effective.configured_business:
            count_query = count_query.join(MessageOrigin).where(MessageOrigin.origin == "google:" + effective.mailbox.casefold())
        counts = dict(session.execute(count_query).all())
        state = session.get(State, "kill_switch")
        return {"mode": ("setup" if effective.configured_business and not effective.business_active else effective.connector_mode), "mailbox": effective.mailbox, "company_name": effective.business_name, "draft_only": effective.review_only, "drive_connected": bool(effective.drive_folder_id), "escalation_email": effective.escalation_email, "counts": counts,
                "kill_switch": state is None or state.value != "off",
                "auto_send_enabled": effective.auto_send_enabled and effective.production_approved,
                "knowledge_sync": session.get(State, "knowledge_sync").value,
                "failed_jobs": session.scalar(select(func.count()).select_from(Job).where(Job.status == "failed")),
                "pending_jobs": session.scalar(select(func.count()).select_from(Job).where(Job.status.in_(["pending", "working"]))),
                "documents": session.scalar(select(func.count()).select_from(Document))}

    @app.get("/api/messages", dependencies=secured)
    def messages(session=Depends(session_dep)):
        effective = runtime(config, factory)
        query = select(Message)
        if effective.configured_business:
            query = query.join(MessageOrigin).where(MessageOrigin.origin == "google:" + effective.mailbox.casefold())
        return [{"id": m.id, "thread_id": m.thread_id, "sender": m.sender, "subject": m.subject,
                 "status": m.status, "disposition": m.disposition, "language": m.language,
                 "brand": m.brand, "risk_tags": m.risk_tags, "created_at": m.created_at}
                for m in session.scalars(query.order_by(Message.created_at.desc()).limit(200))]

    @app.get("/api/messages/{message_id}", dependencies=secured)
    def message(message_id: str, session=Depends(session_dep)):
        m = session.get(Message, message_id)
        effective = runtime(config, factory)
        entry = session.get(MessageOrigin, message_id)
        if not m or (effective.configured_business and (not entry or entry.origin != "google:" + effective.mailbox.casefold())):
            raise HTTPException(404, "Message not found")
        conversation = session.get(Conversation, m.thread_id)
        send = session.get(Send, m.id)
        return {"id": m.id, "thread_id": m.thread_id, "sender": m.sender, "subject": m.subject,
                "body": m.body, "response": m.response, "status": m.status, "disposition": m.disposition,
                "risk_tags": m.risk_tags, "citations": m.citations, "category": m.category,
                "brand": m.brand, "model": m.model, "language": m.language, "draft_id": m.draft_id,
                "provider_version": m.provider_version, "paused": conversation.paused,
                "owner": conversation.owner, "send_state": send.state if send else None}

    @app.post("/api/demo/messages", status_code=202, dependencies=secured)
    def demo_ingest(email: EmailInput, session=Depends(session_dep)):
        effective = runtime(config, factory)
        if effective.configured_business or effective.connector_mode != "demo":
            raise HTTPException(403, "Demo ingest is disabled in Google mode")
        created = ingest(session, email, config)
        session.commit()
        return {"created": created}

    @app.post("/api/messages/{message_id}/approve", dependencies=secured)
    def approve(message_id: str, data: ReviewInput):
        flow().approve(message_id, data.response, data.reason)
        return {"status": "approved"}

    @app.post("/api/messages/{message_id}/send", dependencies=secured)
    def send(message_id: str):
        flow().deliver(message_id)
        return {"status": "sent"}

    @app.post("/api/messages/{message_id}/reconcile", dependencies=secured)
    def reconcile(message_id: str):
        flow().reconcile(message_id)
        return {"status": "reconciled"}

    @app.put("/api/threads/{thread_id}/ownership", dependencies=secured)
    def ownership(thread_id: str, data: OwnershipInput, session=Depends(session_dep)):
        conversation = session.scalar(select(Conversation).where(Conversation.id == thread_id).with_for_update())
        if not conversation:
            raise HTTPException(404, "Thread not found")
        conversation.paused, conversation.owner = data.paused, data.owner
        audit(session, "ownership_changed", thread_id, actor="operator", paused=data.paused, owner=data.owner)
        session.commit()
        return {"paused": conversation.paused}

    @app.put("/api/controls", dependencies=secured)
    def controls(data: ControlsInput, session=Depends(session_dep)):
        if not data.kill_switch and runtime(config, factory).review_only:
            raise Conflict("Business setup is draft-only; sending stays disabled")
        record = session.scalar(select(State).where(State.key == "kill_switch").with_for_update())
        record.value = "on" if data.kill_switch else "off"
        audit(session, "kill_switch_changed", "mailbox", actor="operator", enabled=data.kill_switch)
        session.commit()
        return {"kill_switch": data.kill_switch}

    @app.get("/api/knowledge", dependencies=secured)
    def knowledge(session=Depends(session_dep)):
        effective = runtime(config, factory)
        return [{"id": d.id, "title": d.title, "revision": d.revision, "brand": d.brand,
                 "model": d.model, "language": d.language, "owner": d.owner, "approved": d.approved,
                 "visibility": d.visibility, "url": d.url, "customer_url": d.customer_url, "effective_at": d.effective_at,
                 "expires_at": d.expires_at, "checksum": d.checksum}
                for d in session.scalars(select(Document).order_by(Document.title).limit(500))
                if not effective.configured_business or not d.id.startswith("demo-")]

    @app.put("/api/knowledge", dependencies=secured)
    def put_knowledge(data: KnowledgeInput, session=Depends(session_dep)):
        if data.id.startswith("drive:"):
            raise HTTPException(403, "Drive records are managed by sync, not manual edits")
        upsert_document(session, data)
        session.commit()
        return {"status": "saved"}

    @app.post("/api/knowledge/{document_id}/retire", dependencies=secured)
    def retire_knowledge(document_id: str, session=Depends(session_dep)):
        if document_id.startswith("drive:"):
            raise Conflict("Change approval in Drive and synchronize the source")
        document = session.get(Document, document_id)
        if not document:
            raise HTTPException(404, "Knowledge source not found")
        document.approved, document.visibility = False, "retired"
        audit(session, "knowledge_retired", document_id, actor="operator")
        session.commit()
        return {"status": "retired"}

    @app.post("/api/sync/{kind}", status_code=202, dependencies=secured)
    def sync(kind: str, session=Depends(session_dep)):
        effective = runtime(config, factory)
        if effective.connector_mode != "google" or kind not in {"gmail", "drive", "watch"}:
            raise HTTPException(400, "Google mode and gmail, drive or watch are required")
        if kind == "drive" and not effective.drive_folder_id:
            raise Conflict("Configure and verify a Drive folder first")
        job_kind = "watch" if kind == "watch" else kind + "_sync"
        key = f"{job_kind}:manual:{int(now().timestamp())}"
        enqueue(session, key, job_kind, {})
        audit(session, "sync_requested", kind, actor="operator")
        session.commit()
        return {"job_id": key}

    @app.get("/api/audit", dependencies=secured)
    def audits(session=Depends(session_dep)):
        return [{"id": a.id, "event": a.event, "entity_id": a.entity_id, "actor": a.actor,
                 "details": a.details, "created_at": a.created_at}
                for a in session.scalars(select(Audit).order_by(Audit.id.desc()).limit(200))]

    @app.get("/api/jobs", dependencies=secured)
    def jobs(session=Depends(session_dep)):
        return [{"id": j.id, "kind": j.kind, "status": j.status, "attempts": j.attempts,
                 "error": j.error, "available_at": j.available_at}
                for j in session.scalars(select(Job).order_by(Job.available_at.desc()).limit(100))]

    @app.post("/webhooks/gmail", status_code=202)
    def webhook(request: Request, envelope: dict, authorization: str = Header(default=""),
                session=Depends(session_dep)):
        effective = runtime(config, factory)
        if (effective.connector_mode != "google" or not effective.google_pubsub_audience
                or not effective.google_pubsub_service_account):
            raise HTTPException(503, "Authenticated Pub/Sub is not configured")
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2.id_token import verify_oauth2_token
        try:
            scheme, token = authorization.split(" ", 1)
            if scheme.lower() != "bearer":
                raise ValueError("Bearer token required")
            claims = verify_oauth2_token(token, GoogleRequest(), audience=effective.google_pubsub_audience)
            if (claims.get("email") != effective.google_pubsub_service_account or claims.get("email_verified") is not True):
                raise ValueError("Unexpected push identity")
        except Exception:
            raise HTTPException(401, "Invalid Pub/Sub identity") from None
        try:
            notification = json.loads(base64.b64decode(envelope["message"]["data"], validate=True))
            if notification["emailAddress"].casefold() != effective.mailbox.casefold():
                raise ValueError("Wrong mailbox")
            history_id = str(notification["historyId"])
            if not history_id.isdigit():
                raise ValueError("Invalid history ID")
        except (KeyError, ValueError, TypeError):
            raise HTTPException(400, "Invalid Gmail notification") from None
        enqueue(session, "gmail_event:" + history_id, "gmail_sync", {})
        session.commit()
        return {"status": "queued"}

    install_routes(app, config, factory, operator)
    return app
