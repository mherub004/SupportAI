"""Per-installation business onboarding. No shared multi-tenant authorization is implied."""
import base64
import hashlib
import json
from datetime import timedelta
from email.utils import parseaddr
from typing import Literal

import httpx
from cryptography.fernet import Fernet
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.db import Message, BusinessConfig, Connector, Document, Job, MessageOrigin, State, audit, now
from app.policy import current, valid_recipient

SECRET_FIELDS = {"google_refresh_token", "google_client_secret", "gmail_access_token", "gemini_api_key"}
FIELDS = {
    "google": {"mailbox", "google_client_id", "google_client_secret", "google_refresh_token",
               "gmail_access_token", "drive_folder_id", "gmail_topic", "google_pubsub_audience",
               "google_pubsub_service_account"},
    "gemini": {"gemini_api_key", "gemini_model"},
}


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=120)
    industry: str = Field(default="General customer support", min_length=2, max_length=120)
    website: str = Field(default="", max_length=500)
    support_email: str = Field(min_length=3, max_length=320)
    escalation_email: str = Field(min_length=3, max_length=320)
    languages: list[Literal["en", "de"]] = Field(default_factory=lambda: ["en"], min_length=1, max_length=2)
    tone: Literal["professional", "friendly", "concise"] = "professional"
    escalation_keywords: list[str] = Field(default_factory=list, max_length=50)
    acknowledgement: bool = False

    @field_validator("support_email", "escalation_email")
    @classmethod
    def email_address(cls, value):
        if not valid_recipient(value) or parseaddr(value)[1] != value:
            raise ValueError("Enter a single email address without a display name")
        return value.casefold()

    @field_validator("website")
    @classmethod
    def website_url(cls, value):
        if value:
            from app.schemas import KnowledgeInput
            KnowledgeInput.https_url(value)
        return value

    @field_validator("escalation_keywords")
    @classmethod
    def keywords(cls, value):
        if any(not word.strip() or len(word) > 100 for word in value):
            raise ValueError("Escalation keywords must be 1–100 characters")
        return [word.strip().casefold() for word in value]


class ConnectorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: dict[str, str]

    @field_validator("fields")
    @classmethod
    def bounded_fields(cls, value):
        if len(value) > 12 or any(len(v) > 16000 for v in value.values()):
            raise ValueError("Connector configuration is too large")
        return value


def cipher(config):
    material = config.connector_encryption_key or config.operator_token
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest()))


def decode(record, config):
    return json.loads(cipher(config).decrypt(record.encrypted_config.encode()))


def digest(fields):
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def profile(session):
    record = session.get(BusinessConfig, "profile")
    return record.value if record else None


def active(session):
    record = session.get(BusinessConfig, "activation")
    return bool(record and record.value.get("active"))


def pause(session):
    record = session.get(BusinessConfig, "activation")
    if record:
        record.value = {"active": False}
    else:
        session.add(BusinessConfig(key="activation", value={"active": False}))
    switch = session.get(State, "kill_switch")
    if switch:
        switch.value = "on"


def runtime(base, factory):
    with factory() as session:
        business = profile(session)
        if not business:
            return base
        updates = {"configured_business": True, "business_active": active(session), "review_only": True,
                   "auto_send_enabled": False, "production_approved": False,
                   "business_name": business["name"], "business_industry": business["industry"],
                   "response_tone": business["tone"], "escalation_keywords": business["escalation_keywords"],
                   "supported_languages": business["languages"], "escalation_email": business["escalation_email"], "mailbox": business["support_email"]}
        if not updates["business_active"]:
            updates["connector_mode"] = "demo"
        else:
            for key in FIELDS:
                record = session.get(Connector, key)
                if not record or not record.enabled:
                    raise ValueError("Active business requires connected providers")
                updates.update(decode(record, base))
            updates["connector_mode"] = "google"
        return base.model_copy(update=updates)


def origin(config):
    return "demo" if config.connector_mode == "demo" else "google:" + config.mailbox.casefold()


def origin_matches(session, email, config):
    if config.configured_business and not config.business_active:
        return False
    record = session.get(MessageOrigin, email.id)
    if record:
        return record.origin == origin(config)
    # Pre-upgrade records are safe to simulate only; never send them to a live provider.
    return config.connector_mode == "demo" and not config.configured_business


def public_connector(record, base):
    if not record or not record.enabled:
        return {"configured": False, "fields": {}, "secret_fields_set": [], "verified": False}
    fields = decode(record, base)
    return {"configured": True,
            "fields": {k: v for k, v in fields.items() if k not in SECRET_FIELDS},
            "secret_fields_set": [k for k in SECRET_FIELDS if fields.get(k)],
            "verified": bool(record.verified_at and record.verified_at > now() - timedelta(hours=24)
                             and record.verified_digest == digest(fields)),
            "verified_at": record.verified_at}


def save_connector(session, key, data, base):
    if key not in FIELDS or set(data) - FIELDS[key]:
        raise ValueError("Unsupported connector or configuration field")
    record = session.get(Connector, key)
    fields = decode(record, base) if record and record.enabled else {}
    # Blank secret inputs preserve existing credentials; disconnect removes them.
    fields.update({k: v.strip() for k, v in data.items() if k not in SECRET_FIELDS or v.strip()})
    if key == "google" and fields.get("mailbox"):
        address = fields["mailbox"]
        if not valid_recipient(address) or parseaddr(address)[1] != address or address.endswith(".invalid"):
            raise ValueError("A real, single Gmail mailbox address is required")
        fields["mailbox"] = address.casefold()
    if key == "gemini":
        fields["gemini_model"] = fields.get("gemini_model") or base.gemini_model
        import re
        if fields.get("gemini_model") and not re.fullmatch(r"[A-Za-z0-9._-]+", fields["gemini_model"]):
            raise ValueError("Invalid model identifier")
    ciphertext = cipher(base).encrypt(json.dumps(fields).encode()).decode()
    if record:
        record.encrypted_config, record.enabled = ciphertext, True
        record.verified_at, record.verified_digest = None, ""
    else:
        session.add(Connector(id=key, encrypted_config=ciphertext))
    pause(session)
    audit(session, "connector_saved", key, actor="operator", changed_fields=sorted(data))


def verify_connector(key, fields, base):
    from app.google import Gmail, GoogleClient
    config = base.model_copy(update=fields)
    if key == "google":
        if not fields.get("mailbox"):
            raise ValueError("Mailbox is required")
        if not (fields.get("gmail_access_token") or all(fields.get(k) for k in (
                "google_client_id", "google_client_secret", "google_refresh_token"))):
            raise ValueError("Provide an OAuth refresh configuration or a test access token")
        Gmail(config).verify_mailbox()
        if fields.get("drive_folder_id"):
            from urllib.parse import quote
            folder = GoogleClient(config).request("GET", "drive/v3/files/" + quote(fields["drive_folder_id"], safe=""),
                                                  params={"fields": "id,mimeType", "supportsAllDrives": "true"}).json()
            if folder.get("mimeType") != "application/vnd.google-apps.folder":
                raise ValueError("Drive ID must identify an approved folder")
    elif key == "gemini":
        if not fields.get("gemini_api_key"):
            raise ValueError("Gemini API key is required")
        model = fields.get("gemini_model") or base.gemini_model
        response = httpx.get(f"https://generativelanguage.googleapis.com/v1beta/models/{model}",
                             headers={"x-goog-api-key": fields["gemini_api_key"]}, timeout=20)
        response.raise_for_status()
        if "generateContent" not in response.json().get("supportedGenerationMethods", []):
            raise ValueError("Choose a model supporting content generation")
    else:
        raise ValueError("Unsupported connector")


def readiness(session, base):
    business = profile(session)
    docs = [d for d in session.scalars(select(Document)) if not d.id.startswith("demo-") and current(d)]
    connections = {key: public_connector(session.get(Connector, key), base) for key in FIELDS}
    return {"profile": business, "active": active(session), "connectors": connections,
            "checks": {"company_profile": bool(business),
                       "approved_knowledge": bool(docs),
                       "google_verified": connections["google"]["verified"],
                       "gemini_verified": connections["gemini"]["verified"],
                       "policy_acknowledged": bool(business and business.get("acknowledgement"))},
            "deployment_model": "One isolated deployment and database per company",
            "supported_integrations": ["Gmail", "Google Drive", "Gemini", "Manual knowledge"],
            "unavailable_integrations": ["Microsoft 365", "Salesforce", "Shopify", "WhatsApp"],
            "sending_mode": "draft_only"}


def activate(session, base):
    from app.service import Conflict
    status = readiness(session, base)
    if not all(status["checks"].values()):
        raise Conflict("Complete all readiness checks before activating draft processing")
    fields = decode(session.get(Connector, "google"), base)
    if fields["mailbox"] != status["profile"]["support_email"]:
        raise Conflict("Connected mailbox must match the company support email")
    if session.scalar(select(Job.id).where(Job.status == "working").limit(1)):
        raise Conflict("A worker operation is running; retry after it finishes")
    # Switching live identities in an installation is unsafe: use a separate deployment.
    other = session.scalar(select(MessageOrigin.message_id).where(
        MessageOrigin.origin != "demo", MessageOrigin.origin != "google:" + fields["mailbox"]).limit(1))
    if other:
        raise Conflict("This installation already contains another live mailbox; use an isolated deployment")
    unknown = session.scalar(select(Message.id).outerjoin(MessageOrigin).where(
        MessageOrigin.message_id.is_(None), ~Message.id.like("demo-%")).limit(1))
    if unknown:
        raise Conflict("Unclassified legacy messages exist; migrate their provider identity before activation")
    pause(session)
    # A fresh connection must reconcile its own Gmail history, never a previous identity's cursor.
    cursor = session.get(State, "gmail_history")
    if cursor:
        session.delete(cursor)
    session.get(BusinessConfig, "activation").value = {"active": True}
    audit(session, "business_activated_draft_only", "business", actor="operator")


def install_routes(app, base, factory, operator):
    from fastapi import Depends, HTTPException
    from app.service import Conflict
    secured = [Depends(operator)]

    @app.get("/api/business", dependencies=secured)
    def get_business():
        with factory() as session:
            return readiness(session, base)

    @app.put("/api/business/profile", dependencies=secured)
    def put_profile(data: Profile):
        with factory() as session:
            existing = profile(session)
            if existing and existing["support_email"] != data.support_email:
                if session.scalar(select(MessageOrigin.message_id).where(MessageOrigin.origin != "demo").limit(1)):
                    raise Conflict("Live mailbox identity is fixed; deploy a separate instance for a different company/mailbox")
            record = session.get(BusinessConfig, "profile")
            if record:
                record.value = data.model_dump()
            else:
                session.add(BusinessConfig(key="profile", value=data.model_dump()))
            pause(session)
            audit(session, "business_profile_saved", "business", actor="operator")
            session.commit()
        return {"status": "saved", "sending_mode": "draft_only"}

    @app.put("/api/business/connectors/{key}", dependencies=secured)
    def put_connector(key: str, data: ConnectorInput):
        with factory() as session:
            try:
                save_connector(session, key, data.fields, base)
            except ValueError:
                raise HTTPException(422, "Unsupported connector, field, or invalid configuration") from None
            session.commit()
        return {"status": "saved", "verification_required": True}

    @app.delete("/api/business/connectors/{key}", dependencies=secured)
    def disconnect(key: str):
        if key not in FIELDS:
            raise HTTPException(404, "Connector not found")
        with factory() as session:
            record = session.get(Connector, key)
            if record:
                session.delete(record)
            pause(session)
            audit(session, "connector_disconnected", key, actor="operator")
            session.commit()
        return {"status": "disconnected"}

    @app.post("/api/business/connectors/{key}/verify", dependencies=secured)
    def verify(key: str):
        if key not in FIELDS:
            raise HTTPException(404, "Connector not found")
        with factory() as session:
            record = session.get(Connector, key)
            if not record or not record.enabled:
                raise Conflict("Save this connection first")
            fields = decode(record, base)
            tested_digest = digest(fields)
        try:
            verify_connector(key, fields, base)
        except Exception:
            with factory() as session:
                record = session.get(Connector, key)
                if record:
                    record.verified_at, record.verified_digest = None, ""
                pause(session)
                audit(session, "connector_verification_failed", key, actor="operator")
                session.commit()
            raise HTTPException(422, "Connection verification failed. Check credentials, mailbox identity, model/folder access and outbound networking. No customer messages were sent.") from None
        with factory() as session:
            record = session.get(Connector, key)
            if not record or digest(decode(record, base)) != tested_digest:
                raise Conflict("Configuration changed during verification; test it again")
            record.verified_digest, record.verified_at = tested_digest, now()
            audit(session, "connector_verified", key, actor="operator")
            session.commit()
        return {"status": "verified", "valid_hours": 24}

    @app.post("/api/business/activate", dependencies=secured)
    def activate_business():
        with factory() as session:
            activate(session, base)
            session.commit()
        return {"status": "active", "sending_mode": "draft_only"}

    @app.post("/api/business/pause", dependencies=secured)
    def pause_business():
        with factory() as session:
            pause(session)
            audit(session, "business_paused", "business", actor="operator")
            session.commit()
        return {"status": "paused"}
