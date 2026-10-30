#!/usr/bin/env python3
"""Exercise the deployed demo API + dashboard; never print configured secrets."""
import json
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

root = Path(__file__).resolve().parents[1]
config = {}
for line in (root / ".env").read_text().splitlines():
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        config[key] = value
assert config.get("CONNECTOR_MODE", "demo") == "demo", "Run smoke only against a synthetic demo"
client = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))


def call(path, method="GET", data=None, dashboard=False, auth=True):
    base = "http://localhost:3000" if dashboard else "http://127.0.0.1:8000"
    headers = {"Content-Type": "application/json"}
    if dashboard and method != "GET":
        headers["Origin"] = "http://localhost:3000"
    if auth and not dashboard:
        headers["Authorization"] = "Bearer " + config["OPERATOR_TOKEN"]
    req = Request(base + path, headers=headers, method=method,
                  data=json.dumps(data).encode() if data is not None else None)
    with client.open(req, timeout=15) as response:
        body = response.read()
        if "application/json" in response.headers.get("Content-Type", ""):
            return json.loads(body)
        return body.decode()


assert call("/health")["status"] == "ok"
try:
    call("/api/messages", auth=False)
    raise AssertionError("Unauthenticated API access succeeded")
except HTTPError as exc:
    assert exc.code == 401
for _ in range(30):
    overview = call("/api/overview")
    if overview["counts"].get("draft", 0) >= 5:
        break
    time.sleep(2)
else:
    raise AssertionError("Worker did not prepare five synthetic drafts")
messages = call("/api/messages")
assert len(messages) >= 5
assert call("/api/messages/demo-safety")["disposition"] == "escalate"
assert "untrusted_instructions" in call("/api/messages/demo-injection")["risk_tags"]
assert call("/api/messages/demo-en")["citations"][0]["revision"] == "demo-v1"
assert "SupportFlow" in call("/", dashboard=True, auth=False)
call("/api/session", "POST", {"token": config["OPERATOR_TOKEN"]}, dashboard=True)
assert len(call("/api/backend/messages", dashboard=True)) >= 5
assert call("/api/backend/overview", dashboard=True)["mode"] == "demo"
# Same-origin policy must reject cross-site state changes.
try:
    req = Request("http://localhost:3000/api/session", method="POST", data=b'{}',
                  headers={"Content-Type": "application/json", "Origin": "https://attacker.invalid"})
    client.open(req, timeout=10)
    raise AssertionError("Cross-origin login was accepted")
except HTTPError as exc:
    assert exc.code == 403
print("PASS: API health/auth, five worker drafts, safety escalation, source citations, dashboard session/proxy, CSRF origin check")
