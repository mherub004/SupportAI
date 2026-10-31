import pytest
from cryptography.fernet import InvalidToken

from app.business import cipher, decode, save_connector
from app.db import Connector, Job, Message, database
from app.oauth import redirect_uri, start
from app.service import Workflow, ingest, initialize
from app.worker import run_one
from app.workspaces import personal_config


def test_personal_storage_and_secrets_do_not_inherit_company_configuration(setup):
    base, _, _, _ = setup
    base.google_refresh_token = "company-refresh"
    base.gmail_access_token = "company-access"
    base.drive_folder_id = "company-folder"
    base.gemini_api_key = "company-gemini"
    base.auto_send_enabled = base.production_approved = True
    test = personal_config(base)
    assert test.database_url != base.database_url
    assert test.workspace == "personal_test"
    assert not any([test.google_refresh_token, test.gmail_access_token, test.drive_folder_id, test.gemini_api_key])
    assert not test.auto_send_enabled and not test.production_approved
    assert test.review_only
    assert not test.connector_encryption_key == base.connector_encryption_key


def test_company_credentials_and_messages_survive_test_operations(setup, email):
    base, _, company, _ = setup
    test = personal_config(base)
    engine, personal = database(test.database_url, test.workspace)
    initialize(engine, personal)
    with company() as session:
        save_connector(session, "gemini", {"gemini_api_key": "company-only"}, base)
        ingest(session, email, base)
        session.commit()
    with personal() as session:
        assert session.get(Connector, "gemini") is None
        assert session.get(Message, email.id) is None
        save_connector(session, "gemini", {"gemini_api_key": "personal-only"}, test)
        ingest(session, email, test)
        session.commit()
    assert run_one(personal, Workflow(test, personal))
    with personal() as session:
        assert session.get(Message, email.id).status == "draft"
        assert session.get(Job, "process:" + email.id).status == "done"
        assert decode(session.get(Connector, "gemini"), test)["gemini_api_key"] == "personal-only"
        encrypted = session.get(Connector, "gemini").encrypted_config
        with pytest.raises(InvalidToken):
            cipher(base).decrypt(encrypted.encode())
    with company() as session:
        assert session.get(Message, email.id).status == "queued"
        assert session.get(Job, "process:" + email.id).status == "pending"
        assert decode(session.get(Connector, "gemini"), base)["gemini_api_key"] == "company-only"


def test_company_api_refuses_personal_profile_conversion(setup):
    base, _, factory, _ = setup
    with factory() as session:
        with pytest.raises(ValueError, match="separate personal test"):
            start(session, "google", "b" * 40, base, personal=True)
        assert session.get(Connector, "google") is None


def test_company_and_test_have_distinct_registered_callback_paths(setup):
    base, _, _, _ = setup
    base.public_app_url = "https://support.example.com"
    assert redirect_uri(base, "google") == "https://support.example.com/api/oauth/callback/google"
    assert redirect_uri(personal_config(base), "google") == "https://support.example.com/api/oauth/callback/test/google"


def test_explicit_sqlite_test_database_cannot_point_to_company_file(setup):
    base, _, _, _ = setup
    base.personal_test_database_url = base.database_url
    with pytest.raises(ValueError, match="must differ"):
        personal_config(base)
