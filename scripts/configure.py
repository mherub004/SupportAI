#!/usr/bin/env python3
"""Create local configuration without printing or overwriting credentials."""
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / ".env"
if path.exists():
    print(".env already exists; left unchanged.")
else:
    contents = (root / ".env.example").read_text()
    contents = contents.replace("CHANGE_ME_OPERATOR", secrets.token_urlsafe(48))
    contents = contents.replace("CHANGE_ME_DATABASE", secrets.token_urlsafe(32))
    with open(path, "x", opener=lambda p, f: __import__("os").open(p, f, 0o600)) as handle:
        handle.write(contents)
    print("Created private .env. Use its OPERATOR_TOKEN to sign into the local dashboard.")
