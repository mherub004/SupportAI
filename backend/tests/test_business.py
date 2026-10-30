from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.business import decode, runtime
from app.db import Document, Connector, Message, now
from app.main import create_app
from app.schemas import EmailInput, KnowledgeInput
from app.service import Conflict, Workflow, ingest, upsert_document

PROFILE = {"name": "Acme Services", "industry": "Customer services", "website": "https://example.invalid",
           "support_email": "support@acme.example", "escalation_email": "human@acme.example",
           "languages": ["en", "de"], "tone": "friendly", "escalation_keywords": ["legal advice"],
           "acknowledgement": True}


@pytest.fixture
def client(setup):
    config, engine, factory, _ = setup
    with TestClient(create_app(config, (engine, factory))) as client:
        client.headers["Authorization"] = "Bearer " + config.operator_token
        yield client


def configure(client, setup, monkeypatch):
    assert client.put("/api/business/profile", json=PROFILE).status_code == 200
    assert client.put("/api/business/connectors/google", json={"fields": {
        "mailbox": PROFILE["support_email"], "gmail_access_token": "private-test-google-token"
    }}).status_code == 200
    assert client.put("/api/business/connectors/gemini", json={"fields": {
        "gemini_api_key": "private-test-gemini-key", "gemini_model": ""
    }}).status_code == 200
    monkeypatch.setattr("app.business.verify_connector", lambda *a: None)
    assert client.post("/api/business/connectors/google/verify").status_code == 200
    assert client.post("/api/business/connectors/gemini/verify").status_code == 200
    config, _, factory, _ = setup
    with factory() as session:
        upsert_document(session, KnowledgeInput(
            id="acme-policy", title="Acme account policy", revision="1", brand="Acme Services", model="general",
            language="en", owner="Acme reviewer", approved=True, effective_at=now()-timedelta(days=1),
            content="Acme account support is available through the approved customer portal.",
            url="https://example.invalid/internal", customer_url="https://example.invalid/help",
        ))
        session.commit()


def test_business_requires_auth(setup):
    config, engine, factory, _ = setup
    with TestClient(create_app(config, (engine, factory))) as client:
        assert client.get("/api/business").status_code == 401
        assert client.put("/api/business/profile", json=PROFILE).status_code == 401


def test_unconfigured_deployment_is_ready_for_later_connections(client):
    result = client.get("/api/business").json()
    assert result["profile"] is None
    assert not result["active"]
    assert not any(result["checks"].values())
    assert "Microsoft 365" in result["unavailable_integrations"]
    assert client.post("/api/business/activate").status_code == 409


def test_encrypted_credentials_never_return_or_enter_audit(client, setup):
    token = "sensitive-example-gemini-token"
    assert client.put("/api/business/connectors/gemini", json={"fields": {"gemini_api_key": token}}).status_code == 200
    response = client.get("/api/business")
    assert token not in response.text
    assert "gemini_api_key" in response.json()["connectors"]["gemini"]["secret_fields_set"]
    assert token not in client.get("/api/audit").text
    config, _, factory, _ = setup
    with factory() as session:
        record = session.get(Connector, "gemini")
        assert token not in record.encrypted_config
        assert decode(record, config)["gemini_api_key"] == token


def test_blank_secret_preserves_and_disconnect_removes(client, setup):
    client.put("/api/business/connectors/gemini", json={"fields": {"gemini_api_key": "saved-secret"}})
    client.put("/api/business/connectors/gemini", json={"fields": {"gemini_api_key": "", "gemini_model": "gemini-2.5-flash"}})
    config, _, factory, _ = setup
    with factory() as session:
        assert decode(session.get(Connector, "gemini"), config)["gemini_api_key"] == "saved-secret"
    assert client.delete("/api/business/connectors/gemini").status_code == 200
    with factory() as session:
        assert session.get(Connector, "gemini") is None
    assert not client.get("/api/business").json()["active"]


@pytest.mark.parametrize("key,fields", [("shopify", {}), ("google", {"unexpected": "value"}),
                                       ("google", {"mailbox": "a@b.example, other@b.example"}),
                                       ("gemini", {"gemini_model": "../../bad"})])
def test_bad_connector_configuration_is_rejected(client, key, fields):
    assert client.put(f"/api/business/connectors/{key}", json={"fields": fields}).status_code == 422


def test_activation_hot_reloads_verified_connections_and_stays_draft_only(client, setup, monkeypatch):
    configure(client, setup, monkeypatch)
    assert all(client.get("/api/business").json()["checks"].values())
    assert client.post("/api/business/activate").status_code == 200
    config, _, factory, _ = setup
    effective = runtime(config, factory)
    assert effective.connector_mode == "google"
    assert effective.mailbox == PROFILE["support_email"]
    assert effective.gemini_api_key == "private-test-gemini-key"
    assert effective.gemini_model == config.gemini_model
    assert effective.review_only and not effective.auto_send_enabled
    assert client.get("/api/overview").json()["draft_only"]
    assert client.put("/api/controls", json={"kill_switch": False}).status_code == 409
    with pytest.raises(Conflict, match="draft-only"):
        Workflow(effective, factory).deliver("any-message")


def test_stale_verification_blocks_activation(client, setup, monkeypatch):
    configure(client, setup, monkeypatch)
    _, _, factory, _ = setup
    with factory() as session:
        session.get(Connector, "google").verified_at = now()-timedelta(hours=25)
        session.commit()
    assert client.post("/api/business/activate").status_code == 409


def test_changing_connector_invalidates_verification_and_pauses(client, setup, monkeypatch):
    configure(client, setup, monkeypatch)
    client.post("/api/business/activate")
    client.put("/api/business/connectors/gemini", json={"fields": {"gemini_model": "another-model"}})
    response = client.get("/api/business").json()
    assert not response["active"]
    assert not response["connectors"]["gemini"]["verified"]
    assert client.get("/api/overview").json()["mode"] == "setup"


def test_verification_failure_is_redacted(client, monkeypatch):
    client.put("/api/business/connectors/gemini", json={"fields": {"gemini_api_key": "secret-one"}})

    def fail(*args):
        raise RuntimeError("provider-secret-one-sensitive-error")

    monkeypatch.setattr("app.business.verify_connector", fail)
    response = client.post("/api/business/connectors/gemini/verify")
    assert response.status_code == 422
    assert "secret-one" not in response.text
    assert "secret-one" not in client.get("/api/audit").text


def test_demo_records_never_reach_live_mail_provider(client, setup, email, document, monkeypatch):
    config, _, factory, _ = setup
    with factory() as session:
        upsert_document(session, document)
        ingest(session, email, config)
        session.commit()
    configure(client, setup, monkeypatch)
    assert client.post("/api/business/activate").status_code == 200
    effective = runtime(config, factory)
    workflow = Workflow(effective, factory)
    workflow.process(email.id)
    with factory() as session:
        assert session.get(Message, email.id).status == "archived"
    assert client.get("/api/messages").json() == []
    assert client.get("/api/messages/"+email.id).status_code == 404
    assert client.post("/api/demo/messages", json=email.model_dump()).status_code == 403


def test_live_company_identity_cannot_be_reassigned(client, setup, monkeypatch):
    configure(client, setup, monkeypatch)
    client.post("/api/business/activate")
    config, _, factory, _ = setup
    effective = runtime(config, factory)
    with factory() as session:
        ingest(session, EmailInput(id="live-id", thread_id="live-thread", sender="customer@example.invalid",
                                   subject="Support", body="An account question"), effective)
        session.commit()
    response = client.put("/api/business/profile", json={**PROFILE, "support_email": "other@company.example"})
    assert response.status_code == 409


def test_custom_company_knowledge_and_general_policy_work(client, setup, monkeypatch):
    from app.google import DemoMail
    from app.providers import DemoModel
    configure(client, setup, monkeypatch)
    client.post("/api/business/activate")
    config, _, factory, _ = setup
    effective = runtime(config, factory)
    email = EmailInput(id="custom-brand", thread_id="custom-thread", sender="customer@example.invalid",
                       subject="Account help", body="Where can I find Acme Services account help?")
    with factory() as session:
        ingest(session, email, effective)
        session.commit()
    Workflow(effective, factory, mail=DemoMail(), model=DemoModel()).process(email.id)
    with factory() as session:
        result = session.get(Message, email.id)
        assert result.brand == "Acme Services"
        assert result.model == "general"
        assert result.citations[0]["document_id"] == "acme-policy"
        assert result.status == "draft"


def test_invalid_secret_payload_is_never_echoed(client):
    secret = "private-data" * 1500
    response = client.put("/api/business/connectors/gemini", json={"fields": {"gemini_api_key": secret}})
    assert response.status_code == 422
    assert "private-data" not in response.text


def test_retired_source_invalidates_readiness(client, setup, monkeypatch):
    configure(client, setup, monkeypatch)
    assert client.get("/api/business").json()["checks"]["approved_knowledge"]
    assert client.post("/api/knowledge/acme-policy/retire").status_code == 200
    assert not client.get("/api/business").json()["checks"]["approved_knowledge"]
    assert client.post("/api/business/activate").status_code == 409


def test_additive_schema_upgrade_preserves_existing_data(prepared):
    from app.db import BusinessConfig, Connector, MessageOrigin
    from app.service import initialize
    _, engine, factory, _ = prepared
    # Simulate the original release's schema before additive onboarding tables.
    MessageOrigin.__table__.drop(engine)
    Connector.__table__.drop(engine)
    BusinessConfig.__table__.drop(engine)
    initialize(engine, factory)
    with factory() as session:
        assert session.get(Message, "incoming-1").status == "draft"
        assert session.get(Document, "manual").approved
        assert session.get(BusinessConfig, "profile") is None
