from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore", hide_input_in_errors=True)
    public_app_url: str = ""
    render_external_url: str = ""
    connector_encryption_key: str = ""
    configured_business: bool = False
    business_active: bool = False
    review_only: bool = False
    escalation_email: str = ""
    business_name: str = "SupportFlow AI"
    business_industry: str = "Customer support"
    response_tone: str = "professional"
    escalation_keywords: list[str] = []
    supported_languages: list[str] = ["en", "de"]
    database_url: str = "sqlite:///./supportflow.db"
    operator_token: str
    connector_mode: Literal["demo", "google"] = "demo"
    mailbox: str = "support@example.invalid"
    auto_send_enabled: bool = False
    production_approved: bool = False
    auto_send_categories: str = "manual_link,clarification"
    hourly_send_limit: int = 10
    gmail_access_token: str = ""
    google_refresh_token: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    salesforce_client_id: str = ""
    salesforce_client_secret: str = ""
    salesforce_login_url: str = "https://login.salesforce.com"
    netsuite_client_id: str = ""
    netsuite_client_secret: str = ""
    netsuite_account_id: str = ""
    google_pubsub_audience: str = ""
    google_pubsub_service_account: str = ""
    gmail_topic: str = ""
    drive_folder_id: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    retention_days: int = 30
    job_lease_seconds: int = 180

    @model_validator(mode="after")
    def validate_settings(self):
        if self.connector_encryption_key and len(self.connector_encryption_key) < 32:
            raise ValueError("CONNECTOR_ENCRYPTION_KEY must have at least 32 characters")
        if len(self.operator_token) < 32:
            raise ValueError("OPERATOR_TOKEN must have at least 32 characters")
        if self.hourly_send_limit < 1 or self.retention_days < 1 or self.job_lease_seconds < 30:
            raise ValueError("Send limit and retention must be positive; job lease must be >=30 seconds")
        if self.connector_mode == "google" and self.mailbox.endswith(".invalid"):
            raise ValueError("Set MAILBOX to the approved Gmail user mailbox")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
