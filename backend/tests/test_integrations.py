from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.business import decode, digest, save_connector
from app.crm import NetSuite, Salesforce, client_for, netsuite_account, salesforce_origin
from app.db import Connector, Document, OAuthAttempt, now
from app.drive_setup import folder_id
from app.google import Drive
from app.main import create_app
from app.oauth import finish, start
from app.policy import validate_grounding
from app.schemas import KnowledgeInput, Proposal
from app.service import retrieve, upsert_document


def response(data, status=200):
    return httpx.Response(status, json=data, request=httpx.Request("GET", "https://provider.example.invalid"))


@pytest.fixture
def api(setup):
    base, engine, factory, _ = setup
    base.public_app_url = "http://localhost:13000"
    with TestClient(create_app(base, (engine, factory))) as client:
        client.headers["Authorization"] = "Bearer " + base.operator_token
        yield client


def save(setup, provider, fields, verified=False):
    base, _, factory, _ = setup
    with factory() as session:
        save_connector(session, provider, fields, base)
        session.flush()
        if verified:
            record = session.get(Connector, provider)
            record.verified_at, record.verified_digest = now(), digest(decode(record, base))
        session.commit()


def google_setup(setup):
    save(setup, "google", {"mailbox": "support@example.com", "google_client_id": "test-client",
                           "google_client_secret": "test-secret", "drive_folder_id": "approved-folder"}, True)


def test_oauth_pkce_binding_expiry_and_one_time_consumption(setup, monkeypatch):
    base, _, factory, _ = setup
    base.public_app_url = "https://support.example.com"
    google_setup(setup)
    with factory() as session:
        result = start(session, "google", "b"*40, base)
    params = parse_qs(urlsplit(result["authorization_url"]).query)
    state = params["state"][0]
    assert params["code_challenge_method"] == ["S256"]
    assert params["access_type"] == ["offline"]
    assert params["redirect_uri"] == ["https://support.example.com/api/oauth/callback/google"]
    with factory() as session:
        stored = session.scalar(select(OAuthAttempt))
        assert state not in stored.encrypted_payload
    with pytest.raises(ValueError):
        finish(factory, "google", state, "wrong-browser-binding"*2, "code", base)
    calls = []

    def exchange(url, **kwargs):
        calls.append(kwargs)
        return response({"access_token": "new-access", "refresh_token": "new-offline-token"})

    monkeypatch.setattr("app.oauth.httpx.post", exchange)
    monkeypatch.setattr("app.google.Gmail.verify_mailbox", lambda self: {"emailAddress": self.config.mailbox})
    finish(factory, "google", state, "b"*40, "code", base)
    assert calls[0]["data"]["code_verifier"]
    with factory() as session:
        record = session.get(Connector, "google")
        assert decode(record, base)["google_refresh_token"] == "new-offline-token"
        assert "new-offline-token" not in record.encrypted_config
    with pytest.raises(ValueError):
        finish(factory, "google", state, "b"*40, "code", base)
    assert len(calls) == 1


def test_oauth_expired_or_changed_configuration_is_rejected(setup):
    base, _, factory, _ = setup
    base.public_app_url = "https://support.example.com"
    google_setup(setup)
    with factory() as session:
        result = start(session, "google", "b"*40, base)
        session.scalar(select(OAuthAttempt)).expires_at = now() - timedelta(seconds=1)
        session.commit()
    state = parse_qs(urlsplit(result["authorization_url"]).query)["state"][0]
    with pytest.raises(ValueError):
        finish(factory, "google", state, "b"*40, "code", base)


def test_oauth_api_never_echoes_provider_errors(api, setup, monkeypatch):
    google_setup(setup)
    result = api.post("/api/business/oauth/google/start", json={"binding": "b"*40})
    assert result.status_code == 200
    state = parse_qs(urlsplit(result.json()["authorization_url"]).query)["state"][0]

    def fail(*args, **kwargs):
        raise ValueError("sensitive-provider-body-and-token")

    monkeypatch.setattr("app.oauth.httpx.post", fail)
    result = api.post("/api/business/oauth/google/complete", json={"binding": "b"*40, "state": state, "code": "secret-auth-code"})
    assert result.status_code == 422
    assert "secret-auth-code" not in result.text
    assert "sensitive-provider" not in result.text
    assert "secret-auth-code" not in api.get("/api/audit").text


@pytest.mark.parametrize("origin", ["http://company.salesforce.com", "https://company.salesforce.com.evil.example",
                                     "https://user:secret@company.salesforce.com", "https://company.salesforce.com/query",
                                     "https://127.0.0.1", "https://company.salesforce.com:444"])
def test_salesforce_rejects_credential_forwarding_to_untrusted_origins(origin):
    with pytest.raises(ValueError):
        salesforce_origin(origin)


def test_netsuite_accounts_and_google_folder_links():
    assert netsuite_account("1234567_SB1") == "1234567-sb1"
    with pytest.raises(ValueError):
        netsuite_account("evil.example/path")
    assert folder_id("https://drive.google.com/drive/u/0/folders/approved_123?usp=sharing") == "approved_123"
    with pytest.raises(ValueError):
        folder_id("https://notebooklm.google.com/notebook/id")
    with pytest.raises(ValueError):
        folder_id("https://drive.google.com.evil.example/drive/folders/id")


def test_salesforce_fixed_read_only_customer_query_and_ambiguity(monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/services/data/"):
            return response([{"version": "60.0"}, {"version": "61.0"}])
        return response({"records": [{"Id": "one"}, {"Id": "two"}]})

    monkeypatch.setattr("app.crm.httpx.get", get)
    client = Salesforce({"salesforce_instance_url": "https://company.my.salesforce.com", "salesforce_access_token": "secret"})
    result = client.lookup("o'hara@example.com")
    assert result["status"] == "ambiguous" and result["records"] == []
    query = calls[-1][1]["params"]["q"]
    assert "o\\'hara@example.com" in query and query.endswith("LIMIT 2")
    assert "/v61.0/query" in calls[-1][0]


def test_netsuite_only_uses_suiteql_select_and_exact_email(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return response({"items": [{"id": "42", "entityid": "Acme", "companyname": "Acme Services"}]})

    monkeypatch.setattr("app.crm.httpx.post", post)
    result = NetSuite({"netsuite_account_id": "123_SB1", "netsuite_access_token": "secret"}).lookup("o'hara@example.com")
    assert result["status"] == "matched"
    assert "o''hara@example.com" in calls[0][1]["json"]["q"]
    assert calls[0][1]["json"]["q"].startswith("SELECT ")
    assert "services/rest/query/v1/suiteql" in calls[0][0]
    assert result["records"][0]["record_id"] == "42"


def test_rotating_refresh_token_is_persisted_before_record_request(setup, monkeypatch):
    base, _, factory, _ = setup
    save(setup, "netsuite", {"netsuite_account_id": "123_SB1", "netsuite_client_id": "client",
                             "netsuite_client_secret": "client-secret", "netsuite_refresh_token": "old-refresh"})
    monkeypatch.setattr("app.crm.httpx.post", lambda *a, **k: response({"access_token": "new-access", "refresh_token": "rotated-refresh", "expires_in": 3600}))
    with factory() as session:
        client_for(session, "netsuite", base)
    with factory() as session:
        record = session.get(Connector, "netsuite")
        assert decode(record, base)["netsuite_refresh_token"] == "rotated-refresh"
        assert "rotated-refresh" not in record.encrypted_config


def fake_file(revision="1"):
    return {"id": "file-one", "name": "Approved FAQ", "mimeType": "text/plain", "version": revision,
            "modifiedTime": "2026-10-30T00:00:00Z", "webViewLink": "https://drive.google.com/file/d/file-one/view"}


def test_drive_browse_preview_approve_and_revoke_after_revision_change(api, setup, monkeypatch):
    google_setup(setup)
    version = ["1"]
    monkeypatch.setattr(Drive, "inventory", lambda self: [fake_file(version[0])])
    monkeypatch.setattr(Drive, "export", lambda self, file: "This is the reviewed business FAQ. Use the customer support portal.")
    assert api.get("/api/business/drive/files").json()[0]["approved"] is False
    preview = api.get("/api/business/drive/files/file-one").json()
    data = {"revision": preview["revision"], "modified_time": preview["modified_time"], "brand": "Acme", "owner": "Reviewer", "approved": True}
    assert api.post("/api/business/drive/files/file-one/approve", json=data).status_code == 200
    assert api.get("/api/business/drive/files").json()[0]["approved"]
    _, _, factory, _ = setup
    with factory() as session:
        assert session.get(Document, "drive:file-one").approved
    version[0] = "2"
    assert not api.get("/api/business/drive/files").json()[0]["approved"]
    with factory() as session:
        assert not session.get(Document, "drive:file-one").approved
    assert api.post("/api/business/drive/files/file-one/approve", json=data).status_code == 409
    assert api.get("/api/business/drive/files/outside-folder").status_code == 409


def test_drive_sync_requires_reapproval_for_ui_managed_sources(setup, monkeypatch):
    base = setup[0]
    approvals = {"file-one": {"approved": True, "revision": "1", "modified_time": fake_file()["modifiedTime"],
                              "metadata": {"brand": "Acme", "model": "general", "owner": "Reviewer", "language": "en", "effective_at": now().isoformat()}}}
    drive = Drive(base, approvals)
    monkeypatch.setattr(drive, "inventory", lambda: [fake_file("2")])
    assert drive.documents() == []


def test_long_knowledge_uses_bounded_exact_source_excerpts(setup, document, email):
    _, _, factory, _ = setup
    document.content = "A" * 80000 + "\n\n" + "DEMO-1 manual matching source content and instructions." * 20
    with factory() as session:
        upsert_document(session, document)
        session.commit()
        candidate = SimpleNamespace(subject=email.subject, body=email.body, language="en", brand="ABL", model="unknown")
        evidence = retrieve(session, candidate)
        assert len(evidence) == 1
        assert len(evidence[0].content) <= 16100
        quote = "DEMO-1 manual matching source content and instructions."
        proposal = Proposal(category="manual_link", response="Reviewed", citations=[{"document_id": document.id, "revision": "1", "quote": quote}])
        assert validate_grounding(proposal, evidence)


def test_crm_lookup_does_not_accept_arbitrary_addresses_or_demo_messages(api, setup, email):
    from app.service import ingest
    base, _, factory, _ = setup
    with factory() as session:
        ingest(session, email, base)
        session.commit()
    assert api.post(f"/api/messages/{email.id}/crm-context", json={"email": "other@example.com"}).status_code == 409


def test_oauth_client_change_clears_stale_tokens(setup):
    base, _, factory, _ = setup
    save(setup, "salesforce", {"salesforce_client_id": "old-client", "salesforce_client_secret": "secret",
                               "salesforce_refresh_token": "old-refresh", "salesforce_access_token": "old-access"})
    save(setup, "salesforce", {"salesforce_client_id": "new-client"})
    with factory() as session:
        fields = decode(session.get(Connector, "salesforce"), base)
        assert "salesforce_refresh_token" not in fields
        assert "salesforce_access_token" not in fields


def test_crm_lookup_is_internal_only_and_has_no_automatic_reply_mutation(api, setup, monkeypatch):
    from app.business import BusinessConfig
    from app.db import MessageOrigin
    from app.service import ingest
    from app.schemas import EmailInput
    base, _, factory, _ = setup
    profile = {"name": "Acme", "industry": "Support", "website": "", "support_email": "support@acme.example",
               "escalation_email": "human@acme.example", "languages": ["en"], "tone": "professional",
               "escalation_keywords": [], "acknowledgement": True}
    save(setup, "salesforce", {"salesforce_client_id": "client", "salesforce_client_secret": "secret"}, True)
    with factory() as session:
        session.add(BusinessConfig(key="profile", value=profile))
        email = EmailInput(id="real-gmail", thread_id="real-thread", sender="customer@acme.example",
                           subject="Help", body="A question")
        ingest(session, email, base)
        session.flush()
        session.get(MessageOrigin, email.id).origin = "google:"+profile["support_email"]
        session.commit()
    class Client:
        def verify(self): return "org"
        def lookup(self, email):
            assert email == "customer@acme.example"
            return {"status": "matched", "records": [{"record_id": "record-1", "display_name": "Customer", "organization": "Acme"}]}
    monkeypatch.setattr("app.crm_routes.client_for", lambda *a: Client())
    result = api.post("/api/messages/real-gmail/crm-context", json={}).json()
    assert result["usage"] == "internal_review_only"
    assert result["providers"]["salesforce"]["records"][0]["record_id"] == "record-1"
    assert result["providers"]["netsuite"]["status"] == "not_connected"
    assert api.get("/api/messages/real-gmail").json()["response"] == ""


def test_netsuite_oauth_uses_account_domain_and_basic_client_auth(setup, monkeypatch):
    base, _, factory, _ = setup
    base.public_app_url = "https://support.example.com"
    save(setup, "netsuite", {"netsuite_account_id": "123456_SB1", "netsuite_client_id": "client-id", "netsuite_client_secret": "client-secret"})
    with factory() as session:
        result = start(session, "netsuite", "b"*40, base)
    parsed = urlsplit(result["authorization_url"])
    assert parsed.hostname == "123456-sb1.app.netsuite.com"
    state = parse_qs(parsed.query)["state"][0]
    calls = []
    def exchange(url, **kwargs):
        calls.append((url, kwargs))
        return response({"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600})
    monkeypatch.setattr("app.oauth.httpx.post", exchange)
    finish(factory, "netsuite", state, "b"*40, "code", base)
    assert calls[0][0].startswith("https://123456-sb1.suitetalk.api.netsuite.com/")
    assert calls[0][1]["auth"] == ("client-id", "client-secret")
    assert "client_secret" not in calls[0][1]["data"]
    assert calls[0][1]["data"]["code_verifier"]


def test_noncontiguous_evidence_cannot_fabricate_a_verbatim_quote(document):
    from app.db import Document
    data = document.model_dump()
    data["checksum"] = "test"
    doc = Document(**data)
    # Populate defaults that normally come from the database.
    doc.approved = True
    evidence = SimpleNamespace(**{column.name: getattr(doc, column.name) for column in Document.__table__.columns})
    evidence.content = "First selected section.\n\nA later selected section."
    evidence.full_content = "First selected section. OTHER TEXT A later selected section."
    proposal = Proposal(category="setup_faq", response="Draft", citations=[{
        "document_id": document.id, "revision": document.revision,
        "quote": "First selected section.\n\nA later selected section.",
    }])
    assert not validate_grounding(proposal, [evidence])


def test_uncertain_knowledge_sync_blocks_substantive_drafting(setup, document, email):
    from app.db import Message, State
    from app.service import ingest
    base, _, factory, workflow = setup
    with factory() as session:
        upsert_document(session, document)
        ingest(session, email, base)
        session.get(State, "knowledge_sync").value = "uncertain"
        session.commit()
    workflow.process(email.id)
    with factory() as session:
        result = session.get(Message, email.id)
        assert "knowledge_sync_uncertain" in result.risk_tags
        assert result.citations == []
        assert result.disposition == "review"


def test_crm_verification_cannot_overwrite_new_app_credentials(api, setup, monkeypatch):
    base, _, factory, _ = setup
    save(setup, "salesforce", {"salesforce_client_id": "client", "salesforce_client_secret": "original-secret"})
    def fake_client(session, key, config):
        original = decode(session.get(Connector, key), config)
        class Client:
            fields = original
            def verify(self):
                save(setup, "salesforce", {"salesforce_client_secret": "new-administrator-secret"})
                return "organization-id"
        return Client()
    monkeypatch.setattr("app.crm.client_for", fake_client)
    assert api.post("/api/business/connectors/salesforce/verify").status_code == 422
    with factory() as session:
        assert decode(session.get(Connector, "salesforce"), base)["salesforce_client_secret"] == "new-administrator-secret"


def test_folder_changes_immediately_disable_old_drive_knowledge(setup):
    google_setup(setup)
    base, _, factory, _ = setup
    with factory() as session:
        upsert_document(session, KnowledgeInput(id="drive:old-folder-file", title="Old FAQ", revision="1", brand="Acme",
                           model="general", language="en", owner="Reviewer", approved=True, effective_at=now(),
                           content="An approved source in the previously configured folder.", url="https://drive.google.com/file/d/old/view"))
        session.commit()
    save(setup, "google", {"drive_folder_id": "new-folder"})
    with factory() as session:
        assert not session.get(Document, "drive:old-folder-file").approved


def test_salesforce_oauth_requests_identity_scope_for_userinfo(setup):
    base, _, factory, _ = setup
    base.public_app_url = "https://support.example.com"
    save(setup, "salesforce", {"salesforce_client_id": "client", "salesforce_client_secret": "secret"})
    with factory() as session:
        result = start(session, "salesforce", "b"*40, base)
    assert "openid" in parse_qs(urlsplit(result["authorization_url"]).query)["scope"][0].split()


def test_sync_cannot_reapprove_a_source_retired_while_exporting(setup, document, monkeypatch):
    base, _, factory, workflow = setup
    from app.db import DriveApproval
    document.id = "drive:file-one"
    with factory() as session:
        upsert_document(session, document)
        session.add(DriveApproval(file_id="file-one", revision="1", modified_time="now", approved=True, source_metadata={}))
        session.commit()
    def stale_inventory(self):
        with factory() as session:
            session.get(DriveApproval, "file-one").approved = False
            session.get(Document, document.id).approved = False
            session.commit()
        return [document]
    monkeypatch.setattr(Drive, "documents", stale_inventory)
    workflow.sync_drive()
    with factory() as session:
        assert not session.get(Document, document.id).approved
