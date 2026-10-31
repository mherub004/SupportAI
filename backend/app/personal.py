"""Personal setup uses the existing encrypted connectors and draft-only workflow."""
from app.business import decode, public_connector
from app.db import Connector
from app.google import GoogleClient


def install_routes(app, base, factory, operator):
    from fastapi import Depends, HTTPException

    @app.get("/api/personal/drive-folders", dependencies=[Depends(operator)])
    def folders():
        with factory() as session:
            record = session.get(Connector, "google")
            if not public_connector(record, base)["verified"]:
                raise HTTPException(409, "Connect and verify Google first")
            fields = decode(record, base)
        try:
            data = GoogleClient(base.model_copy(update=fields)).request("GET", "drive/v3/files", params={
                "q": "mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                "fields": "nextPageToken,files(id,name)", "pageSize": 100, "orderBy": "name",
                "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
            }).json()
            return {"folders": data.get("files", []), "has_more": bool(data.get("nextPageToken"))}
        except Exception:
            raise HTTPException(422, "Cannot list Drive folders. Check Google access or paste a folder link instead") from None
