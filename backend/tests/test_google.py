import base64
from email import policy
from email.parser import BytesParser

from app.db import Message
from app.google import Gmail


def test_reply_preserves_thread_headers(setup, email):
    config, _, _, _ = setup
    gmail = Gmail(config)
    message = Message(**email.model_dump())
    data = gmail.raw_reply(message, "Approved answer", "<reply@supportflow.invalid>")
    parsed = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(data["raw"]))
    assert data["threadId"] == email.thread_id
    assert parsed["To"] == "customer@example.invalid"
    assert parsed["In-Reply-To"] == "<original@example.invalid>"
    assert parsed["References"] == "<original@example.invalid>"
    assert parsed["Auto-Submitted"] == "auto-replied"
    assert parsed["X-SupportFlow"] == "1"
    assert parsed["Message-ID"] == "<reply@supportflow.invalid>"
    assert "Approved answer" in parsed.get_content()


def test_gmail_fetch_excludes_spam(setup):
    config, _, _, _ = setup
    gmail = Gmail(config)

    class Result:
        def json(self):
            return {"id": "spam", "labelIds": ["SPAM"]}

    gmail.request = lambda *a, **k: Result()
    assert gmail.fetch("spam") is None
