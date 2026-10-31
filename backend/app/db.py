from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now():
    # UTC naive timestamps keep SQLite and PostgreSQL comparisons consistent.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    owner: Mapped[str] = mapped_column(String(100), default="")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    revision: Mapped[str] = mapped_column(String(100))
    checksum: Mapped[str] = mapped_column(String(64))
    brand: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100))
    language: Mapped[str] = mapped_column(String(2))
    owner: Mapped[str] = mapped_column(String(200))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    visibility: Mapped[str] = mapped_column(String(40), default="customer_safe")
    effective_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1000))
    customer_url: Mapped[str] = mapped_column(String(1000), default="")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    sender: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    headers: Mapped[dict] = mapped_column(JSON, default=dict)
    language: Mapped[str] = mapped_column(String(2), default="en")
    brand: Mapped[str] = mapped_column(String(40), default="unknown")
    model: Mapped[str] = mapped_column(String(100), default="unknown")
    category: Mapped[str] = mapped_column(String(50), default="unknown")
    disposition: Mapped[str] = mapped_column(String(30), default="pending")
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    risk_tags: Mapped[list] = mapped_column(JSON, default=list)
    response: Mapped[str] = mapped_column(Text, default="")
    citations: Mapped[list] = mapped_column(JSON, default=list)
    provider_version: Mapped[str] = mapped_column(String(100), default="")
    draft_id: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(300), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str] = mapped_column(String(100), default="")


class Send(Base):
    __tablename__ = "sends"
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(30), default="reserved")
    outbound_id: Mapped[str] = mapped_column(String(255), default="")
    rfc_message_id: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(300))
    actor: Mapped[str] = mapped_column(String(100), default="system")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class State(Base):
    __tablename__ = "state"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class CrmDelivery(Base):
    __tablename__ = "crm_deliveries"
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), primary_key=True)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    customer_id: Mapped[str] = mapped_column(String(100), default="")
    case_id: Mapped[str] = mapped_column(String(100), default="")
    activity_id: Mapped[str] = mapped_column(String(255), default="")
    target_origin: Mapped[str] = mapped_column(String(500), default="")
    activity_state: Mapped[str] = mapped_column(String(30), default="pending")
    case_state: Mapped[str] = mapped_column(String(30), default="pending")
    error: Mapped[str] = mapped_column(String(100), default="")


def database(url, workspace="company"):
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if workspace == "personal_test" and engine.dialect.name == "postgresql":
        from sqlalchemy.schema import CreateSchema
        from app.workspaces import TEST_SCHEMA
        with engine.begin() as connection:
            connection.execute(CreateSchema(TEST_SCHEMA, if_not_exists=True))
        engine = engine.execution_options(schema_translate_map={None: TEST_SCHEMA})
    return engine, sessionmaker(engine, expire_on_commit=False)


def audit(session, event, entity_id, actor="system", **details):
    session.add(Audit(event=event, entity_id=entity_id, actor=actor, details=details))


class BusinessConfig(Base):
    __tablename__ = "business_config"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Connector(Base):
    __tablename__ = "connectors"
    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    encrypted_config: Mapped[str] = mapped_column(Text)
    verified_digest: Mapped[str] = mapped_column(String(64), default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class MessageOrigin(Base):
    __tablename__ = "message_origins"
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), primary_key=True)
    origin: Mapped[str] = mapped_column(String(400))


class OAuthAttempt(Base):
    __tablename__ = "oauth_attempts"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(30))
    binding_hash: Mapped[str] = mapped_column(String(64))
    encrypted_payload: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


class DriveApproval(Base):
    __tablename__ = "drive_approvals"
    file_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    revision: Mapped[str] = mapped_column(String(100))
    modified_time: Mapped[str] = mapped_column(String(100))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    source_metadata: Mapped[dict] = mapped_column(JSON)
