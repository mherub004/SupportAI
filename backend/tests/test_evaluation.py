import json
from pathlib import Path

import pytest

from app.cli import seed
from app.db import Message, Send
from app.schemas import EmailInput
from app.service import ingest

CASES = [json.loads(line) for line in (Path(__file__).parents[1] / "evaluation/cases.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_synthetic_bilingual_acceptance_cases(setup, case):
    config, _, factory, workflow = setup
    seed(factory, config)
    email = EmailInput(id=case["id"], thread_id=case["id"], sender="customer@example.invalid",
                       subject=case["subject"], body=case["body"],
                       headers={"message-id": f"<{case['id']}@example.invalid>"})
    with factory() as session:
        ingest(session, email, config)
        session.commit()
    workflow.process(email.id)
    with factory() as session:
        message = session.get(Message, email.id)
        assert message.disposition == case["disposition"]
        assert message.language == case["language"]
        if case["tag"]:
            assert case["tag"] in message.risk_tags
        assert session.get(Send, email.id) is None
