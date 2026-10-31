"""Authorization-code/PKCE handshakes. Tokens are persisted encrypted, never returned to browsers."""
import base64
import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.business import Profile, cipher, decode, digest, profile, save_connector
from app.crm import netsuite_account, netsuite_origin, salesforce_login, salesforce_origin
from app.db import BusinessConfig, Connector, MessageOrigin, OAuthAttempt, audit, now

PROVIDERS = {"google", "salesforce", "netsuite"}


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


def public_origin(base):
    value = (base.public_app_url or base.render_external_url).rstrip("/")
    parsed = urlsplit(value)
    local = parsed.hostname in {"localhost", "127.0.0.1"}
    if (not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
            or (parsed.scheme != "https" and not (local and parsed.scheme == "http"))):
        raise ValueError("Set PUBLIC_APP_URL to the public HTTPS dashboard origin (Render supplies it automatically)")
    return value


def redirect_uri(base, provider):
    segment = "test/" if base.workspace == "personal_test" else ""
    return public_origin(base) + "/api/oauth/callback/" + segment + provider


def endpoints(provider, fields):
    if provider == "google":
        return "https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token"
    if provider == "salesforce":
        origin = salesforce_login(fields.get("salesforce_login_url"))
        return origin + "/services/oauth2/authorize", origin + "/services/oauth2/token"
    account = netsuite_account(fields["netsuite_account_id"])
    return (f"https://{account}.app.netsuite.com/app/login/oauth2/authorize.nl",
            netsuite_origin(account) + "/services/rest/auth/oauth2/v1/token")


def hosted_fields(provider, base):
    prefix = "google" if provider == "google" else provider
    fields = {name: getattr(base, name, "") for name in (prefix + "_client_id", prefix + "_client_secret")}
    if not all(fields.values()):
        return {}
    if provider == "salesforce":
        fields["salesforce_login_url"] = base.salesforce_login_url
    if provider == "netsuite" and base.netsuite_account_id:
        fields["netsuite_account_id"] = base.netsuite_account_id
    return fields


def start(session, provider, binding, base, personal=False):
    if provider not in PROVIDERS:
        raise ValueError("Unsupported OAuth provider")
    if personal:
        if base.workspace != "personal_test":
            raise ValueError("Use the separate personal test environment")
        if provider != "google":
            raise ValueError("Personal sign-in requires Google")
        marker = session.get(BusinessConfig, "personal")
        if profile(session) and not (marker and marker.value.get("enabled")) and session.scalar(
                select(MessageOrigin.message_id).where(MessageOrigin.origin != "demo").limit(1)):
            raise ValueError("Use business setup for this existing company")
    record = session.get(Connector, provider)
    existing_fields = decode(record, base) if record and record.enabled else {}
    prefix = "google" if provider == "google" else provider
    if not (existing_fields.get(prefix + "_client_id") and existing_fields.get(prefix + "_client_secret")):
        hosted = hosted_fields(provider, base)
        if not hosted:
            raise ValueError("The host must configure its provider OAuth application first")
        if provider == "netsuite" and existing_fields.get("netsuite_account_id"):
            hosted["netsuite_account_id"] = existing_fields["netsuite_account_id"]
        if provider == "google" and not personal and not existing_fields.get("mailbox"):
            business = profile(session)
            if not business:
                raise ValueError("Save the company support mailbox first")
            hosted["mailbox"] = business["support_email"]
        save_connector(session, provider, hosted, base)
        session.flush()
        record = session.get(Connector, provider)
    if not record or not record.enabled:
        raise ValueError("Save the administrator app/client configuration first")
    fields = decode(record, base)
    prefix = "google" if provider == "google" else provider
    if not fields.get(prefix + "_client_id") or not fields.get(prefix + "_client_secret"):
        raise ValueError("Save the OAuth client ID and secret first")
    authorization_url, _ = endpoints(provider, fields)
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(32)
    uri = redirect_uri(base, provider)
    payload = {"verifier": verifier, "redirect_uri": uri, "config_digest": digest(fields),
               "personal": personal, "profile_digest": digest(profile(session) or {})}
    session.execute(delete(OAuthAttempt).where((OAuthAttempt.expires_at < now()) | OAuthAttempt.consumed))
    session.add(OAuthAttempt(state_hash=fingerprint(state), provider=provider, binding_hash=fingerprint(binding),
                             encrypted_payload=cipher(base).encrypt(json.dumps(payload).encode()).decode(),
                             expires_at=now() + timedelta(minutes=10)))
    scope = {"google": "https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/drive.readonly",
             "salesforce": "api refresh_token openid", "netsuite": "rest_webservices"}[provider]
    params = {"response_type": "code", "client_id": fields[prefix + "_client_id"], "redirect_uri": uri,
              "state": state, "scope": scope, "code_challenge_method": "S256",
              "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()}
    if provider == "google":
        params.update(access_type="offline", prompt="consent", include_granted_scopes="true")
        if fields.get("mailbox"):
            params["login_hint"] = fields["mailbox"]
    audit(session, "oauth_started", provider, actor="operator")
    session.commit()
    return {"authorization_url": authorization_url + "?" + urlencode(params)}


def finish(factory, provider, state, binding, code, base):
    with factory() as session:
        attempt = session.scalar(select(OAuthAttempt).where(
            OAuthAttempt.state_hash == fingerprint(state)).with_for_update())
        if (not attempt or attempt.provider != provider or attempt.consumed or attempt.expires_at <= now()
                or not hmac.compare_digest(attempt.binding_hash, fingerprint(binding))):
            raise ValueError("OAuth session expired, already used or belongs to another browser")
        payload = json.loads(cipher(base).decrypt(attempt.encrypted_payload.encode()))
        record = session.get(Connector, provider)
        if not record or not record.enabled:
            raise ValueError("Connection was removed")
        fields = decode(record, base)
        if digest(fields) != payload["config_digest"] or payload["redirect_uri"] != redirect_uri(base, provider):
            raise ValueError("OAuth configuration changed; start again")
        attempt.consumed = True
        session.commit()  # Reserve before exchanging a one-time code. Never retry an ambiguous exchange.
    _, token_url = endpoints(provider, fields)
    prefix = "google" if provider == "google" else provider
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": payload["redirect_uri"],
            "client_id": fields[prefix + "_client_id"], "code_verifier": payload["verifier"]}
    kwargs = {}
    if provider == "netsuite":
        data.pop("client_id")
        kwargs["auth"] = (fields[prefix + "_client_id"], fields[prefix + "_client_secret"])
    else:
        data["client_secret"] = fields[prefix + "_client_secret"]
    response = httpx.post(token_url, data=data, timeout=25, **kwargs)
    response.raise_for_status()
    tokens = response.json()
    if not tokens.get("refresh_token") or not tokens.get("access_token"):
        raise ValueError("Offline/refresh access was not granted; check provider application policies and reconnect")
    updates = {prefix + "_refresh_token": tokens["refresh_token"]}
    if provider == "google":
        if not fields.get("mailbox") and not payload.get("personal"):
            raise ValueError("Configure the support mailbox first")
        # Validate the actual selected Google identity, using the newly issued access token.
        from app.google import Gmail
        gmail = Gmail(base.model_copy(update={"google_refresh_token": "", "gmail_access_token": tokens["access_token"]}))
        if payload.get("personal"):
            mailbox = gmail.request("GET", gmail.root + "profile").json()["emailAddress"].casefold()
            personal_profile = Profile(name="Personal inbox", industry="Personal email testing",
                                       support_email=mailbox, escalation_email=mailbox, languages=["en", "de"])
            updates["mailbox"] = mailbox
        else:
            gmail.config.mailbox = fields["mailbox"]
            gmail.verify_mailbox()
        updates["gmail_access_token"] = ""  # Refresh token is authoritative for continued access.
    else:
        updates[prefix + "_access_token"] = tokens["access_token"]
        if provider == "salesforce":
            updates["salesforce_instance_url"] = salesforce_origin(tokens["instance_url"])
    with factory() as session:
        record = session.scalar(select(Connector).where(Connector.id == provider).with_for_update())
        if not record or digest(decode(record, base)) != payload["config_digest"]:
            raise ValueError("Connection changed while authorizing; reconnect")
        if payload.get("personal"):
            if digest(profile(session) or {}) != payload["profile_digest"]:
                raise ValueError("Profile changed while authorizing")
            if session.scalar(select(MessageOrigin.message_id).where(
                    MessageOrigin.origin != "demo", MessageOrigin.origin != "google:" + mailbox).limit(1)):
                raise ValueError("Use a separate installation for a different mailbox")
            existing = session.get(BusinessConfig, "profile")
            if not existing:
                session.add(BusinessConfig(key="profile", value=personal_profile.model_dump()))
            elif existing.value.get("support_email") != mailbox or not session.get(BusinessConfig, "personal"):
                existing.value = personal_profile.model_dump()
            marker = session.get(BusinessConfig, "personal")
            if not marker:
                session.add(BusinessConfig(key="personal", value={"enabled": True}))
        save_connector(session, provider, updates, base)
        record = session.get(Connector, provider)
        saved = decode(record, base)
        # Blank secret fields normally preserve an existing token; remove a stale test access token explicitly.
        if provider == "google":
            saved.pop("gmail_access_token", None)
        else:
            saved["_access_expires"] = (now() + timedelta(seconds=min(int(tokens.get("expires_in", 900)), 3600)-60)).isoformat()
        record.encrypted_config = cipher(base).encrypt(json.dumps(saved).encode()).decode()
        if payload.get("personal") and not saved.get("drive_folder_id"):
            record.verified_at, record.verified_digest = now(), digest(saved)
        audit(session, "oauth_connected", provider, actor="operator")
        session.commit()


class StartInput(BaseModel):
    binding: str = Field(min_length=32, max_length=200)
    personal: bool = False


class FinishInput(StartInput):
    state: str = Field(min_length=32, max_length=200)
    code: str = Field(min_length=1, max_length=4000)


def install_routes(app, base, factory, operator):
    from fastapi import Depends, HTTPException
    secured = [Depends(operator)]

    @app.get("/api/business/oauth", dependencies=secured)
    def oauth_status():
        try:
            with factory() as session:
                ready = {}
                for key in PROVIDERS:
                    record = session.get(Connector, key)
                    fields = decode(record, base) if record and record.enabled else {}
                    if not (fields.get(key + "_client_id") and fields.get(key + "_client_secret")):
                        fields = {**fields, **hosted_fields(key, base)}
                    ready[key] = bool(fields.get(key + "_client_id") and fields.get(key + "_client_secret")
                                      and (key != "netsuite" or fields.get("netsuite_account_id")))
            return {"available": True, "google_ready": ready["google"], "provider_ready": ready,
                    "redirect_uris": {key: redirect_uri(base, key) for key in sorted(PROVIDERS)}}
        except ValueError:
            return {"available": False, "redirect_uris": {}, "detail": "Set PUBLIC_APP_URL to the HTTPS dashboard origin"}

    @app.post("/api/business/oauth/{provider}/start", dependencies=secured)
    def oauth_start(provider: str, data: StartInput):
        try:
            with factory() as session:
                return start(session, provider, data.binding, base, data.personal)
        except (ValueError, KeyError):
            raise HTTPException(422, "Save the provider's app/client configuration and configure the public callback origin first") from None

    @app.post("/api/business/oauth/{provider}/complete", dependencies=secured)
    def oauth_complete(provider: str, data: FinishInput):
        if provider not in PROVIDERS:
            raise HTTPException(404, "Provider not found")
        try:
            finish(factory, provider, data.state, data.binding, data.code, base)
        except Exception:
            with factory() as session:
                audit(session, "oauth_failed", provider, actor="operator")
                session.commit()
            raise HTTPException(422, "Authorization could not be completed. Check selected account, offline access, client settings, callback URL and network access, then start again.") from None
        return {"status": "connected", "verification_required": True}
