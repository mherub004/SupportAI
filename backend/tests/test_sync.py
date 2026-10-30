import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import Document, Job, Message, State
from app.google import Gmail
from app.main import create_app
from app.service import Workflow, upsert_document


def test_history_reconciliation_replays_idempotently(setup, email):
    config, _, factory, _ = setup

    class FakeGmail(Gmail):
        cursors = []

        def verify_mailbox(self):
            return {"historyId": "200"}

        def changes(self, cursor):
            self.cursors.append(cursor)
            return [{"messagesAdded": [{"message": {"id": email.id}}]}] if cursor else None

        def recent_ids(self):
            return [email.id]

        def fetch(self, message_id):
            return email

    gmail = FakeGmail(config)
    workflow = Workflow(config, factory, mail=gmail)
    workflow.sync_gmail()
    workflow.sync_gmail()
    assert gmail.cursors == ["", "200"]
    with factory() as session:
        assert session.get(State, "gmail_history").value == "200"
        assert session.scalar(select(func.count()).select_from(Message)) == 1
        assert session.scalar(select(func.count()).select_from(Job)) == 1


def test_expired_history_cursor_reconciles_recent_inbox(setup, email):
    config, _, factory, _ = setup

    class FakeGmail(Gmail):
        def verify_mailbox(self):
            return {"historyId": "500"}

        def changes(self, cursor):
            req = httpx.Request("GET", "https://www.googleapis.com/gmail/v1/users/me/history")
            raise httpx.HTTPStatusError("expired", request=req, response=httpx.Response(404, request=req))

        def recent_ids(self):
            return [email.id]

        def fetch(self, message_id):
            return email

    Workflow(config, factory, mail=FakeGmail(config)).sync_gmail()
    with factory() as session:
        assert session.get(Message, email.id)
        assert session.get(State, "gmail_history").value == "500"


def test_failed_drive_refresh_marks_knowledge_uncertain(setup, monkeypatch):
    _, _, factory, workflow = setup

    def fail(self):
        raise TimeoutError()

    monkeypatch.setattr("app.service.Drive.documents", fail)
    with pytest.raises(TimeoutError):
        workflow.sync_drive()
    with factory() as session:
        assert session.get(State, "knowledge_sync").value == "uncertain"


def test_drive_refresh_atomically_retires_missing_files(setup, document, monkeypatch):
    _, _, factory, workflow = setup
    document.id = "drive:old"
    with factory() as session:
        upsert_document(session, document)
        session.commit()
    replacement = document.model_copy(update={"id": "drive:new", "revision": "2"})
    monkeypatch.setattr("app.service.Drive.documents", lambda self: [replacement])
    workflow.sync_drive()
    with factory() as session:
        assert not session.get(Document, "drive:old").approved
        assert session.get(Document, "drive:new").approved
        assert session.get(State, "knowledge_sync").value == "current"


def test_authenticated_pubsub_is_deduplicated(setup, monkeypatch):
    config, engine, factory, workflow = setup
    config.connector_mode = "google"
    config.google_pubsub_audience = "https://service.example.invalid/webhooks/gmail"
    config.google_pubsub_service_account = "push@example.invalid"
    monkeypatch.setattr("google.oauth2.id_token.verify_oauth2_token", lambda *a, **k: {
        "email": "push@example.invalid", "email_verified": True
    })
    notification = {"emailAddress": config.mailbox, "historyId": "123"}
    body = {"message": {"data": base64.b64encode(json.dumps(notification).encode()).decode()}}
    with TestClient(create_app(config, (engine, factory), workflow)) as client:
        assert client.post("/webhooks/gmail", json=body).status_code == 401
        for _ in range(2):
            assert client.post("/webhooks/gmail", headers={"Authorization": "Bearer test-jwt"}, json=body).status_code == 202
        notification["emailAddress"] = "wrong@example.invalid"
        body["message"]["data"] = base64.b64encode(json.dumps(notification).encode()).decode()
        assert client.post("/webhooks/gmail", headers={"Authorization": "Bearer test-jwt"}, json=body).status_code == 400
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1
