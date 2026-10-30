from datetime import timedelta
from email.utils import parseaddr

from app.business import decode, digest, profile
from app.crm import client_for
from app.db import Connector, Message, MessageOrigin, audit, now


def install_routes(app, base, factory, operator):
    from fastapi import Depends, HTTPException
    from app.service import Conflict

    @app.post("/api/messages/{message_id}/crm-context", dependencies=[Depends(operator)])
    def context(message_id: str):
        with factory() as session:
            business = profile(session)
            message = session.get(Message, message_id)
            origin = session.get(MessageOrigin, message_id)
            if (not business or not message or not origin
                    or origin.origin != "google:" + business["support_email"]):
                raise Conflict("CRM lookup is available only for this company's real Gmail messages")
            email = parseaddr(message.sender)[1]
            if not email or message.status in {"purged", "excluded"}:
                raise HTTPException(409, "No eligible sender identity")
        results = {}
        for provider in ("salesforce", "netsuite"):
            with factory() as session:
                record = session.get(Connector, provider)
                if not record:
                    results[provider] = {"status": "not_connected", "records": []}
                    continue
                if (not record.verified_at or record.verified_at < now() - timedelta(hours=24)
                        or record.verified_digest != digest(decode(record, base))):
                    results[provider] = {"status": "verify_connection", "records": []}
                    continue
                try:
                    client = client_for(session, provider, base)
                    client.verify()
                    results[provider] = client.lookup(email)
                    audit(session, "crm_context_reviewed", message_id, actor="operator", provider=provider,
                          outcome=results[provider]["status"])
                    session.commit()
                except Exception:
                    session.rollback()
                    results[provider] = {"status": "unavailable", "records": []}
        return {"providers": results, "usage": "internal_review_only",
                "warning": "Email matching does not verify the customer's identity. CRM facts are not sent to Gemini or inserted into replies. No CRM records are modified."}
