# Design: carrion as a Python package with PDF ingestion

**Date:** 2026-07-23
**Status:** Approved (design), pending spec review

## Goal

Add resume-PDF ingestion to carrion so a user reviewing job applicants can drop
in a PDF and get: extracted contact info, an extracted work-experience table, a
Twilio phone lookup/risk assessment, deterministic offline cross-checks, and a
composite verdict — all logged. As part of this, restructure the project from a
bash script that shells out to Python into a proper Python package run via `uv`.

Context: carrion is one leg of a manual fraud-vetting process for remote-worker
applications. The fraud signature is a **composite** (generic identity + throwaway
number + unverifiable employers + claim-vs-evidence location mismatch), so the
tool surfaces signals for a human; it does not auto-reject. See
`memory/carrion-use-case.md`.

## Non-goals

- Active online verification (web-searching companies / LinkedIn). Explicitly
  out of scope — extraction + offline cross-checks only.
- `caller.sh` (incoming-call spam detection) — untouched, separate track.
- Inferring nationality/ethnicity. Checks are claim-vs-evidence only.

## Architecture

A `uv`-managed Python package. `carrion.sh`'s logic (Twilio v2 lookup + risk
scoring) and `areacodes.py` (area-code→state map) are ported into Python modules;
PDF ingestion is built on top.

```
carrion/
  pyproject.toml            # uv-managed; deps + [project.scripts] entry points
  carrion/
    __init__.py
    config.py               # load .env → Twilio + Anthropic creds
    lookup.py               # Twilio v2 Lookup + risk logic (port of carrion.sh)
    geo.py                  # area-code → state map + claim comparison (port of areacodes.py)
    ingest.py               # PDF → text (pypdf) + regex extraction of contacts
    extract.py              # Claude API → name + experience table (structured output)
    checks.py               # offline cross-checks → flags
    report.py               # dossier rendering + vetting-log.tsv append
    cli.py                  # `carrion` (phone) + `carrion-vet` (pdf) commands
  tests/
    test_geo.py
    test_checks.py
    test_ingest.py
    test_lookup.py          # mocked httpx
    test_extract.py         # mocked Anthropic client
    fixtures/               # sample resume text + Twilio/Claude response fixtures
  carrion.sh                # one-line shim: exec uv run carrion "$@"
```

Dependencies: `anthropic`, `pypdf`, `httpx`.

Entry points (`[project.scripts]`):
- `carrion` → phone lookup, behavior-compatible with today's `carrion.sh`
  (including `--full` interactive worksheet + location arg).
- `carrion-vet` → PDF ingestion pipeline.

Run as `uv run carrion 4045551234 "Atlanta, GA" --full` and
`uv run carrion-vet resume.pdf`.

## Module responsibilities & interfaces

### config.py
`load_config() -> Config` — reads env then `.env` (same precedence as today).
`Config` exposes `twilio_account_sid`, `twilio_auth_token`, `anthropic_api_key`
(the last optional). Raises a clear error for missing Twilio creds; Anthropic key
absence is tolerated (extraction degrades — see below).

### lookup.py
`lookup(phone: str, config) -> LookupResult`. Normalizes the number (10/11-digit
→ E.164), calls Twilio v2 `?Fields=line_type_intelligence,sms_pumping_risk`,
parses fields, and computes the phone risk (Low/Medium/High) with the same rules
the bash script uses today: invalid → High; VoIP substring in type → High; known
VoIP carrier keyword → High; non-US country → High; blocked / pump≥66 → High;
pump 33–65 → Medium; no carrier data / lookup error_code → Medium. `LookupResult`
is a dataclass carrying every displayed field + `risk_level` + `risk_reasons` +
the raw response dict.

### geo.py
`resolve(area_code: str, claimed_location: str | None) -> GeoResult` — the same
area-code→state table and MATCH/MISMATCH/KNOWN/TOLLFREE/UNKNOWN logic as
`areacodes.py`, returning a dataclass instead of tab-delimited text.

### ingest.py
`extract_text(pdf_path) -> str` (pypdf) and
`extract_contacts(text) -> Contacts` — regex for phone (first plausible
US number), email, LinkedIn URL, and a best-effort location string. All local,
deterministic. Empty text (scanned/image PDF) raises `NoTextError`.

### extract.py
`extract_resume(text, config) -> ResumeData | None`. Uses the `anthropic` SDK:
`client.messages.parse(model="claude-opus-4-8", max_tokens=16000,
output_format=ResumeData, messages=[...])`. `ResumeData` is a Pydantic model:
`name: str | None`, `location: str | None`, `experience: list[ExperienceRow]`
where `ExperienceRow = {company, role, start, end}` (strings; None allowed).
Structured outputs guarantees schema-valid JSON. Returns `None` (with a logged
warning) if `anthropic_api_key` is missing or the call fails — callers fall back
to a contacts-only dossier. Model is configurable via a module constant.

### checks.py
`run_checks(contacts, resume, lookup_result, geo_result) -> list[Flag]`.
Deterministic offline cross-checks:
1. **Area code vs location** — geo MISMATCH → flag (with the "people relocate"
   caveat in the message). (Red flag #3.)
2. **LinkedIn** — missing or malformed URL → flag. (#1, partial; authenticity is
   left to the human, URL is surfaced.)
3. **Email domain vs employers** — classify freemail vs custom domain; if custom,
   note whether it matches any company in the experience table (informational).
4. **Experience dates** — parse ranges; flag overlaps or large unexplained gaps.
   (#4 territory.)
Each `Flag` has a code, human message, and weight (all weight 1 for now).

### report.py
`render(dossier) -> str` prints the sectioned dossier: Candidate (name, contacts),
Location Check, Experience table, Carrier/Risk, Flags, Composite Verdict.
`log(dossier)` appends a row to `vetting-log.tsv` (superset of today's columns +
name, email, linkedin, flag codes). Timestamp via `datetime.now()`.

### cli.py
- `carrion`: argv parsing identical to today (`<phone> [location] [--full]`),
  calls lookup + geo + (optionally) the interactive worksheet + composite + log.
- `carrion-vet`: `<pdf> [--no-log]`. Runs the full pipeline, non-interactive,
  prints the dossier and logs. Auto-derives flags from `checks.py` — no prompts.

## carrion-vet data flow

```
resume.pdf
 → ingest.extract_text → ingest.extract_contacts   (local, deterministic)
 → extract.extract_resume (Claude, structured output)  (resume text → API)
 → lookup.lookup(best phone)  (Twilio v2 + risk)
 → geo.resolve(area_code, location)
 → checks.run_checks(...) → flags
 → composite verdict (phone-risk points + flag count; same thresholds as phone tool)
 → report.render + report.log
```

## Composite verdict

Same scoring model as the phone tool: phone-risk points (High=2/Medium=1/Low=0)
+ number of flags; ≥3 HIGH, 2 MEDIUM, 1 "minor — see notes", 0 clean. For
`carrion-vet` the flags come from `checks.py` (auto-derived) rather than the
interactive worksheet. Presented as a decision aid; the itemized reasons are what
matter. Thresholds/weights are constants, tunable later against real data.

## Error handling

- Scanned/image PDF (no extractable text) → clear "no text found; is this a
  scanned image?" message, exit non-zero.
- No phone number found in the resume → run extraction + checks anyway; skip the
  Twilio lookup; note it in the dossier.
- Missing Anthropic key or extraction failure → contacts-only dossier with an
  "experience extraction unavailable" note; still runs phone lookup + geo.
- Missing Twilio creds → same hard error as today.

## Testing (TDD)

- `test_geo`, `test_checks`, `test_ingest` — pure functions, tested directly with
  crafted inputs and sample resume-text fixtures.
- `test_lookup` — mock `httpx` with recorded Twilio v2 response fixtures
  (populated + error_code cases).
- `test_extract` — mock the Anthropic client to return a fixture `ResumeData`;
  assert graceful `None` on missing key / raised API error.
- Each module's behavior is written test-first.

## PII posture

Resume text is sent to the Anthropic API for experience extraction (accepted
trade-off of the hybrid extraction choice). `vetting-log.tsv` holds applicant PII
and stays gitignored. Both documented in the README. `.env` remains gitignored.

## Migration / compatibility

- `carrion.sh` becomes a one-line shim (`exec uv run carrion "$@"`), preserving
  existing invocation habits and the `--full` / location args.
- `areacodes.py` is removed (folded into `geo.py`).
- Existing `vetting-log.tsv` rows remain valid; new columns are appended to the
  header for new rows.
