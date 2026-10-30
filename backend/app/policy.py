import re
from email.utils import getaddresses, parseaddr

from app.db import Document, now

SAFETY = re.compile(
    r"smoke|overheat|electric\s*shock|burn(?:ing|t)|sparks?|exposed\s*wir|damaged\s*(?:cable|wire)|"
    r"rauch|überhitz|stromschlag|verschmort|funken|beschädigt.{0,20}(?:kabel|leitung)|"
    r"(?:open|öffnen|öffne).{0,30}(?:charger|gehäuse|wallbox)|"
    r"(?:bypass|überbrück|disable).{0,30}(?:safety|schutz|rcd|breaker)", re.I
)
HUMAN = re.compile(r"(?:speak|talk).{0,20}(?:human|person|agent)|human\s*(?:agent|please)|"
                   r"mensch|mitarbeiter|persönlich", re.I)
INJECTION = re.compile(r"ignore.{0,30}(?:instructions|rules|previous)|system\s*prompt|"
                       r"ignorier.{0,30}(?:regel|anweisung)|api[_ -]?key|password|passwort", re.I)
REVIEW = re.compile(r"warranty|refund|complaint|garantie|erstattung|beschwerde|reklamation", re.I)


def valid_recipient(sender):
    if any(c in sender for c in "\r\n"):
        return False
    addresses = getaddresses([sender])
    if len(addresses) != 1:
        return False
    _, address = addresses[0]
    return bool(re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+", address))


def classify(email, product_brands=("ABL", "Wallbox")):
    text = f"{email.subject}\n{email.body}"
    language = "de" if re.search(r"\b(hallo|bitte|mein|meine|ladegerät|anleitung|fehler|und|nicht)\b", text, re.I) else "en"
    brands = [brand for brand in product_brands if re.search(r"(?<!\w)" + re.escape(brand) + r"(?!\w)", text, re.I)]
    brand = brands[0] if len(brands) == 1 else "unknown"
    tags = []
    if SAFETY.search(text):
        tags.append("electrical_safety")
    if HUMAN.search(text):
        tags.append("human_requested")
    if INJECTION.search(text):
        tags.append("untrusted_instructions")
    if REVIEW.search(text):
        tags.append("commercial_review")
    return language, brand, tags


def excluded(email, mailbox):
    headers = email.headers
    sender = parseaddr(email.sender)[1].casefold()
    return (
        not valid_recipient(email.sender)
        or sender == mailbox.casefold()
        or headers.get("auto-submitted", "no").lower() != "no"
        or "list-id" in headers
        or headers.get("precedence", "").lower() in {"bulk", "junk", "list"}
        or bool(re.search(r"(?:mailer-daemon|postmaster|no-?reply)@", sender))
    )


def current(doc: Document):
    return (doc.approved and doc.visibility == "customer_safe" and doc.effective_at <= now()
            and (doc.expires_at is None or doc.expires_at > now()))


def safe_response(language):
    if language == "de":
        return "Vielen Dank für Ihre Nachricht. Ihr Anliegen erfordert eine persönliche Prüfung durch unser Support-Team."
    return "Thank you for your message. Your request requires personal review by our support team."


def validate_grounding(proposal, documents):
    docs = {doc.id: doc for doc in documents}
    if not proposal.citations:
        return False
    for citation in proposal.citations:
        doc = docs.get(citation.document_id)
        if (doc is None or not current(doc) or doc.revision != citation.revision
                or citation.quote not in doc.content):
            return False
    return True
