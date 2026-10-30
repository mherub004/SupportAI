"""Google REST adapters. All requests retain system TLS/proxy configuration."""
import base64
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import parseaddr
from typing import Protocol
from urllib.parse import quote

import httpx

from app.schemas import EmailInput


class MailProvider(Protocol):
    def draft(self, email, body: str, rfc_id: str) -> str: ...
    def send(self, draft_id: str) -> str: ...
    def human_owned(self, email) -> bool: ...


class DemoMail:
    def draft(self, email, body, rfc_id):
        return f"demo-draft-{email.id}"

    def update_draft(self, draft_id, email, body, rfc_id):
        return draft_id

    def verify_draft(self, draft_id, email, body, rfc_id):
        return True

    def send(self, draft_id):
        return f"demo-sent-{draft_id}"

    def human_owned(self, email):
        return False


class GoogleClient:
    def __init__(self, config):
        self.config = config

    def token(self):
        if self.config.google_refresh_token:
            result = httpx.post("https://oauth2.googleapis.com/token", data={
                "grant_type": "refresh_token", "refresh_token": self.config.google_refresh_token,
                "client_id": self.config.google_client_id, "client_secret": self.config.google_client_secret,
            }, timeout=20)
            result.raise_for_status()
            return result.json()["access_token"]
        if self.config.gmail_access_token:
            return self.config.gmail_access_token
        import google.auth
        from google.auth.transport.requests import Request
        credentials, _ = google.auth.default(scopes=[
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/drive.readonly",
        ])
        credentials.refresh(Request())
        return credentials.token

    def request(self, method, path, **kwargs):
        result = httpx.request(method, "https://www.googleapis.com/" + path,
                               headers={"Authorization": f"Bearer {self.token()}"}, timeout=45, **kwargs)
        result.raise_for_status()
        return result

    def pages(self, path, key, params=None):
        params = dict(params or {})
        while True:
            data = self.request("GET", path, params=params).json()
            yield from data.get(key, [])
            if not data.get("nextPageToken"):
                break
            params["pageToken"] = data["nextPageToken"]


class Gmail(GoogleClient):
    root = "gmail/v1/users/me/"

    def verify_mailbox(self):
        profile = self.request("GET", self.root + "profile").json()
        if profile["emailAddress"].casefold() != self.config.mailbox.casefold():
            raise ValueError("Authenticated Gmail mailbox differs from MAILBOX")
        return profile

    def raw_reply(self, email, body, rfc_id):
        if "\r" in email.subject or "\n" in email.subject:
            raise ValueError("Invalid subject")
        message = EmailMessage(policy=SMTP)
        message["From"] = self.config.mailbox
        message["To"] = parseaddr(email.sender)[1]
        message["Subject"] = email.subject if email.subject.lower().startswith("re:") else "Re: " + email.subject
        original_id = email.headers.get("message-id", "")
        if not original_id or any(c in original_id for c in "\r\n"):
            raise ValueError("Missing or invalid original Message-ID")
        message["In-Reply-To"] = original_id
        message["References"] = (email.headers.get("references", "") + " " + original_id).strip()
        message["Message-ID"] = rfc_id
        message["Auto-Submitted"] = "auto-replied"
        message["X-SupportFlow"] = "1"
        message.set_content(body)
        return {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode(), "threadId": email.thread_id}

    def draft(self, email, body, rfc_id):
        self.verify_mailbox()
        data = self.request("POST", self.root + "drafts", json={
            "message": self.raw_reply(email, body, rfc_id)
        }).json()
        return data["id"]

    def update_draft(self, draft_id, email, body, rfc_id):
        self.verify_mailbox()
        return self.request("PUT", self.root + "drafts/" + quote(draft_id, safe=""), json={
            "id": draft_id, "message": self.raw_reply(email, body, rfc_id)
        }).json()["id"]

    def verify_draft(self, draft_id, email, body, rfc_id):
        from email import policy
        from email.parser import BytesParser
        data = self.request("GET", self.root + "drafts/" + quote(draft_id, safe=""),
                            params={"format": "raw"}).json()["message"]
        raw = data["raw"]
        actual = BytesParser(policy=policy.default).parsebytes(
            base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        expected_data = self.raw_reply(email, body, rfc_id)["raw"]
        expected = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(expected_data))
        headers = ["from", "to", "subject", "message-id", "in-reply-to", "references", "auto-submitted", "x-supportflow"]
        return (data["threadId"] == email.thread_id
                and not actual.get("Cc") and not actual.get("Bcc")
                and all(str(actual.get(h, "")) == str(expected.get(h, "")) for h in headers)
                and not actual.is_multipart()
                and actual.get_content().replace("\r\n", "\n") == expected.get_content().replace("\r\n", "\n"))

    def send(self, draft_id):
        self.verify_mailbox()
        return self.request("POST", self.root + "drafts/send", json={"id": draft_id}).json()["id"]

    def human_owned(self, email):
        thread = self.request("GET", self.root + "threads/" + quote(email.thread_id, safe=""),
                              params={"format": "metadata", "metadataHeaders": "X-SupportFlow"}).json()
        for message in thread.get("messages", []):
            headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
            if "SENT" in message.get("labelIds", []) and headers.get("x-supportflow") != "1":
                # Conservative: any human outgoing message in the thread pauses AI.
                return True
        return False

    def find_sent(self, rfc_id):
        messages = self.request("GET", self.root + "messages", params={
            "q": f"in:sent rfc822msgid:{rfc_id.strip('<>')}", "maxResults": 2
        }).json().get("messages", [])
        return messages[0]["id"] if len(messages) == 1 else None

    def find_draft(self, rfc_id):
        drafts = self.request("GET", self.root + "drafts", params={
            "q": f"rfc822msgid:{rfc_id.strip('<>')}", "maxResults": 2
        }).json().get("drafts", [])
        return drafts[0]["id"] if len(drafts) == 1 else None

    def fetch(self, message_id):
        data = self.request("GET", self.root + "messages/" + quote(message_id, safe=""),
                            params={"format": "full"}).json()
        if set(data.get("labelIds", [])) & {"SPAM", "TRASH", "SENT", "DRAFT"}:
            return None
        payload = data.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
        bodies = []

        def walk(part):
            # Do not forward attachments or HTML/script content to the model.
            if part.get("mimeType") == "text/plain" and not part.get("filename"):
                raw = part.get("body", {}).get("data", "")
                bodies.append(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", "replace"))
            for child in part.get("parts", []):
                walk(child)

        walk(payload)
        body = "\n".join(bodies).strip()
        if not body:
            # HTML-only emails remain review-only, without treating HTML as trusted evidence.
            body = "[No plain-text body. Human review required.]"
        return EmailInput(id=data["id"], thread_id=data["threadId"], sender=headers.get("from", ""),
                          subject=headers.get("subject", "(no subject)"), body=body[:50000], headers=headers)

    def changes(self, cursor):
        if not cursor:
            return None
        return list(self.pages(self.root + "history", "history", {
            "startHistoryId": cursor, "historyTypes": "messageAdded", "maxResults": 100
        }))

    def recent_ids(self):
        return [m["id"] for m in self.pages(self.root + "messages", "messages", {
            "q": "in:inbox newer_than:7d", "maxResults": 100
        })]

    def watch(self):
        if not self.config.gmail_topic:
            raise ValueError("GMAIL_TOPIC is required for watch renewal")
        self.verify_mailbox()
        return self.request("POST", self.root + "watch", json={
            "topicName": self.config.gmail_topic, "labelIds": ["INBOX"], "labelFilterBehavior": "include"
        }).json()


class Drive(GoogleClient):
    def documents(self):
        """Return complete folder inventory before caller atomically updates registry.

        Approval metadata lives in Drive appProperties managed by this OAuth app:
        supportflow_approved=true, brand, model, language, owner, visibility,
        effective_at, expires_at (optional). Missing metadata never grants approval.
        """
        folder = self.config.drive_folder_id
        if not folder or not all(c.isalnum() or c in "_-" for c in folder):
            raise ValueError("DRIVE_FOLDER_ID is required and must be a Drive ID")
        from datetime import datetime
        from io import BytesIO
        from pypdf import PdfReader
        from app.schemas import KnowledgeInput

        inventory = list(self.pages("drive/v3/files", "files", {
            "q": f"'{folder}' in parents and trashed = false", "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true", "pageSize": 100,
            "fields": "nextPageToken,files(id,name,mimeType,version,modifiedTime,webViewLink,appProperties)",
        }))
        result = []
        for file in inventory:
            props = file.get("appProperties", {})
            if props.get("supportflow_approved") != "true" or props.get("visibility") != "customer_safe":
                continue
            file_id = quote(file["id"], safe="")
            mime = file["mimeType"]
            if mime == "application/vnd.google-apps.document":
                content = self.request("GET", f"drive/v3/files/{file_id}/export",
                                       params={"mimeType": "text/plain"}).text
            elif mime in {"text/plain", "text/markdown", "application/pdf"}:
                raw = self.request("GET", f"drive/v3/files/{file_id}", params={
                    "alt": "media", "supportsAllDrives": "true"
                }).content
                if len(raw) > 10_000_000:
                    raise ValueError("Knowledge file exceeds 10MB limit")
                content = ("\n\n".join(f"[Page {index + 1}]\n" + (page.extract_text() or "")
                                      for index, page in enumerate(PdfReader(BytesIO(raw)).pages))
                           if mime == "application/pdf" else raw.decode("utf-8"))
            else:
                raise ValueError("Approved file has unsupported format")
            refreshed = self.request("GET", f"drive/v3/files/{file_id}", params={
                "fields": "version,modifiedTime", "supportsAllDrives": "true"
            }).json()
            if (refreshed.get("version") != file.get("version")
                    or refreshed.get("modifiedTime") != file.get("modifiedTime")):
                raise ValueError("Knowledge source changed during export; sync must retry")
            result.append(KnowledgeInput(
                id="drive:" + file["id"], title=file["name"], revision=file.get("version", file["modifiedTime"]),
                brand=props["brand"], model=props["model"], language=props["language"], owner=props["owner"],
                approved=True, visibility="customer_safe", content=content,
                effective_at=datetime.fromisoformat(props["effective_at"].replace("Z", "+00:00")),
                expires_at=datetime.fromisoformat(props["expires_at"].replace("Z", "+00:00"))
                if props.get("expires_at") else None,
                url=file.get("webViewLink", f"https://drive.google.com/file/d/{file['id']}/view"),
                customer_url=props.get("customer_url", ""),
            ))
        return result
