"""Fixed, read-only CRM queries for the authenticated review screen, never LLM tools."""
import json
import re
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select

from app.business import cipher, decode, digest
from app.db import Connector, now
from app.policy import valid_recipient


def salesforce_origin(value):
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or not host.endswith(".salesforce.com")
            or parsed.username or parsed.password or parsed.port or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment):
        raise ValueError("Use an HTTPS Salesforce organization origin")
    return "https://" + host


def netsuite_account(value):
    if not re.fullmatch(r"[A-Za-z0-9]+(?:[_-](?:SB|RP)[0-9]+)?", value, re.I):
        raise ValueError("Invalid NetSuite account ID")
    return value.lower().replace("_", "-")


def netsuite_origin(account):
    return "https://" + netsuite_account(account) + ".suitetalk.api.netsuite.com"


def salesforce_login(value):
    value = salesforce_origin(value or "https://login.salesforce.com")
    host = urlsplit(value).hostname
    if host not in {"login.salesforce.com", "test.salesforce.com"} and not host.endswith(".my.salesforce.com"):
        raise ValueError("Use Salesforce login, sandbox login or your My Domain")
    return value


def refresh(provider, fields):
    prefix = provider + "_"
    refresh_token = fields.get(prefix + "refresh_token")
    if not refresh_token:
        raise ValueError("Connect this account through OAuth first")
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token,
            "client_id": fields[prefix + "client_id"]}
    if provider == "salesforce":
        data["client_secret"] = fields[prefix + "client_secret"]
        response = httpx.post(salesforce_login(fields.get("salesforce_login_url")) + "/services/oauth2/token",
                              data=data, timeout=20)
    else:
        data["client_secret"] = fields[prefix + "client_secret"]
        # NetSuite requires HTTP Basic client authentication.
        data.pop("client_secret")
        data.pop("client_id")
        response = httpx.post(netsuite_origin(fields["netsuite_account_id"]) + "/services/rest/auth/oauth2/v1/token",
                              data=data, auth=(fields[prefix + "client_id"], fields[prefix + "client_secret"]), timeout=20)
    response.raise_for_status()
    result = response.json()
    fields[prefix + "access_token"] = result["access_token"]
    if result.get("refresh_token"):
        fields[prefix + "refresh_token"] = result["refresh_token"]
    if provider == "salesforce":
        fields["salesforce_instance_url"] = salesforce_origin(result.get("instance_url") or fields["salesforce_instance_url"])
    fields["_access_expires"] = (now() + timedelta(seconds=min(int(result.get("expires_in", 900)), 3600) - 60)).isoformat()
    return fields


def client_for(session, provider, base):
    """Serialize refresh and persist rotating tokens BEFORE subsequent API requests."""
    record = session.scalar(select(Connector).where(Connector.id == provider).with_for_update())
    if not record or not record.enabled:
        raise ValueError("Connector is not configured")
    fields = decode(record, base)
    previously_verified = record.verified_digest == digest(fields)
    from datetime import datetime
    expires = datetime.fromisoformat(fields.get("_access_expires") or "2000-01-01T00:00:00")
    if not fields.get(provider + "_access_token") or expires <= now():
        fields = refresh(provider, fields)
        record.encrypted_config = cipher(base).encrypt(json.dumps(fields).encode()).decode()
        if previously_verified:
            record.verified_digest = digest(fields)
        session.commit()
    return Salesforce(fields) if provider == "salesforce" else NetSuite(fields)


def one_match(records, project):
    if len(records) == 0:
        return {"status": "no_match", "records": []}
    if len(records) != 1:
        return {"status": "ambiguous", "records": []}
    return {"status": "matched", "records": [project(records[0])],
            "warning": "Email address match is not identity verification. Review internally; do not disclose account details without your identity checks."}


class Salesforce:
    def __init__(self, fields):
        self.fields = fields
        self.origin = salesforce_origin(fields["salesforce_instance_url"])
        self.headers = {"Authorization": "Bearer " + fields["salesforce_access_token"]}

    def get(self, path, **kwargs):
        result = httpx.get(self.origin + path, headers=self.headers, timeout=20, **kwargs)
        result.raise_for_status()
        return result.json()

    def verify(self):
        identity = self.get("/services/oauth2/userinfo")
        if not identity.get("organization_id"):
            raise ValueError("Salesforce organization identity missing")
        expected = self.fields.get("_organization_id")
        if expected and expected != identity["organization_id"]:
            raise ValueError("Salesforce organization identity changed")
        return identity["organization_id"]

    def lookup(self, email):
        if not valid_recipient(email):
            raise ValueError("Invalid customer email")
        versions = self.get("/services/data/")
        versions = [v for v in versions if re.fullmatch(r"\d+\.\d+", str(v.get("version", "")))]
        if not versions:
            raise ValueError("No supported Salesforce REST API version")
        version = max(versions, key=lambda v: float(v["version"]))["version"]
        escaped = email.replace("\\", "\\\\").replace("'", "\\'")
        query = "SELECT Id, Name, Account.Name FROM Contact WHERE Email = '" + escaped + "' LIMIT 2"
        data = self.get(f"/services/data/v{version}/query", params={"q": query})
        return one_match(data.get("records", []), lambda row: {
            "record_id": row["Id"], "display_name": row.get("Name", ""),
            "organization": (row.get("Account") or {}).get("Name", ""),
        })


class NetSuite:
    def __init__(self, fields):
        self.fields = fields
        self.origin = netsuite_origin(fields["netsuite_account_id"])
        self.headers = {"Authorization": "Bearer " + fields["netsuite_access_token"], "Prefer": "transient"}

    def query(self, query):
        result = httpx.post(self.origin + "/services/rest/query/v1/suiteql", headers=self.headers,
                            params={"limit": 2}, json={"q": query}, timeout=20)
        result.raise_for_status()
        return result.json().get("items", [])

    def verify(self):
        self.query("SELECT id FROM customer WHERE 1 = 0")
        return netsuite_account(self.origin.split("//")[1].split(".")[0])

    def lookup(self, email):
        if not valid_recipient(email):
            raise ValueError("Invalid customer email")
        escaped = email.casefold().replace("'", "''")
        rows = self.query("SELECT id, entityid, companyname FROM customer WHERE LOWER(email) = '" + escaped + "'")
        return one_match(rows, lambda row: {"record_id": str(row["id"]),
                                            "display_name": row.get("entityid", ""),
                                            "organization": row.get("companyname", "")})
