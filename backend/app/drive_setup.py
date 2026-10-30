"""Browse, preview and approve exact revisions without writing metadata into Drive."""
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.business import decode, digest, public_connector
from app.db import Connector, Document, DriveApproval, audit, now
from app.google import Drive
from app.schemas import KnowledgeInput


def folder_id(value):
    if value.startswith("https://"):
        parsed = urlsplit(value)
        if parsed.hostname != "drive.google.com" or parsed.username or parsed.password:
            raise ValueError("Use a Google Drive folder link")
        match = re.search(r"/folders/([A-Za-z0-9_-]+)(?:/|$)", parsed.path)
        if not match:
            raise ValueError("Paste a Drive folder URL, not a file/notebook link")
        value = match.group(1)
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("A Drive folder ID or folder URL is required")
    return value


def source_client(factory, base):
    from app.service import Conflict
    with factory() as session:
        record = session.get(Connector, "google")
        if not public_connector(record, base)["verified"]:
            raise Conflict("Connect Google, save a folder and verify access first")
        fields = decode(record, base)
        folder_id(fields.get("drive_folder_id", ""))
        return Drive(base.model_copy(update=fields)), digest(fields)


def inventory(client):
    files = client.inventory()
    if len(files) > 1000:
        raise ValueError("Use a smaller approved folder (at most 1,000 direct-child files)")
    return files


def revoke_changed(session, files):
    versions = {file["id"]: file for file in files}
    for approval in session.scalars(select(DriveApproval)):
        file = versions.get(approval.file_id)
        if (not file or str(file.get("version", "")) != approval.revision
                or file.get("modifiedTime") != approval.modified_time):
            approval.approved = False
            document = session.get(Document, "drive:" + approval.file_id)
            if document:
                document.approved = False


class ImportInput(BaseModel):
    revision: str = Field(min_length=1, max_length=100)
    modified_time: str = Field(min_length=1, max_length=100)
    brand: str = Field(min_length=1, max_length=40)
    model: str = Field(default="general", min_length=1, max_length=100)
    language: Literal["en", "de"] = "en"
    owner: str = Field(min_length=1, max_length=200)
    customer_url: str = Field(default="", max_length=1000)
    approved: bool = False


def install_routes(app, base, factory, operator):
    from fastapi import Depends, HTTPException
    from app.service import Conflict, upsert_document
    secured = [Depends(operator)]

    def file_preview(file_id):
        client, config_digest = source_client(factory, base)
        files = inventory(client)
        with factory() as session:
            revoke_changed(session, files)
            session.commit()
        file = next((f for f in files if f["id"] == file_id), None)
        if not file:
            raise Conflict("File is not in the currently approved folder")
        return file, client.export(file), config_digest

    @app.get("/api/business/drive/files", dependencies=secured)
    def files():
        try:
            client, _ = source_client(factory, base)
            items = inventory(client)
        except Conflict:
            raise
        except Exception:
            raise HTTPException(422, "Cannot read folder. Check Google permissions and use a smaller approved folder") from None
        with factory() as session:
            revoke_changed(session, items)
            session.commit()
            approvals = {a.file_id: a for a in session.scalars(select(DriveApproval))}
            return [{"id": f["id"], "title": f["name"], "mime_type": f["mimeType"],
                     "revision": str(f.get("version", "")), "modified_time": f.get("modifiedTime", ""),
                     "approved": bool(approvals.get(f["id"]) and approvals[f["id"]].approved)} for f in items]

    @app.get("/api/business/drive/files/{file_id}", dependencies=secured)
    def preview(file_id: str):
        try:
            file, text, _ = file_preview(file_id)
            return {"id": file["id"], "title": file["name"], "revision": str(file.get("version", "")),
                    "modified_time": file["modifiedTime"], "content": text}
        except Conflict:
            raise
        except Exception:
            raise HTTPException(422, "Cannot preview source. Use a stable Docs/text/Markdown/text-extractable PDF under the size limit") from None

    @app.post("/api/business/drive/files/{file_id}/approve", dependencies=secured)
    def approve(file_id: str, data: ImportInput):
        if not data.approved:
            raise Conflict("A knowledge owner must explicitly approve this source")
        try:
            file, content, tested_digest = file_preview(file_id)
            if str(file.get("version", "")) != data.revision or file["modifiedTime"] != data.modified_time:
                raise Conflict("Source changed after preview. Review its new version before approving")
            source = KnowledgeInput(id="drive:" + file_id, title=file["name"], revision=data.revision,
                                    brand=data.brand, model=data.model, language=data.language, owner=data.owner,
                                    content=content, approved=True, effective_at=now(),
                                    url=file.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view"),
                                    customer_url=data.customer_url)
        except Conflict:
            raise
        except Exception:
            raise HTTPException(422, "Import failed. Check the file, source metadata and HTTPS customer link") from None
        with factory() as session:
            record = session.scalar(select(Connector).where(Connector.id == "google").with_for_update())
            if not record or digest(decode(record, base)) != tested_digest:
                raise Conflict("Google configuration changed. Browse the folder again")
            metadata = {"brand": data.brand, "model": data.model, "language": data.language,
                        "owner": data.owner, "effective_at": source.effective_at.isoformat(), "customer_url": data.customer_url}
            approval = session.get(DriveApproval, file_id)
            if approval:
                approval.revision, approval.modified_time = data.revision, data.modified_time
                approval.approved, approval.source_metadata = True, metadata
            else:
                session.add(DriveApproval(file_id=file_id, revision=data.revision, modified_time=data.modified_time,
                                          approved=True, source_metadata=metadata))
            upsert_document(session, source)
            audit(session, "drive_source_approved", file_id, actor="operator", revision=data.revision)
            session.commit()
        return {"status": "imported", "requires_reapproval_after_change": True}
