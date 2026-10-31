import pytest
import base64
from email import policy
from email.parser import BytesParser
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.business import Profile, save_connector
from app.db import BusinessConfig, Conversation, HumanHandoff, Job, Message, MessageOrigin, now
from app.google import DemoMail
from app.handoffs import AlertDeferred, notify, rfc_id
from app.main import create_app
from app.providers import DemoModel
from app.schemas import Proposal
from app.service import Conflict, Workflow, ingest
from app.worker import run_one


def prepare(setup, email):
    base, engine, factory, _ = setup
    with factory() as session:
        session.add(BusinessConfig(key="profile", value=Profile(name="Acme Services", support_email="support@example.com",
            escalation_email="human@example.com", acknowledgement=True).model_dump()))
        save_connector(session, "google", {"mailbox": "support@example.com", "gmail_access_token": "synthetic"}, base)
        session.get(BusinessConfig, "activation").value = {"active": True}
        session.commit()
    config = base.model_copy(update={"configured_business": True, "business_active": True,
        "connector_mode": "google", "mailbox": "support@example.com", "escalation_email": "human@example.com",
        "business_name": "Acme Services"})
    workflow = Workflow(config, factory, mail=DemoMail(), model=DemoModel())
    email.body = "Please let me speak to a human agent."
    with factory() as session:
        ingest(session, email, config)
        session.commit()
    workflow.process(email.id)
    return config, engine, factory, workflow


class Alert:
    calls = 0
    fail = False
    recipient = ""
    body = ""

    def alert(self, recipient, body, identifier):
        self.calls += 1
        self.recipient, self.body = recipient, body
        assert identifier.startswith("<supportflow-human-")
        if self.fail:
            raise TimeoutError()
        return "confirmed-alert"


def test_handoff_pauses_ai_and_notifies_once_per_active_thread(setup, email):
    config, _, factory, workflow = prepare(setup, email)
    alert = Alert()
    notify(factory, config, email.id, alert)
    notify(factory, config, email.id, alert)
    with factory() as session:
        assert session.get(Conversation, email.thread_id).paused
        assert session.get(Message, email.id).status == "review"
        assert session.get(HumanHandoff, email.id).status == "sent"
        second = email.model_copy(update={"id": "follow-up"})
        ingest(session, second, config)
        session.commit()
    workflow.process(second.id)
    with factory() as session:
        assert len(list(session.scalars(select(HumanHandoff)))) == 1
        assert not session.get(Job, "human_alert:" + second.id)
    assert alert.calls == 1 and alert.recipient == "human@example.com"
    assert "human_requested" in alert.body and email.body not in alert.body
    assert rfc_id(email.id) != workflow.rfc_id(email.id)


def test_uncertain_alert_is_not_repeated_and_can_be_confirmed(setup, email, monkeypatch):
    config, engine, factory, _ = prepare(setup, email)
    alert = Alert()
    alert.fail = True
    with pytest.raises(TimeoutError):
        notify(factory, config, email.id, alert)
    notify(factory, config, email.id, alert)
    with TestClient(create_app(config, (engine, factory))) as client:
        client.headers["Authorization"] = "Bearer " + config.operator_token
        assert client.post(f"/api/handoffs/{email.id}/retry").status_code == 409
        monkeypatch.setattr("app.handoffs.Gmail.verify_mailbox", lambda self: {})
        monkeypatch.setattr("app.handoffs.Gmail.find_sent", lambda self, identifier: "confirmed-alert")
        result = client.post(f"/api/handoffs/{email.id}/reconcile")
        assert result.json()["email_resend"] is False
    assert alert.calls == 1
    with factory() as session:
        assert session.get(HumanHandoff, email.id).status == "sent"


def test_resuming_thread_resolves_handoff_and_allows_a_new_later_handoff(setup, email):
    config, engine, factory, workflow = prepare(setup, email)
    with TestClient(create_app(config, (engine, factory))) as client:
        client.headers["Authorization"] = "Bearer " + config.operator_token
        response = client.put(f"/api/threads/{email.thread_id}/ownership", json={"paused": False, "owner": "assistant"})
        assert response.status_code == 200
    with factory() as session:
        assert not session.get(HumanHandoff, email.id).active
        followup = email.model_copy(update={"id": "later-human-request"})
        ingest(session, followup, config)
        session.commit()
    workflow.process(followup.id)
    with factory() as session:
        assert session.get(HumanHandoff, followup.id).active
        assert len(list(session.scalars(select(HumanHandoff)))) == 2


def test_wrong_mailbox_or_changed_recipient_never_sends_alert(setup, email):
    config, _, factory, _ = prepare(setup, email)
    with factory() as session:
        session.get(MessageOrigin, email.id).origin = "google:other@example.com"
        session.commit()
    alert = Alert()
    with pytest.raises(Conflict, match="live mailbox"):
        notify(factory, config, email.id, alert)
    assert alert.calls == 0


def test_alert_quota_defers_without_consuming_retry_budget(setup, email):
    config, _, factory, workflow = prepare(setup, email)
    config.human_alert_hourly_limit = 1
    notify(factory, config, email.id, Alert())
    followup = email.model_copy(update={"id": "different-thread", "thread_id": "different-thread"})
    with factory() as session:
        ingest(session, followup, config)
        session.commit()
    workflow.process(followup.id)
    with pytest.raises(AlertDeferred):
        notify(factory, config, followup.id, Alert())
    assert run_one(factory, workflow, crm_only=True)
    assert run_one(factory, workflow, crm_only=True)
    with factory() as session:
        job = session.get(Job, "human_alert:" + followup.id)
        assert job.status == "pending" and job.attempts == 0 and job.available_at > now()


def test_business_clarification_uses_business_neutral_language(setup, email):
    config, _, factory, workflow = prepare(setup, email)
    second = email.model_copy(update={"id": "generic-question", "thread_id": "generic-thread", "body": "Can you help with my service account?", "subject": "Account help"})
    with factory() as session:
        ingest(session, second, config)
        session.commit()
    class Model:
        version = "controlled"
        def propose(self, email, docs):
            return Proposal(category="clarification", response="Missing details", uncertain=True)
    workflow.model = Model()
    workflow.process(second.id)
    with factory() as session:
        message = session.get(Message, second.id)
        assert "model" not in message.response and "error code" not in message.response
        assert "request" in message.response
        assert session.get(HumanHandoff, second.id).active


def test_handoff_endpoints_require_operator_auth(setup):
    base, engine, factory, _ = setup
    with TestClient(create_app(base, (engine, factory))) as client:
        assert client.get("/api/handoffs").status_code == 401
        assert client.post("/api/handoffs/any/retry").status_code == 401


def test_pending_alert_can_be_retargeted_only_through_verified_retry(setup, email):
    config, engine, factory, _ = prepare(setup, email)
    with factory() as session:
        row = session.get(BusinessConfig, "profile")
        row.value = {**row.value, "escalation_email": "new-agent@example.com"}
        session.commit()
    alert = Alert()
    with pytest.raises(Conflict, match="recipient changed"):
        notify(factory, config, email.id, alert)
    with TestClient(create_app(config, (engine, factory))) as client:
        client.headers["Authorization"] = "Bearer " + config.operator_token
        assert client.post(f"/api/handoffs/{email.id}/retry").status_code == 200
    notify(factory, config, email.id, alert)
    assert alert.recipient == "new-agent@example.com" and alert.calls == 1


def test_gmail_human_alert_is_internal_separate_and_loop_excluded(setup, monkeypatch):
    from app.google import Gmail
    from app.policy import excluded
    from app.schemas import EmailInput
    base, _, _, _ = setup
    base.mailbox = "support@example.com"
    client = Gmail(base)
    monkeypatch.setattr(client, "verify_mailbox", lambda: {})
    requests = []
    def request(method, path, **kwargs):
        requests.append((method, path, kwargs))
        return httpx.Response(200, json={"id": "sent-alert"})
    monkeypatch.setattr(client, "request", request)
    assert client.alert("human@example.com", "A human requested support", rfc_id("source")) == "sent-alert"
    raw = requests[0][2]["json"]["raw"]
    parsed = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw))
    assert parsed["To"] == "human@example.com" and parsed["From"] == base.mailbox
    assert parsed["Auto-Submitted"] == "auto-generated" and parsed["X-SupportFlow"] == "1"
    assert not parsed["In-Reply-To"] and not parsed["References"]
    assert "threadId" not in requests[0][2]["json"]
    alert = EmailInput(id="alert", thread_id="alert-thread", sender=base.mailbox, subject=parsed["Subject"], body="notice", headers={"auto-submitted": parsed["Auto-Submitted"]})
    assert excluded(alert, base.mailbox)
