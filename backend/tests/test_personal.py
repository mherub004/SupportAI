from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from app.business import Profile, decode, profile, readiness
from app.db import BusinessConfig, Connector, MessageOrigin
from app.main import create_app
from app.oauth import finish, start
from app.service import ingest


def host(base):
    base.workspace = "personal_test"
    base.public_app_url = "https://support.example.com"
    base.google_client_id = "synthetic-host-client"
    base.google_client_secret = "synthetic-host-secret"


def begin(base, factory):
    with factory() as session:
        result = start(session, "google", "b" * 40, base, personal=True)
    return parse_qs(urlsplit(result["authorization_url"]).query)["state"][0]


def provider(monkeypatch, mailbox="person@example.com"):
    monkeypatch.setattr("app.oauth.httpx.post", lambda *a, **k: httpx.Response(
        200, json={"access_token": "personal-access", "refresh_token": "personal-refresh"},
        request=httpx.Request("POST", "https://oauth2.googleapis.com/token")))
    monkeypatch.setattr("app.google.Gmail.request", lambda *a, **k: httpx.Response(
        200, json={"emailAddress": mailbox}, request=httpx.Request("GET", "https://www.googleapis.com/")))


def test_personal_connection_infers_identity_and_stays_paused_until_consent(setup, monkeypatch):
    base, engine, factory, _ = setup
    host(base)
    state = begin(base, factory)
    provider(monkeypatch)
    finish(factory, "google", state, "b" * 40, "test-code", base)
    with factory() as session:
        status = readiness(session, base)
        assert status["personal"] and not status["active"]
        assert status["profile"]["support_email"] == "person@example.com"
        assert not status["checks"]["policy_acknowledged"]
        assert status["checks"]["google_verified"]
        assert not status["checks"]["gemini_verified"]
        fields = decode(session.get(Connector, "google"), base)
        assert fields["google_refresh_token"] == "personal-refresh"
    with TestClient(create_app(base, (engine, factory))) as client:
        headers = {"Authorization": "Bearer " + base.operator_token}
        result = client.get("/api/business/oauth", headers=headers)
        assert result.json()["google_ready"]
        assert "synthetic-host-secret" not in result.text
        assert "personal-refresh" not in client.get("/api/business", headers=headers).text
        assert client.post("/api/business/activate", headers=headers).status_code == 409


def test_personal_requires_host_client_and_does_not_create_fake_connection(setup):
    base, _, factory, _ = setup
    base.workspace = "personal_test"
    base.google_client_id = base.google_client_secret = ""
    with pytest.raises(ValueError, match="host"):
        begin(base, factory)
    with factory() as session:
        assert session.get(Connector, "google") is None
        assert profile(session) is None


def test_profile_changed_during_personal_signin_is_preserved(setup, monkeypatch):
    base, _, factory, _ = setup
    host(base)
    state = begin(base, factory)
    with factory() as session:
        session.add(BusinessConfig(key="profile", value=Profile(
            name="Changed company", support_email="support@example.com", escalation_email="human@example.com").model_dump()))
        session.commit()
    provider(monkeypatch)
    with pytest.raises(ValueError, match="Profile changed"):
        finish(factory, "google", state, "b" * 40, "code", base)
    with factory() as session:
        assert profile(session)["name"] == "Changed company"
        assert "google_refresh_token" not in decode(session.get(Connector, "google"), base)


def test_personal_reconnect_cannot_change_mailbox_after_ingestion(setup, email, monkeypatch):
    base, _, factory, _ = setup
    host(base)
    provider(monkeypatch)
    finish(factory, "google", begin(base, factory), "b" * 40, "code", base)
    with factory() as session:
        ingest(session, email, base)
        session.flush()
        session.get(MessageOrigin, email.id).origin = "google:person@example.com"
        session.commit()
    state = begin(base, factory)
    provider(monkeypatch, "different@example.com")
    with pytest.raises(ValueError, match="separate installation"):
        finish(factory, "google", state, "b" * 40, "code", base)
    with factory() as session:
        assert profile(session)["support_email"] == "person@example.com"
        assert decode(session.get(Connector, "google"), base)["mailbox"] == "person@example.com"


def test_personal_can_replace_unactivated_profile_but_not_live_business(setup, email, monkeypatch):
    base, _, factory, _ = setup
    host(base)
    with factory() as session:
        session.add(BusinessConfig(key="profile", value=Profile(
            name="Unfinished setup", support_email="old@example.com", escalation_email="old@example.com").model_dump()))
        session.commit()
    provider(monkeypatch)
    finish(factory, "google", begin(base, factory), "b" * 40, "code", base)
    with factory() as session:
        assert profile(session)["name"] == "Personal inbox"
        session.delete(session.get(BusinessConfig, "personal"))
        ingest(session, email, base)
        session.flush()
        session.get(MessageOrigin, email.id).origin = "google:person@example.com"
        session.commit()
    with pytest.raises(ValueError, match="business setup"):
        begin(base, factory)


def test_personal_folder_picker_requires_auth_and_verified_google(setup, monkeypatch):
    base, engine, factory, _ = setup
    host(base)
    with TestClient(create_app(base, (engine, factory))) as client:
        assert client.get("/api/personal/drive-folders").status_code == 401
        client.headers["Authorization"] = "Bearer " + base.operator_token
        assert client.get("/api/personal/drive-folders").status_code == 409
        provider(monkeypatch)
        finish(factory, "google", begin(base, factory), "b" * 40, "code", base)
        calls = []

        def folders(self, method, path, **kwargs):
            calls.append((method, path, kwargs))
            return httpx.Response(200, json={"files": [{"id": "approved", "name": "My knowledge"}]})

        monkeypatch.setattr("app.google.GoogleClient.request", folders)
        result = client.get("/api/personal/drive-folders")
        assert result.json() == {"folders": [{"id": "approved", "name": "My knowledge"}], "has_more": False}
        assert calls[0][0] == "GET"
        assert "mimeType" in calls[0][2]["params"]["q"]


@pytest.mark.parametrize("provider_name", ["salesforce", "netsuite"])
def test_optional_crm_can_start_from_host_configuration_without_exposing_secret(setup, provider_name):
    base, engine, factory, _ = setup
    base.public_app_url = "https://support.example.com"
    setattr(base, provider_name + "_client_id", "host-client")
    setattr(base, provider_name + "_client_secret", "private-host-secret")
    if provider_name == "netsuite":
        base.netsuite_account_id = "123456_SB1"
    with TestClient(create_app(base, (engine, factory))) as client:
        client.headers["Authorization"] = "Bearer " + base.operator_token
        status = client.get("/api/business/oauth")
        assert status.json()["provider_ready"][provider_name]
        assert "private-host-secret" not in status.text
        started = client.post(f"/api/business/oauth/{provider_name}/start", json={"binding": "b" * 40})
        assert started.status_code == 200
        assert "private-host-secret" not in started.text
        assert "code_challenge" in started.json()["authorization_url"]
    with factory() as session:
        assert profile(session) is None
        assert decode(session.get(Connector, provider_name), base)[provider_name + "_client_secret"] == "private-host-secret"
