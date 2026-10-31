"""Separate storage and encryption context for the personal test workspace."""
import hashlib

from sqlalchemy.engine import make_url


TEST_SCHEMA = "supportflow_personal_test"


def personal_config(base):
    url = make_url(base.personal_test_database_url or base.database_url)
    if url.get_backend_name() == "sqlite" and not base.personal_test_database_url:
        if not url.database or url.database == ":memory:":
            raise ValueError("Personal tests require their own persistent SQLite file or PostgreSQL schema")
        url = url.set(database=url.database + ".personal-test")
    if url.get_backend_name() == "sqlite" and url == make_url(base.database_url):
        raise ValueError("Personal test storage must differ from company storage")
    material = base.connector_encryption_key or base.operator_token
    return base.model_copy(update={
        "workspace": "personal_test", "database_url": url.render_as_string(hide_password=False),
        "connector_encryption_key": hashlib.sha256((material + ":personal-test").encode()).hexdigest(),
        "connector_mode": "demo", "mailbox": "test@example.invalid", "gmail_access_token": "",
        "configured_business": False, "business_active": False, "review_only": True,
        "business_name": "Personal test", "business_industry": "Personal email testing",
        "escalation_email": "", "escalation_keywords": [], "response_tone": "professional",
        "google_refresh_token": "", "drive_folder_id": "", "gemini_api_key": "",
        "auto_send_enabled": False, "production_approved": False,
        "gmail_topic": "", "google_pubsub_audience": "", "google_pubsub_service_account": "",
    })
