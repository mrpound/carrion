import re
from dataclasses import dataclass

from pypdf import PdfReader


class NoTextError(Exception):
    """Raised when a PDF yields no extractable text (likely a scanned image)."""


@dataclass
class Contacts:
    phone: str | None
    email: str | None
    linkedin: str | None
    location: str | None


_PHONE_RE = re.compile(
    r"(\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s|]+", re.I)
# "City, ST" on a single line — city allows letters/periods/spaces but not newlines
_LOCATION_RE = re.compile(r"([A-Z][A-Za-z. ]+,[ ]*[A-Z]{2})\b")


def extract_text(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def require_text(text: str) -> str:
    if not text or not text.strip():
        raise NoTextError("No extractable text found (is this a scanned image?)")
    return text


def extract_contacts(text: str) -> Contacts:
    phone_m = _PHONE_RE.search(text)
    email_m = _EMAIL_RE.search(text)
    linkedin_m = _LINKEDIN_RE.search(text)
    location_m = _LOCATION_RE.search(text)
    return Contacts(
        phone=phone_m.group(1).strip() if phone_m else None,
        email=email_m.group(0) if email_m else None,
        linkedin=linkedin_m.group(0) if linkedin_m else None,
        location=location_m.group(1).strip() if location_m else None,
    )
