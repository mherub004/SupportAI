from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmailInput(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    thread_id: str = Field(min_length=1, max_length=255)
    sender: str = Field(min_length=3, max_length=320)
    subject: str = Field(max_length=1000)
    body: str = Field(min_length=1, max_length=50000)
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("headers")
    @classmethod
    def lower_headers(cls, value):
        return {k.lower(): v for k, v in value.items()}


class KnowledgeInput(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    revision: str = Field(min_length=1, max_length=100)
    brand: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=100)
    language: Literal["de", "en"]
    owner: str = Field(min_length=1, max_length=200)
    approved: bool = False
    visibility: Literal["customer_safe", "internal", "retired"] = "customer_safe"
    effective_at: datetime
    expires_at: datetime | None = None
    content: str = Field(min_length=1, max_length=200000)
    url: str = Field(max_length=1000)
    customer_url: str = Field(default="", max_length=1000)

    @field_validator("effective_at", "expires_at")
    @classmethod
    def utc_dates(cls, value):
        from datetime import timezone
        if value is not None and value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    @field_validator("customer_url")
    @classmethod
    def optional_customer_url(cls, value):
        return cls.https_url(value) if value else ""

    @field_validator("url")
    @classmethod
    def https_url(cls, value):
        from urllib.parse import urlparse
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("A credential-free HTTPS source URL is required")
        return value


class Citation(BaseModel):
    document_id: str
    revision: str
    quote: str = Field(min_length=15, max_length=2000)


class Proposal(BaseModel):
    category: Literal["manual_link", "product_specs", "setup_faq", "clarification", "warranty", "complaint", "unknown"]
    response: str = Field(min_length=1, max_length=10000)
    citations: list[Citation] = Field(default_factory=list, max_length=10)
    uncertain: bool = True
    model_config = ConfigDict(extra="forbid")


class ReviewInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    response: str = Field(min_length=1, max_length=10000)
    reason: str = Field(min_length=3, max_length=500)


class OwnershipInput(BaseModel):
    paused: bool
    owner: str = Field(default="operator", max_length=100)


class ControlsInput(BaseModel):
    kill_switch: bool
