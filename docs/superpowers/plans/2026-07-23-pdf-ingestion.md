# PDF Ingestion + Python Package Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure carrion from a bash script into a uv-managed Python package and add resume-PDF ingestion (`carrion-vet`) that extracts contacts + an experience table, runs the Twilio phone lookup, applies offline cross-checks, and prints/logs a composite vetting dossier.

**Architecture:** A flat-layout Python package `carrion/` with focused modules (config, geo, lookup, ingest, extract, checks, report, cli). `carrion.sh`'s Twilio-lookup + risk logic and `areacodes.py`'s map are ported to Python. Two console entry points: `carrion` (phone lookup, behavior-compatible with today) and `carrion-vet` (PDF pipeline). Everything is TDD with mocked network for the Twilio and Anthropic calls.

**Tech Stack:** Python 3.11+, uv, pytest, httpx (Twilio), anthropic SDK (structured-output extraction, model `claude-opus-4-8`), pypdf.

---

## File Structure

- `pyproject.toml` — uv project metadata, deps, `[project.scripts]`.
- `carrion/__init__.py` — package marker.
- `carrion/config.py` — `Config` dataclass + `load_config()`.
- `carrion/geo.py` — area-code→state map + `resolve()`.
- `carrion/lookup.py` — Twilio v2 lookup + `assess_risk()` + `lookup()`.
- `carrion/ingest.py` — `extract_text()` (pypdf) + `extract_contacts()` (regex).
- `carrion/extract.py` — Pydantic `ResumeData` + `extract_resume()` (Claude).
- `carrion/checks.py` — `Flag`, `run_checks()`, `geo_flag()`, `composite()`.
- `carrion/report.py` — `Dossier` + `render()` + `log()`.
- `carrion/cli.py` — `main_lookup()` (carrion) + `main_vet()` (carrion-vet).
- `tests/` — one test module per source module; `tests/fixtures/`.
- `carrion.sh` — replaced with a one-line shim at the end.
- `areacodes.py` — removed at the end (folded into `geo.py`).

---

## Task 1: Project scaffolding (uv package)

**Files:**
- Create: `pyproject.toml`
- Create: `carrion/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create the package marker files**

`carrion/__init__.py`:
```python
"""carrion — phone-number and resume vetting toolkit."""

__version__ = "0.1.0"
```

`tests/__init__.py`:
```python
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "carrion"
version = "0.1.0"
description = "Phone-number and resume vetting toolkit"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40",
    "pypdf>=4.0",
    "httpx>=0.27",
]

[project.scripts]
carrion = "carrion.cli:main_lookup"
carrion-vet = "carrion.cli:main_vet"

[dependency-groups]
dev = ["pytest>=8.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["carrion"]
```

- [ ] **Step 3: Sync the environment**

Run: `uv sync`
Expected: creates `.venv`, installs anthropic/pypdf/httpx/pytest, installs `carrion` editable. No errors.

- [ ] **Step 4: Verify the package imports and pytest runs**

Run: `uv run python -c "import carrion; print(carrion.__version__)"`
Expected: prints `0.1.0`
Run: `uv run pytest -q`
Expected: `no tests ran` (exit 0 or 5 — no tests yet).

- [ ] **Step 5: Update `.gitignore` for the venv/lock**

Add these lines to `.gitignore` (keep existing `.env` and `vetting-log.tsv`):
```
.venv/
__pycache__/
*.pyc
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml carrion/__init__.py tests/__init__.py .gitignore uv.lock
git commit -m "chore: scaffold uv-managed carrion package"
```

---

## Task 2: config.py

**Files:**
- Create: `carrion/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
import pytest
from carrion.config import load_config


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxx")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    cfg = load_config(env_path="/nonexistent")
    assert cfg.twilio_account_sid == "ACxxx"
    assert cfg.twilio_auth_token == "tok"
    assert cfg.anthropic_api_key == "sk-ant"


def test_load_config_reads_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text('TWILIO_ACCOUNT_SID="AC1"\nTWILIO_AUTH_TOKEN=tok2\n# comment\n')
    cfg = load_config(env_path=str(env))
    assert cfg.twilio_account_sid == "AC1"
    assert cfg.twilio_auth_token == "tok2"
    assert cfg.anthropic_api_key is None


def test_load_config_missing_twilio_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    with pytest.raises(ValueError, match="TWILIO"):
        load_config(env_path=str(tmp_path / "missing.env"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'carrion.config'`.

- [ ] **Step 3: Write the implementation**

`carrion/config.py`:
```python
import os
from dataclasses import dataclass


@dataclass
class Config:
    twilio_account_sid: str
    twilio_auth_token: str
    anthropic_api_key: str | None


def _parse_dotenv(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                value = value.strip().strip('"')
                values[key.strip()] = value
    except FileNotFoundError:
        pass
    return values


def load_config(env_path: str = ".env") -> Config:
    dotenv = _parse_dotenv(env_path)

    def get(name: str) -> str | None:
        return os.environ.get(name) or dotenv.get(name)

    sid = get("TWILIO_ACCOUNT_SID")
    token = get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        raise ValueError(
            "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set in the "
            "environment or .env file"
        )
    return Config(
        twilio_account_sid=sid,
        twilio_auth_token=token,
        anthropic_api_key=get("ANTHROPIC_API_KEY"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add carrion/config.py tests/test_config.py
git commit -m "feat: add config loader (env + .env)"
```

---

## Task 3: geo.py (port areacodes)

**Files:**
- Create: `carrion/geo.py`
- Test: `tests/test_geo.py`

- [ ] **Step 1: Write the failing test**

`tests/test_geo.py`:
```python
from carrion.geo import resolve


def test_match_by_abbreviation():
    r = resolve("404", "Atlanta, GA")
    assert r.status == "MATCH"
    assert r.state_abbr == "GA"
    assert r.state_name == "Georgia"


def test_match_by_full_name():
    assert resolve("404", "Georgia").status == "MATCH"


def test_mismatch():
    r = resolve("404", "Dallas, TX")
    assert r.status == "MISMATCH"
    assert r.state_abbr == "GA"


def test_known_no_claim():
    r = resolve("212", None)
    assert r.status == "KNOWN"
    assert r.state_abbr == "NY"


def test_tollfree():
    assert resolve("800", "CA").status == "TOLLFREE"


def test_unknown():
    assert resolve("999", "CA").status == "UNKNOWN"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_geo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'carrion.geo'`.

- [ ] **Step 3: Write the implementation**

Create `carrion/geo.py`. Copy the `AREA_CODES`, `TOLL_FREE`, and `STATE_NAMES` dicts **verbatim** from the existing `areacodes.py` at the repo root into this module (they are already complete and correct), then add the dataclass and `resolve()` below them:

```python
import re
from dataclasses import dataclass

# --- paste AREA_CODES, TOLL_FREE, STATE_NAMES from areacodes.py here ---


@dataclass
class GeoResult:
    status: str  # MATCH | MISMATCH | KNOWN | TOLLFREE | UNKNOWN
    state_abbr: str | None
    state_name: str | None


def resolve(area_code: str, claimed_location: str | None) -> GeoResult:
    area_code = (area_code or "").strip()
    if area_code in TOLL_FREE:
        return GeoResult("TOLLFREE", None, None)
    abbr = AREA_CODES.get(area_code)
    if not abbr:
        return GeoResult("UNKNOWN", None, None)
    name = STATE_NAMES.get(abbr, abbr)

    claim = (claimed_location or "").strip().lower()
    if not claim:
        return GeoResult("KNOWN", abbr, name)

    abbr_hit = re.search(r"\b" + re.escape(abbr.lower()) + r"\b", claim) is not None
    name_hit = name.lower() in claim
    status = "MATCH" if (abbr_hit or name_hit) else "MISMATCH"
    return GeoResult(status, abbr, name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_geo.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add carrion/geo.py tests/test_geo.py
git commit -m "feat: port area-code geo resolver to Python"
```

---

## Task 4: lookup.py (Twilio v2 + risk)

**Files:**
- Create: `carrion/lookup.py`
- Test: `tests/test_lookup.py`

- [ ] **Step 1: Write the failing test**

`tests/test_lookup.py`:
```python
from carrion.lookup import normalize_number, assess_risk, parse_response


def test_normalize_10_digit():
    assert normalize_number("4045551234") == "+14045551234"


def test_normalize_11_digit():
    assert normalize_number("14045551234") == "+14045551234"


def test_normalize_strips_formatting():
    assert normalize_number("(404) 555-1234") == "+14045551234"


def _fields(**over):
    base = {
        "phone_number": "+14045551234", "national_format": "(404) 555-1234",
        "country_code": "US", "calling_country_code": "1", "valid": True,
        "line_type_intelligence": {"carrier_name": "AT&T", "type": "mobile",
            "mobile_country_code": "310", "mobile_network_code": "410",
            "error_code": None},
        "sms_pumping_risk": {"sms_pumping_risk_score": 5,
            "carrier_risk_category": "low", "number_blocked": False,
            "error_code": None},
    }
    base.update(over)
    return base


def test_mobile_is_low_risk():
    res = parse_response(_fields())
    assert res.risk_level == "Low"
    assert res.carrier == "AT&T"
    assert res.area_code == "404"


def test_voip_type_is_high():
    f = _fields(line_type_intelligence={"carrier_name": "Twilio",
        "type": "nonFixedVoip", "mobile_country_code": None,
        "mobile_network_code": None, "error_code": None})
    res = parse_response(f)
    assert res.risk_level == "High"


def test_no_carrier_data_is_medium():
    f = _fields(line_type_intelligence={"carrier_name": None, "type": None,
        "mobile_country_code": None, "mobile_network_code": None,
        "error_code": 60600})
    res = parse_response(f)
    assert res.risk_level == "Medium"


def test_non_us_is_high():
    res = parse_response(_fields(country_code="CA"))
    assert res.risk_level == "High"


def test_high_pump_score_is_high():
    f = _fields(sms_pumping_risk={"sms_pumping_risk_score": 80,
        "carrier_risk_category": "high", "number_blocked": False,
        "error_code": None})
    assert parse_response(f).risk_level == "High"


def test_assess_risk_returns_reasons():
    level, reasons = assess_risk(valid=True, line_type="nonFixedVoip",
        carrier="Twilio", country="US", error_code="None",
        pump_blocked="False", pump_score="0")
    assert level == "High"
    assert any("VoIP" in r for r in reasons)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_lookup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'carrion.lookup'`.

- [ ] **Step 3: Write the implementation**

`carrion/lookup.py`:
```python
import re
from dataclasses import dataclass, field

import httpx

VOIP_CARRIER_KEYWORDS = [
    "TWILIO", "BANDWIDTH", "GOOGLE", "VONAGE", "MAGICJACK", "LINGO",
    "VOIP", "SKYPE", "TEXTPLUS", "TEXTNOW", "GOOGLE VOICE",
]


@dataclass
class LookupResult:
    phone: str
    national: str
    country: str
    calling_code: str
    area_code: str
    valid: bool | None
    carrier: str
    line_type: str
    mcc: str
    mnc: str
    error_code: str
    pump_score: str
    pump_category: str
    pump_blocked: str
    risk_level: str
    risk_reasons: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def normalize_number(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    return "+" + digits


def assess_risk(*, valid, line_type, carrier, country, error_code,
                pump_blocked, pump_score) -> tuple[str, list[str]]:
    level = "Low"
    reasons: list[str] = []

    if valid is False:
        level = "High"
        reasons.append("Number is not a valid phone number")

    if "VOIP" in (line_type or "").upper():
        level = "High"
        reasons.append(f"Number type is VoIP ({line_type})")

    carrier_upper = (carrier or "").upper()
    for kw in VOIP_CARRIER_KEYWORDS:
        if kw in carrier_upper:
            level = "High"
            reasons.append(f"Carrier is a known VoIP/virtual provider: {carrier}")
            break

    if valid is not False and country not in ("N/A", "US"):
        level = "High"
        reasons.append(f"Number is not US-based (country: {country})")

    if pump_blocked == "True":
        level = "High"
        reasons.append("Number is on Twilio's SMS-pumping block list")

    if pump_score.isdigit():
        score = int(pump_score)
        if score >= 66:
            level = "High"
            reasons.append(f"High SMS-pumping/fraud risk score ({score}/100)")
        elif score >= 33:
            if level != "High":
                level = "Medium"
            reasons.append(f"Elevated SMS-pumping/fraud risk score ({score}/100)")

    no_carrier = (carrier in ("N/A", "") or line_type in ("N/A", "")
                  or error_code != "None")
    if no_carrier:
        if level != "High":
            level = "Medium"
        if error_code != "None":
            reasons.append(
                f"Carrier lookup returned an error code ({error_code}) — "
                "carrier data unavailable")
        else:
            reasons.append("No identifiable carrier/type data returned")

    if not reasons:
        reasons.append("Appears to be a standard mobile or landline number")
    return level, reasons


def _s(value) -> str:
    return "N/A" if value is None else str(value)


def parse_response(data: dict) -> LookupResult:
    phone = data.get("phone_number") or "N/A"
    lti = data.get("line_type_intelligence") or {}
    pump = data.get("sms_pumping_risk") or {}

    carrier = _s(lti.get("carrier_name"))
    line_type = _s(lti.get("type"))
    err = lti.get("error_code")
    error_code = "None" if err is None else str(err)

    pb = pump.get("number_blocked")
    pump_blocked = "N/A" if pb is None else str(pb)
    ps = pump.get("sms_pumping_risk_score")
    pump_score = "N/A" if ps is None else str(ps)

    m = re.match(r"^\+1(\d{3})", phone)
    area_code = m.group(1) if m else "N/A"
    country = data.get("country_code") or "N/A"

    level, reasons = assess_risk(
        valid=data.get("valid"), line_type=line_type, carrier=carrier,
        country=country, error_code=error_code,
        pump_blocked=pump_blocked, pump_score=pump_score)

    return LookupResult(
        phone=phone, national=data.get("national_format") or "N/A",
        country=country, calling_code=data.get("calling_country_code") or "N/A",
        area_code=area_code, valid=data.get("valid"), carrier=carrier,
        line_type=line_type, mcc=_s(lti.get("mobile_country_code")),
        mnc=_s(lti.get("mobile_network_code")), error_code=error_code,
        pump_score=pump_score, pump_category=_s(pump.get("carrier_risk_category")),
        pump_blocked=pump_blocked, risk_level=level, risk_reasons=reasons,
        raw=data)


def lookup(phone: str, config) -> LookupResult:
    e164 = normalize_number(phone)
    url = (f"https://lookups.twilio.com/v2/PhoneNumbers/{e164}"
           "?Fields=line_type_intelligence,sms_pumping_risk")
    resp = httpx.get(
        url, auth=(config.twilio_account_sid, config.twilio_auth_token),
        timeout=20.0)
    return parse_response(resp.json())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_lookup.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add carrion/lookup.py tests/test_lookup.py
git commit -m "feat: port Twilio v2 lookup + risk scoring to Python"
```

---

## Task 5: ingest.py (PDF text + contact regex)

**Files:**
- Create: `carrion/ingest.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ingest.py`:
```python
import pytest
from carrion.ingest import extract_contacts, NoTextError, require_text

SAMPLE = """
Jane Doe
Atlanta, GA
jane.doe@example.com | (404) 555-1234
linkedin.com/in/janedoe
Experience ...
"""


def test_extract_phone():
    assert extract_contacts(SAMPLE).phone == "(404) 555-1234"


def test_extract_email():
    assert extract_contacts(SAMPLE).email == "jane.doe@example.com"


def test_extract_linkedin():
    assert extract_contacts(SAMPLE).linkedin == "linkedin.com/in/janedoe"


def test_missing_fields_are_none():
    c = extract_contacts("no contacts here")
    assert c.phone is None and c.email is None and c.linkedin is None


def test_require_text_raises_on_empty():
    with pytest.raises(NoTextError):
        require_text("   \n  ")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'carrion.ingest'`.

- [ ] **Step 3: Write the implementation**

`carrion/ingest.py`:
```python
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
# "City, ST" — two-letter state after a comma
_LOCATION_RE = re.compile(r"([A-Z][A-Za-z.\s]+,\s*[A-Z]{2})\b")


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add carrion/ingest.py tests/test_ingest.py
git commit -m "feat: add PDF text extraction + contact regex"
```

---

## Task 6: extract.py (Claude structured output)

**Files:**
- Create: `carrion/extract.py`
- Test: `tests/test_extract.py`

- [ ] **Step 1: Write the failing test**

`tests/test_extract.py`:
```python
from unittest.mock import MagicMock

from carrion.config import Config
from carrion.extract import extract_resume, ResumeData, ExperienceRow


def _cfg(key):
    return Config(twilio_account_sid="AC", twilio_auth_token="t",
                  anthropic_api_key=key)


def test_returns_none_without_key():
    assert extract_resume("some text", _cfg(None)) is None


def test_parses_resume_with_mocked_client():
    parsed = ResumeData(name="Jane Doe", location="Atlanta, GA",
        experience=[ExperienceRow(company="Acme", role="Engineer",
                                  start="2020", end="2023")])
    fake_client = MagicMock()
    fake_client.messages.parse.return_value = MagicMock(parsed_output=parsed)

    result = extract_resume("resume text", _cfg("sk-ant"),
                            client=fake_client)
    assert result.name == "Jane Doe"
    assert result.experience[0].company == "Acme"
    fake_client.messages.parse.assert_called_once()


def test_returns_none_on_api_error():
    fake_client = MagicMock()
    fake_client.messages.parse.side_effect = RuntimeError("boom")
    assert extract_resume("resume text", _cfg("sk-ant"),
                          client=fake_client) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_extract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'carrion.extract'`.

- [ ] **Step 3: Write the implementation**

`carrion/extract.py`:
```python
from pydantic import BaseModel

MODEL = "claude-opus-4-8"

_PROMPT = (
    "Extract the candidate's full name, their stated location (city/state or "
    "country if present), and their work experience as a list of rows with "
    "company, role/title, start, and end (use the dates exactly as written; "
    "use null for anything not present). Only use information explicitly in "
    "the resume text. Do not infer or invent.\n\nResume text:\n"
)


class ExperienceRow(BaseModel):
    company: str | None = None
    role: str | None = None
    start: str | None = None
    end: str | None = None


class ResumeData(BaseModel):
    name: str | None = None
    location: str | None = None
    experience: list[ExperienceRow] = []


def extract_resume(text: str, config, client=None) -> ResumeData | None:
    if not config.anthropic_api_key:
        return None
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        response = client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            output_format=ResumeData,
            messages=[{"role": "user", "content": _PROMPT + text}],
        )
        return response.parsed_output
    except Exception:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_extract.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add carrion/extract.py tests/test_extract.py
git commit -m "feat: add Claude structured-output resume extraction"
```

---

## Task 7: checks.py (offline cross-checks + composite)

**Files:**
- Create: `carrion/checks.py`
- Test: `tests/test_checks.py`

- [ ] **Step 1: Write the failing test**

`tests/test_checks.py`:
```python
from carrion.geo import GeoResult
from carrion.extract import ResumeData, ExperienceRow
from carrion.ingest import Contacts
from carrion.checks import geo_flag, run_checks, composite, Flag


def test_geo_flag_on_mismatch():
    f = geo_flag(GeoResult("MISMATCH", "GA", "Georgia"), "Dallas, TX")
    assert f is not None and f.code == "GEO_MISMATCH"


def test_geo_flag_none_on_match():
    assert geo_flag(GeoResult("MATCH", "GA", "Georgia"), "Atlanta, GA") is None


def test_missing_linkedin_flag():
    contacts = Contacts(phone=None, email="a@b.com", linkedin=None, location=None)
    resume = ResumeData()
    flags = run_checks(contacts, resume, GeoResult("UNKNOWN", None, None))
    assert any(f.code == "NO_LINKEDIN" for f in flags)


def test_freemail_is_not_flagged_as_mismatch():
    contacts = Contacts(phone=None, email="jane@gmail.com",
                        linkedin="linkedin.com/in/j", location=None)
    resume = ResumeData(experience=[ExperienceRow(company="Acme")])
    flags = run_checks(contacts, resume, GeoResult("UNKNOWN", None, None))
    assert not any(f.code == "EMAIL_DOMAIN" for f in flags)


def test_date_overlap_flag():
    resume = ResumeData(experience=[
        ExperienceRow(company="A", start="2020", end="2023"),
        ExperienceRow(company="B", start="2021", end="2024"),
    ])
    contacts = Contacts(phone=None, email=None, linkedin="linkedin.com/in/j",
                        location=None)
    flags = run_checks(contacts, resume, GeoResult("UNKNOWN", None, None))
    assert any(f.code == "DATE_OVERLAP" for f in flags)


def test_composite_thresholds():
    assert composite("Low", 0)[0] == "LOW"
    assert composite("Medium", 0)[0] == "LOW"      # 1 point
    assert composite("High", 0)[0] == "MEDIUM"     # 2 points
    assert composite("Medium", 2)[0] == "HIGH"     # 3 points
    assert composite("High", 1)[0] == "HIGH"       # 3 points
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_checks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'carrion.checks'`.

- [ ] **Step 3: Write the implementation**

`carrion/checks.py`:
```python
import re
from dataclasses import dataclass

FREEMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "aol.com", "proton.me", "protonmail.com", "live.com", "msn.com",
}


@dataclass
class Flag:
    code: str
    message: str
    weight: int = 1


def geo_flag(geo, claimed_location: str | None) -> Flag | None:
    if geo.status == "MISMATCH":
        return Flag(
            "GEO_MISMATCH",
            f'Area code is registered to {geo.state_name}, not the claimed '
            f'location "{claimed_location}" — verify (people relocate)')
    return None


def _years(row) -> list[int]:
    text = f"{row.start or ''} {row.end or ''}"
    return [int(y) for y in re.findall(r"(19|20)\d{2}", text)]


def _date_flags(experience) -> list[Flag]:
    spans = []
    for row in experience:
        ys = _years(row)
        if len(ys) >= 2:
            spans.append((min(ys), max(ys)))
    spans.sort()
    flags: list[Flag] = []
    for i in range(1, len(spans)):
        prev_start, prev_end = spans[i - 1]
        start, end = spans[i]
        if start < prev_end:
            flags.append(Flag("DATE_OVERLAP",
                "Overlapping employment date ranges in the experience section"))
            break
    for i in range(1, len(spans)):
        if spans[i][0] - spans[i - 1][1] > 1:
            flags.append(Flag("DATE_GAP",
                "Unexplained gap (>1 year) between employment date ranges"))
            break
    return flags


def run_checks(contacts, resume, geo) -> list[Flag]:
    flags: list[Flag] = []

    gf = geo_flag(geo, resume.location or contacts.location)
    if gf:
        flags.append(gf)

    if not contacts.linkedin:
        flags.append(Flag("NO_LINKEDIN",
            "No LinkedIn URL found in the resume — verify identity manually"))

    if contacts.email and "@" in contacts.email:
        domain = contacts.email.rsplit("@", 1)[1].lower()
        if domain not in FREEMAIL_DOMAINS:
            companies = " ".join(
                (r.company or "").lower() for r in resume.experience)
            stem = domain.split(".")[0]
            if stem and stem not in companies:
                flags.append(Flag("EMAIL_DOMAIN",
                    f"Email domain ({domain}) does not match any listed "
                    "employer — informational"))

    flags.extend(_date_flags(resume.experience))
    return flags


def composite(phone_risk_level: str, flag_count: int) -> tuple[str, int]:
    points = {"High": 2, "Medium": 1, "Low": 0}.get(phone_risk_level, 0)
    total = points + flag_count
    if total >= 3:
        return "HIGH", total
    if total == 2:
        return "MEDIUM", total
    return "LOW", total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_checks.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add carrion/checks.py tests/test_checks.py
git commit -m "feat: add offline cross-checks + composite verdict"
```

---

## Task 8: report.py (dossier render + log)

**Files:**
- Create: `carrion/report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

`tests/test_report.py`:
```python
from carrion.report import Dossier, render, log
from carrion.checks import Flag
from carrion.extract import ResumeData, ExperienceRow
from carrion.ingest import Contacts
from carrion.geo import GeoResult


def _dossier():
    return Dossier(
        contacts=Contacts(phone="(404) 555-1234", email="j@x.com",
                          linkedin="linkedin.com/in/j", location="Atlanta, GA"),
        resume=ResumeData(name="Jane Doe", location="Atlanta, GA",
            experience=[ExperienceRow(company="Acme", role="Eng",
                                      start="2020", end="2023")]),
        lookup=None,
        geo=GeoResult("MATCH", "GA", "Georgia"),
        flags=[Flag("NO_LINKEDIN", "No LinkedIn URL found")],
        verdict="MEDIUM", verdict_points=2,
    )


def test_render_includes_name_and_verdict():
    out = render(_dossier())
    assert "Jane Doe" in out
    assert "MEDIUM" in out
    assert "Acme" in out


def test_log_appends_row(tmp_path):
    path = tmp_path / "vetting-log.tsv"
    log(_dossier(), timestamp="2026-07-23 10:00:00", path=str(path))
    lines = path.read_text().splitlines()
    assert lines[0].startswith("timestamp\t")
    assert "Jane Doe" in lines[1]
    log(_dossier(), timestamp="2026-07-23 11:00:00", path=str(path))
    assert len(path.read_text().splitlines()) == 3  # header + 2 rows
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'carrion.report'`.

- [ ] **Step 3: Write the implementation**

`carrion/report.py`:
```python
import os
from dataclasses import dataclass, field

LOG_HEADER = ("timestamp\tsource\tname\tphone\temail\tlinkedin\tcountry\t"
              "area_code\tgeo_status\ttype\tcarrier\tpump_score\tphone_risk\t"
              "flag_codes\tverdict")


@dataclass
class Dossier:
    contacts: object
    resume: object          # ResumeData | None
    lookup: object          # LookupResult | None
    geo: object             # GeoResult | None
    flags: list = field(default_factory=list)
    verdict: str = "LOW"
    verdict_points: int = 0
    source: str = "vet"


def render(d: Dossier) -> str:
    lines: list[str] = []
    name = getattr(d.resume, "name", None) or "N/A"
    lines.append("=== CANDIDATE VETTING DOSSIER ===")
    lines.append(f"Name        : {name}")
    lines.append(f"Phone       : {d.contacts.phone or 'N/A'}")
    lines.append(f"Email       : {d.contacts.email or 'N/A'}")
    lines.append(f"LinkedIn    : {d.contacts.linkedin or 'N/A'}")
    loc = getattr(d.resume, "location", None) or d.contacts.location or "N/A"
    lines.append(f"Location    : {loc}")

    if d.geo is not None:
        lines.append("")
        lines.append("-- Location Check --")
        lines.append(f"Reg. Region : {d.geo.state_name or d.geo.status}")

    if d.resume is not None and getattr(d.resume, "experience", None):
        lines.append("")
        lines.append("-- Experience --")
        for r in d.resume.experience:
            lines.append(f"  {r.company or '?'} — {r.role or '?'} "
                         f"({r.start or '?'}–{r.end or '?'})")
    elif d.resume is None:
        lines.append("")
        lines.append("-- Experience --")
        lines.append("  (experience extraction unavailable)")

    if d.lookup is not None:
        lines.append("")
        lines.append("-- Carrier / Risk --")
        lines.append(f"Type        : {d.lookup.line_type}")
        lines.append(f"Carrier     : {d.lookup.carrier}")
        lines.append(f"Pump Score  : {d.lookup.pump_score}")
        lines.append(f"Phone Risk  : {d.lookup.risk_level}")
        for reason in d.lookup.risk_reasons:
            lines.append(f"  • {reason}")

    lines.append("")
    lines.append("-- Flags --")
    if d.flags:
        for f in d.flags:
            lines.append(f"  • {f.message}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append(f"COMPOSITE VERDICT: {d.verdict} ({d.verdict_points} pts)")
    return "\n".join(lines)


def log(d: Dossier, timestamp: str, path: str = "vetting-log.tsv") -> None:
    if not os.path.exists(path):
        with open(path, "w") as fh:
            fh.write(LOG_HEADER + "\n")
    name = getattr(d.resume, "name", None) or ""
    lk = d.lookup
    row = [
        timestamp, d.source, name, d.contacts.phone or "",
        d.contacts.email or "", d.contacts.linkedin or "",
        (lk.country if lk else ""), (lk.area_code if lk else ""),
        (d.geo.status if d.geo else ""), (lk.line_type if lk else ""),
        (lk.carrier if lk else ""), (lk.pump_score if lk else ""),
        (lk.risk_level if lk else ""),
        ",".join(f.code for f in d.flags) or "none", d.verdict,
    ]
    with open(path, "a") as fh:
        fh.write("\t".join(row) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_report.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add carrion/report.py tests/test_report.py
git commit -m "feat: add dossier rendering + TSV logging"
```

---

## Task 9: cli.py — `carrion` phone command

**Files:**
- Create: `carrion/cli.py`
- Test: `tests/test_cli_lookup.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cli_lookup.py`:
```python
from unittest.mock import patch

from carrion.lookup import LookupResult
from carrion.config import Config


def _lookup_result():
    return LookupResult(
        phone="+14045551234", national="(404) 555-1234", country="US",
        calling_code="1", area_code="404", valid=True, carrier="AT&T",
        line_type="mobile", mcc="310", mnc="410", error_code="None",
        pump_score="2", pump_category="low", pump_blocked="False",
        risk_level="Low", risk_reasons=["Appears standard"], raw={})


def test_main_lookup_runs(capsys, tmp_path, monkeypatch):
    from carrion import cli
    cfg = Config("AC", "tok", None)
    with patch.object(cli, "load_config", return_value=cfg), \
         patch.object(cli, "lookup", return_value=_lookup_result()):
        monkeypatch.chdir(tmp_path)
        rc = cli.main_lookup(["4045551234", "Dallas, TX"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "COMPOSITE VERDICT" in out
    assert "not match" in out.lower() or "GEO" in out or "Georgia" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_lookup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'carrion.cli'`.

- [ ] **Step 3: Write the implementation**

`carrion/cli.py`:
```python
import sys
from datetime import datetime

from .config import load_config
from .lookup import lookup
from .geo import resolve
from .checks import geo_flag, composite, Flag
from .report import Dossier, render, log
from .ingest import Contacts


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main_lookup(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    full = "--full" in argv
    argv = [a for a in argv if a != "--full"]
    if not argv:
        print("Usage: carrion <phone_number> [claimed_location] [--full]")
        return 1

    phone = argv[0]
    claimed_location = argv[1] if len(argv) > 1 else None

    config = load_config()
    result = lookup(phone, config)
    geo = resolve(result.area_code, claimed_location)

    flags: list[Flag] = []
    gf = geo_flag(geo, claimed_location)
    if gf:
        flags.append(gf)

    if full and sys.stdin.isatty():
        prompts = [
            ("No LinkedIn, or profile looks copied/altered?", "LINKEDIN"),
            ("Past roles unverifiable online?", "ROLES"),
            ("Resume generic or doesn't match LinkedIn?", "RESUME_DRIFT"),
        ]
        print("Manual vetting (answer y for each red flag present):")
        for question, code in prompts:
            if input(f"  {question} [y/N] ").strip().lower().startswith("y"):
                flags.append(Flag(code, question))

    verdict, points = composite(result.risk_level, len(flags))
    dossier = Dossier(
        contacts=Contacts(phone=result.national, email=None, linkedin=None,
                          location=claimed_location),
        resume=None, lookup=result, geo=geo, flags=flags,
        verdict=verdict, verdict_points=points, source="phone")
    print(render(dossier))
    log(dossier, timestamp=_now())
    return 0


def main_vet(argv: list[str] | None = None) -> int:  # completed in Task 10
    raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_lookup.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add carrion/cli.py tests/test_cli_lookup.py
git commit -m "feat: add carrion phone-lookup CLI command"
```

---

## Task 10: cli.py — `carrion-vet` PDF command

**Files:**
- Modify: `carrion/cli.py` (replace the `main_vet` stub)
- Test: `tests/test_cli_vet.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cli_vet.py`:
```python
from unittest.mock import patch

from carrion.config import Config
from carrion.extract import ResumeData, ExperienceRow
from tests.test_cli_lookup import _lookup_result

SAMPLE = ("Jane Doe\nAtlanta, GA\njane@example.com | (404) 555-1234\n"
          "linkedin.com/in/janedoe\n")


def test_main_vet_runs(capsys, tmp_path, monkeypatch):
    from carrion import cli
    cfg = Config("AC", "tok", "sk-ant")
    resume = ResumeData(name="Jane Doe", location="Atlanta, GA",
        experience=[ExperienceRow(company="Acme", role="Eng",
                                  start="2020", end="2023")])
    with patch.object(cli, "load_config", return_value=cfg), \
         patch.object(cli, "extract_text", return_value=SAMPLE), \
         patch.object(cli, "extract_resume", return_value=resume), \
         patch.object(cli, "lookup", return_value=_lookup_result()):
        monkeypatch.chdir(tmp_path)
        rc = cli.main_vet(["resume.pdf"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Jane Doe" in out
    assert "Acme" in out
    assert "COMPOSITE VERDICT" in out


def test_main_vet_no_phone_skips_lookup(capsys, tmp_path, monkeypatch):
    from carrion import cli
    cfg = Config("AC", "tok", "sk-ant")
    with patch.object(cli, "load_config", return_value=cfg), \
         patch.object(cli, "extract_text", return_value="No number here"), \
         patch.object(cli, "extract_resume", return_value=ResumeData()):
        monkeypatch.chdir(tmp_path)
        rc = cli.main_vet(["resume.pdf"])
    assert rc == 0
    assert "N/A" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_vet.py -v`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Write the implementation**

Add these imports to the top of `carrion/cli.py` (alongside the existing ones):
```python
from .ingest import extract_text, extract_contacts, require_text, NoTextError
from .extract import extract_resume
from .checks import run_checks
```

Replace the `main_vet` stub in `carrion/cli.py` with:
```python
def main_vet(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    no_log = "--no-log" in argv
    argv = [a for a in argv if a != "--no-log"]
    if not argv:
        print("Usage: carrion-vet <resume.pdf> [--no-log]")
        return 1

    pdf_path = argv[0]
    config = load_config()

    try:
        text = require_text(extract_text(pdf_path))
    except NoTextError as exc:
        print(f"Error: {exc}")
        return 2

    contacts = extract_contacts(text)
    resume = extract_resume(text, config)
    location = (resume.location if resume and resume.location
                else contacts.location)

    result = None
    geo = resolve("N/A", location)
    if contacts.phone:
        result = lookup(contacts.phone, config)
        geo = resolve(result.area_code, location)

    resume_for_checks = resume if resume is not None else ResumeData()
    flags = run_checks(contacts, resume_for_checks, geo)

    phone_risk = result.risk_level if result else "Low"
    verdict, points = composite(phone_risk, len(flags))

    dossier = Dossier(
        contacts=contacts, resume=resume, lookup=result, geo=geo,
        flags=flags, verdict=verdict, verdict_points=points, source="vet")
    print(render(dossier))
    if not no_log:
        log(dossier, timestamp=_now())
    return 0
```

Add this import near the other `.extract` import in `carrion/cli.py`:
```python
from .extract import extract_resume, ResumeData
```
(Replace the earlier `from .extract import extract_resume` line so `ResumeData` is available in `main_vet`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_vet.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add carrion/cli.py tests/test_cli_vet.py
git commit -m "feat: add carrion-vet PDF ingestion CLI command"
```

---

## Task 11: Retire bash, add shim, docs

**Files:**
- Replace: `carrion.sh`
- Delete: `areacodes.py`
- Modify: `README.md`

- [ ] **Step 1: Replace `carrion.sh` with a shim**

Overwrite `carrion.sh` with:
```bash
#!/bin/bash
# Shim: carrion is now a uv-managed Python package. This preserves the old
# ./carrion.sh invocation by delegating to the `carrion` console script.
exec uv run --project "$(dirname "$0")" carrion "$@"
```

- [ ] **Step 2: Delete the ported area-code module**

Run: `git rm areacodes.py`
Expected: `areacodes.py` staged for deletion. (Its data now lives in `carrion/geo.py`.)

- [ ] **Step 3: Verify the shim works end-to-end (mocked-free smoke)**

Run: `./carrion.sh` (no args)
Expected: prints the usage line `Usage: carrion <phone_number> [claimed_location] [--full]` and exits non-zero. (Confirms the shim resolves to the Python entry point.)

- [ ] **Step 4: Update `README.md`**

Add a section documenting the new usage. Append to `README.md`:
```markdown
## Usage (Python package via uv)

Install/sync once:

    uv sync

Phone lookup (behavior-compatible with the old carrion.sh):

    uv run carrion 4045551234 "Atlanta, GA" --full
    # or via the shim:
    ./carrion.sh 4045551234 "Atlanta, GA" --full

Resume PDF vetting:

    uv run carrion-vet path/to/resume.pdf

### Credentials (.env)

    TWILIO_ACCOUNT_SID=...
    TWILIO_AUTH_TOKEN=...
    ANTHROPIC_API_KEY=...   # optional; enables resume experience extraction

### Privacy notes

- `carrion-vet` sends the resume's **text** to the Anthropic API to extract the
  experience table. Phone/email/LinkedIn are parsed locally.
- `vetting-log.tsv` contains applicant PII and is gitignored — do not commit it.
```

- [ ] **Step 5: Run the full suite once more**

Run: `uv run pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add carrion.sh README.md
git rm --cached areacodes.py 2>/dev/null || true
git commit -m "chore: retire bash script (shim), remove areacodes.py, update README"
```

---

## Self-Review Notes

- **Spec coverage:** config (Task 2), geo/#3 (Task 3, 7), lookup+risk (Task 4),
  ingest contacts (Task 5), Claude extraction (Task 6), offline checks #1/#3/#4 +
  composite (Task 7), dossier+log (Task 8), `carrion` phone CLI incl. `--full`
  worksheet (Task 9), `carrion-vet` non-interactive pipeline incl. no-phone and
  no-key fallbacks (Task 10), bash shim + areacodes removal + README/PII notes
  (Task 11). All spec sections map to a task.
- **Type consistency:** `Config`, `GeoResult`, `LookupResult`, `Contacts`,
  `ResumeData`/`ExperienceRow`, `Flag`, `Dossier` names and fields are used
  consistently across tasks. `composite()` returns `(verdict, points)`
  everywhere. `log()` takes `timestamp` + `path`.
- **Known wrinkle:** against a pre-existing old-format `vetting-log.tsv`, new
  rows append with the superset column set without rewriting the header — a
  personal-tool tradeoff noted in the spec, acceptable here.
