"""Run INSIDE the demo API container: python - < scripts/check_postgres.py.

Uses isolated synthetic IDs and restores the kill switch after the check.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from app.config import settings
from app.db import Audit, Conversation, Job, Message, Send, State, database
from app.google import DemoMail
from app.schemas import EmailInput
from app.service import Conflict, Workflow, ingest
from sqlalchemy import delete

config = settings()
assert config.connector_mode == "demo", "Concurrency checks require synthetic demo mode"
assert config.database_url.startswith("postgresql"), "PostgreSQL required"
_, factory = database(config.database_url)
key = "postgres-concurrency-check"
email = EmailInput(id=key, thread_id=key, sender="test-lock@example.invalid",
                   subject="ABL DEMO-1 manual", body="Please send the manual for ABL DEMO-1.",
                   headers={"message-id": "<concurrency@example.invalid>"})
with factory() as session:
    assert session.get(Message, key) is None, "Prior check state remains; inspect it before rerunning"
    previous_switch = session.get(State, "kill_switch").value


class CountingMail(DemoMail):
    sends = 0
    lock = Lock()

    def send(self, draft_id):
        with self.lock:
            self.sends += 1
        return "synthetic-concurrency-sent"


mail = CountingMail()
workflow = Workflow(config, factory, mail=mail)


def incoming(_):
    with factory() as session:
        created = ingest(session, email, config)
        session.commit()
        return created


def send(_):
    try:
        workflow.deliver(key)
        return "sent"
    except Conflict:
        return "blocked"


try:
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(incoming, range(8)))
    assert sum(results) == 1, results
    workflow.process(key)
    with factory() as session:
        response = session.get(Message, key).response
        session.get(State, "kill_switch").value = "off"
        session.commit()
    workflow.approve(key, response, "Synthetic PostgreSQL concurrency test")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(send, range(8)))
    assert results.count("sent") == 1, results
    assert mail.sends == 1
    with factory() as session:
        assert session.get(Send, key).state == "sent"
    print("PASS: PostgreSQL eight concurrent ingests produce one message/job; eight send attempts produce one adapter call")
finally:
    with factory() as session:
        session.get(State, "kill_switch").value = previous_switch
        session.execute(delete(Send).where(Send.message_id == key))
        session.execute(delete(Job).where(Job.id == "process:" + key))
        session.execute(delete(Audit).where(Audit.entity_id.in_([key, "process:" + key])))
        session.execute(delete(Message).where(Message.id == key))
        session.execute(delete(Conversation).where(Conversation.id == key))
        session.commit()
