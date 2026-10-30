from datetime import timedelta

import pytest

from app.config import Settings
from app.db import database, now
from app.schemas import EmailInput, KnowledgeInput
from app.service import Workflow, initialize, upsert_document


@pytest.fixture
def setup(tmp_path):
    config = Settings(operator_token="test-operator-token-32-characters-long",
                      database_url=f"sqlite:///{tmp_path / 'test.db'}")
    engine, factory = database(config.database_url)
    initialize(engine, factory)
    workflow = Workflow(config, factory)
    return config, engine, factory, workflow


@pytest.fixture
def document():
    return KnowledgeInput(id="manual", title="Synthetic manual", revision="1", brand="ABL", model="DEMO-1",
                          language="en", owner="reviewer", approved=True,
                          effective_at=now() - timedelta(days=1),
                          content="Synthetic DEMO-1 reference for testing. Not a real charger manual.",
                          url="https://example.invalid/manual", customer_url="https://example.invalid/manual")


@pytest.fixture
def email():
    return EmailInput(id="incoming-1", thread_id="thread-1", sender="Customer <customer@example.invalid>",
                      subject="ABL DEMO-1 manual", body="Please send the manual for ABL DEMO-1.",
                      headers={"Message-ID": "<original@example.invalid>"})


@pytest.fixture
def prepared(setup, document, email):
    from app.service import ingest
    config, engine, factory, workflow = setup
    with factory() as session:
        upsert_document(session, document)
        ingest(session, email, config)
        session.commit()
    workflow.process(email.id)
    return setup
