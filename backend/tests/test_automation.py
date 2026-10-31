from datetime import timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.automation import Policy, queue_crm, sync
from app.business import Profile, decode, digest, runtime, save_connector
from app.crm import NetSuite, Salesforce
from app.db import BusinessConfig, Connector, CrmDelivery, Job, Message, Send, now
from app.google import DemoMail
from app.main import create_app
from app.schemas import Proposal
from app.service import Conflict, Workflow, ingest, upsert_document
from app.worker import run_one


class Mail(DemoMail):
    sends = 0

    def send(self, draft_id):
        self.sends += 1
        return "confirmed-gmail-id"


class Model:
    version = "controlled-faq"

    def propose(self, email, docs):
        d = docs[0]
        return Proposal(category="setup_faq", response=d.content, uncertain=False,
                        citations=[{"document_id": d.id, "revision": d.revision, "quote": d.content}])


def configured(setup, email, document, providers=()):
    base, engine, factory, _ = setup
    with factory() as session:
        session.add(BusinessConfig(key="profile", value=Profile(name="ABL", support_email="support@example.com",
                    escalation_email="human@example.com", acknowledgement=True).model_dump()))
        for provider, fields in {
            "google": {"mailbox": "support@example.com", "google_client_id": "client", "google_client_secret": "secret", "google_refresh_token": "refresh"},
            "gemini": {"gemini_api_key": "model-key"},
            "salesforce": {"salesforce_instance_url": "https://org.salesforce.com", "salesforce_access_token": "access"},
            "netsuite": {"netsuite_account_id": "12345", "netsuite_access_token": "access", "netsuite_case_reply_field": "custevent_supportflow_reply"},
        }.items():
            save_connector(session, provider, fields, base)
            session.flush()
            record = session.get(Connector, provider)
            record.verified_at, record.verified_digest = now(), digest(decode(record, base))
        session.get(BusinessConfig, "activation").value = {"active": True, "since": (now() - timedelta(hours=1)).isoformat()}
        session.add(BusinessConfig(key="automation", value=Policy(enabled=True, acknowledgement=True,
            allowed_senders=["customer@example.invalid"], crm_providers=list(providers)).model_dump()))
        from app.db import State
        session.get(State, "kill_switch").value = "off"
        upsert_document(session, document)
        session.commit()
    config = runtime(base, factory)
    email.headers["x-supportflow-internal-date"] = str(int((now() - timedelta(seconds=1)).replace(tzinfo=timezone.utc).timestamp()*1000))
    with factory() as session:
        ingest(session, email, config)
        session.commit()
    mail = Mail()
    return config, factory, Workflow(config, factory, mail=mail, model=Model()), mail


def send(setup, email, document, providers=()):
    result = configured(setup, email, document, providers)
    config, factory, workflow, mail = result
    assert run_one(factory, workflow)  # Process, prepare draft, persist separate send job.
    assert mail.sends == 0
    assert run_one(factory, workflow)  # Reserved, verified and confirmed send.
    assert mail.sends == 1
    return result


class CRM:
    origin = "https://org.salesforce.com"
    activities = 0
    cases = 0
    matches = "matched"
    fail_case = False

    def verify(self): pass
    def verify_writes(self): pass
    def lookup(self, email):
        return {"status": self.matches, "records": [{"record_id": "003000000000001"}]}
    def support_cases(self, customer): return ["500000000000001"]
    def validate_case(self, case, customer): assert case == "500000000000001"
    def log_activity(self, customer, case, marker, body):
        self.activities += 1
        assert "confirmed-gmail-id" in body and "Outcome: email sent" in body
        return "task-1"
    def log_case(self, case, marker, body):
        self.cases += 1
        if self.fail_case:
            raise TimeoutError("ambiguous write")
    def confirm_write(self, stage, customer, case, marker, external_id):
        return external_id == "verifiedrecord" and len(marker) == 32


def test_full_confirmed_send_updates_customer_and_case_once(setup, email, document, monkeypatch):
    config, factory, workflow, mail = send(setup, email, document, ["salesforce"])
    crm = CRM()
    monkeypatch.setattr("app.crm.client_for", lambda *a: crm)
    assert run_one(factory, workflow)
    sync(factory, config, email.id, "salesforce")
    with factory() as session:
        row = session.get(CrmDelivery, (email.id, "salesforce"))
        assert (row.status, row.activity_state, row.case_state) == ("done", "done", "done")
        queue_crm(session, email.id)
        session.commit()
        assert len(list(session.scalars(select(CrmDelivery)))) == 1
    assert crm.activities == crm.cases == mail.sends == 1


def test_uncertain_case_write_never_repeats_activity_or_email(setup, email, document, monkeypatch):
    config, factory, workflow, mail = send(setup, email, document, ["salesforce"])
    crm = CRM()
    crm.fail_case = True
    monkeypatch.setattr("app.crm.client_for", lambda *a: crm)
    assert run_one(factory, workflow)
    sync(factory, config, email.id, "salesforce")
    with factory() as session:
        row = session.get(CrmDelivery, (email.id, "salesforce"))
        assert row.status == "needs_review" and row.activity_state == "done" and row.case_state == "reserved"
        assert session.get(Send, email.id).state == "sent"
    assert mail.sends == crm.activities == crm.cases == 1
    base, engine, _, _ = setup
    with TestClient(create_app(base, (engine, factory))) as client:
        result = client.post(f"/api/automation/deliveries/{email.id}/salesforce/retry", headers={"Authorization": "Bearer " + base.operator_token})
        assert result.status_code == 409
        result = client.post(f"/api/automation/deliveries/{email.id}/salesforce/reconcile", headers={"Authorization": "Bearer " + base.operator_token}, json={"external_id": "incorrect"})
        assert result.status_code == 409
        result = client.post(f"/api/automation/deliveries/{email.id}/salesforce/reconcile", headers={"Authorization": "Bearer " + base.operator_token}, json={"external_id": "verifiedrecord"})
        assert result.status_code == 200
    assert crm.activities == crm.cases == mail.sends == 1


def test_read_failure_retries_crm_without_resending_email(setup, email, document, monkeypatch):
    config, factory, workflow, mail = send(setup, email, document, ["salesforce"])
    crm = CRM()
    monkeypatch.setattr("app.crm.client_for", lambda *a: (_ for _ in ()).throw(TimeoutError()))
    assert run_one(factory, workflow)
    with factory() as session:
        row = session.get(CrmDelivery, (email.id, "salesforce"))
        assert row.activity_state == row.case_state == "pending"
        job = session.get(Job, "crm:salesforce:" + email.id)
        job.available_at = now() - timedelta(seconds=1)
        session.commit()
    monkeypatch.setattr("app.crm.client_for", lambda *a: crm)
    assert run_one(factory, workflow)
    assert crm.activities == crm.cases == mail.sends == 1


def test_ambiguous_customer_does_not_write_any_crm_record(setup, email, document, monkeypatch):
    config, factory, _, mail = send(setup, email, document, ["salesforce"])
    crm = CRM()
    crm.matches = "ambiguous"
    monkeypatch.setattr("app.crm.client_for", lambda *a: crm)
    sync(factory, config, email.id, "salesforce")
    with factory() as session:
        assert session.get(CrmDelivery, (email.id, "salesforce")).error == "Customer_ambiguous"
    assert crm.activities == crm.cases == 0 and mail.sends == 1


@pytest.mark.parametrize("change", ["paused", "disabled", "old_mail", "wrong_sender"])
def test_live_policy_and_sender_guards_block_automatic_send(setup, email, document, change):
    config, factory, workflow, mail = configured(setup, email, document)
    workflow.process(email.id)
    with factory() as session:
        if change == "paused":
            session.get(BusinessConfig, "activation").value = {"active": False}
        if change == "disabled":
            session.get(BusinessConfig, "automation").value = Policy().model_dump()
        if change == "old_mail":
            session.get(Message, email.id).headers = {"x-supportflow-internal-date": "1"}
        if change == "wrong_sender":
            row = session.get(BusinessConfig, "automation")
            row.value = {**row.value, "allowed_senders": ["another@example.com"]}
        session.commit()
    with pytest.raises(Conflict):
        workflow.deliver(email.id, automatic=True)
    assert mail.sends == 0


def test_personal_auto_mode_requires_sender_and_explicit_acknowledgement(setup):
    base, engine, factory, _ = setup
    base.workspace = "personal_test"
    with TestClient(create_app(base, (engine, factory))) as client:
        client.headers["Authorization"] = "Bearer " + base.operator_token
        assert client.put("/api/automation", json={"enabled": True}).status_code == 409
        assert client.put("/api/automation", json={"enabled": True, "acknowledgement": True}).status_code == 409
        assert client.put("/api/automation", json={"enabled": True, "acknowledgement": True, "allowed_senders": ["test@example.com"]}).status_code == 200
        assert client.get("/api/automation").json()["enabled"]


def test_risk_email_never_auto_sends(setup, email, document):
    config, factory, workflow, mail = configured(setup, email, document)
    with factory() as session:
        session.get(Message, email.id).body = "The device is smoking and sparks are visible"
        session.commit()
    workflow.process(email.id)
    with factory() as session:
        assert session.get(Message, email.id).disposition == "escalate"
        assert session.get(Job, "auto_send:" + email.id) is None
    assert mail.sends == 0


def test_salesforce_writes_activity_and_private_case_comment(monkeypatch):
    posts = []
    sf = Salesforce({"salesforce_instance_url": "https://org.salesforce.com", "salesforce_access_token": "private"})
    sf._root = "/services/data/v65.0"
    monkeypatch.setattr("app.crm.httpx.post", lambda url, **kw: (posts.append((url, kw)) or httpx.Response(201, json={"id": "activity"}, request=httpx.Request("POST", url))))
    assert sf.log_activity("003000000000001", "500000000000001", "marker", "sent response") == "activity"
    sf.log_case("500000000000001", "marker", "sent response")
    assert posts[0][1]["json"]["WhoId"] == "003000000000001"
    assert posts[0][1]["json"]["WhatId"] == "500000000000001"
    assert posts[1][1]["json"] == {"ParentId": "500000000000001", "CommentBody": "sent response", "IsPublished": False}


def test_netsuite_schema_is_checked_and_no_second_email_is_requested(monkeypatch):
    calls = []
    ns = NetSuite({"netsuite_account_id": "12345", "netsuite_access_token": "private", "netsuite_case_reply_field": "custevent_supportflow_reply"})
    def request(method, url, **kw):
        calls.append((method, url, kw))
        data = {"properties": {k: {"type": "string"} for k in ["title", "company", "message", "custevent_supportflow_reply"]}}
        return httpx.Response(200, json=data, headers={"Location": "https://12345.suitetalk.api.netsuite.com/services/rest/record/v1/task/12"}, request=httpx.Request(method, url))
    monkeypatch.setattr("app.crm.httpx.request", request)
    ns.verify_writes()
    assert ns.log_activity("1", "2", "marker", "sent response") == "12"
    ns.log_case("2", "marker", "sent response")
    assert calls[0][2]["headers"]["Accept"] == "application/schema+json"
    assert calls[-1][0] == "PATCH" and calls[-1][2]["json"] == {"custevent_supportflow_reply": "sent response"}
    assert all("outgoingMessage" not in c[2].get("json", {}) for c in calls)


def test_both_crms_update_independently_after_one_email(setup, email, document, monkeypatch):
    config, factory, workflow, mail = send(setup, email, document, ["salesforce", "netsuite"])
    clients = {provider: CRM() for provider in ("salesforce", "netsuite")}
    clients["netsuite"].origin = "https://12345.suitetalk.api.netsuite.com"
    monkeypatch.setattr("app.crm.client_for", lambda session, provider, base: clients[provider])
    assert run_one(factory, workflow) and run_one(factory, workflow)
    with factory() as session:
        assert all(row.status == "done" for row in session.scalars(select(CrmDelivery)))
    assert all(client.activities == client.cases == 1 for client in clients.values())
    assert mail.sends == 1


def test_confirmed_email_is_required_before_any_crm_write(setup, email, document, monkeypatch):
    config, factory, workflow, mail = configured(setup, email, document, ["salesforce"])
    def fail(draft):
        mail.sends += 1
        raise TimeoutError()
    monkeypatch.setattr(mail, "send", fail)
    assert run_one(factory, workflow) and run_one(factory, workflow)
    with factory() as session:
        assert session.get(Send, email.id).state == "uncertain"
        assert not list(session.scalars(select(CrmDelivery)))
        job = session.get(Job, "auto_send:" + email.id)
        job.available_at = now() - timedelta(seconds=1)
        session.commit()
    assert run_one(factory, workflow)
    assert mail.sends == 1


def test_netsuite_missing_custom_field_stops_before_mutation(monkeypatch):
    ns = NetSuite({"netsuite_account_id": "12345", "netsuite_access_token": "private", "netsuite_case_reply_field": "custevent_missing"})
    calls = []
    def request(method, url, **kw):
        calls.append(method)
        return httpx.Response(200, json={"properties": {k: {} for k in ["title", "company", "message"]}}, request=httpx.Request(method, url))
    monkeypatch.setattr("app.crm.httpx.request", request)
    with pytest.raises(ValueError, match="absent"):
        ns.verify_writes()
    assert calls == ["GET", "GET"]


@pytest.mark.parametrize("outside", ["old", "sender"])
def test_old_or_out_of_scope_emails_create_no_draft_and_make_no_model_call(setup, email, document, monkeypatch, outside):
    config, factory, workflow, mail = configured(setup, email, document)
    with factory() as session:
        message = session.get(Message, email.id)
        if outside == "old":
            message.headers = {"x-supportflow-internal-date": "1"}
        else:
            message.sender = "different@example.com"
        session.commit()
    monkeypatch.setattr(workflow.model, "propose", lambda *a: pytest.fail("Excluded email reached the model"))
    workflow.process(email.id)
    with factory() as session:
        message = session.get(Message, email.id)
        assert message.status == "excluded" and not message.draft_id
        assert session.get(Job, "auto_send:" + email.id) is None
    assert mail.sends == 0


def test_verified_case_mapping_resolves_ambiguity_without_resending(setup, email, document, monkeypatch):
    config, factory, workflow, mail = send(setup, email, document, ["salesforce"])
    crm = CRM()
    monkeypatch.setattr(crm, "support_cases", lambda customer: ["500000000000001", "500000000000002"])
    monkeypatch.setattr("app.crm.client_for", lambda *a: crm)
    sync(factory, config, email.id, "salesforce")
    with factory() as session:
        assert session.get(CrmDelivery, (email.id, "salesforce")).error == "CaseMissingOrAmbiguous"
    base, engine, _, _ = setup
    with TestClient(create_app(base, (engine, factory))) as client:
        result = client.put(f"/api/automation/deliveries/{email.id}/salesforce/case", headers={"Authorization": "Bearer " + base.operator_token}, json={"case_id": "500000000000001"})
        assert result.status_code == 200
    assert run_one(factory, workflow)
    assert crm.activities == crm.cases == mail.sends == 1


def test_case_reference_is_customer_scoped_before_writes(setup, email, document, monkeypatch):
    email.subject = "Case #12345 ABL DEMO-1 manual"
    config, factory, _, mail = send(setup, email, document, ["salesforce"])
    crm = CRM()
    references = []
    monkeypatch.setattr(crm, "support_cases", lambda customer, reference: references.append((customer, reference)) or ["500000000000001"])
    monkeypatch.setattr("app.crm.client_for", lambda *a: crm)
    sync(factory, config, email.id, "salesforce")
    assert references == [("003000000000001", "12345")]
    assert crm.activities == crm.cases == mail.sends == 1
