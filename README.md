# carrion

Twilio-powered vetting toolkit: phone-number carrier/risk lookup and resume-PDF
ingestion for screening applicants.

carrion is a `uv`-managed Python package exposing two commands:

- **`carrion`** — phone-number lookup: Twilio Lookup v2 (carrier / line-type
  intelligence + SMS-pumping risk), area-code vs. claimed-location geo check,
  and a composite risk verdict.
- **`carrion-vet`** — resume-PDF ingestion: extracts contacts + a work-experience
  table, runs the phone lookup, applies offline cross-checks, and prints/logs a
  composite vetting dossier.

## Setup

Install/sync the environment once (requires [uv](https://docs.astral.sh/uv/)):

```bash
uv sync
```

### Credentials (`.env`)

```bash
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
ANTHROPIC_API_KEY=sk-ant-...   # optional; enables resume experience extraction
```

Environment variables take precedence over `.env`.

## Usage

### Phone lookup

```bash
uv run carrion 4045551234 "Atlanta, GA" --full
# or via the compatibility shim:
./carrion.sh 4045551234 "Atlanta, GA" --full
```

- `<phone_number>` — 10-digit (country code added automatically) or 11-digit.
- `[claimed_location]` — optional; cross-checks the number's area code against
  the claimed location (a mismatch is a "verify" flag, not an auto-fail — people
  relocate).
- `--full` — interactive vetting worksheet (LinkedIn / role / resume flags) that
  folds into the composite verdict.

### Resume PDF vetting

```bash
uv run carrion-vet path/to/resume.pdf
uv run carrion-vet path/to/resume.pdf --no-log   # skip writing to vetting-log.tsv
```

Prints a dossier (candidate + contacts + experience table + carrier/risk +
offline-check flags + composite verdict). Non-interactive.

## Docker

Build the image:

    docker build -t carrion .

Batch-vet a local folder of resumes (the log is written into that same folder):

    docker run --rm --env-file .env -v "$PWD/resumes:/data" carrion

Vet a single resume in the mounted folder:

    docker run --rm --env-file .env -v "$PWD/resumes:/data" carrion carrion-vet /data/jane.pdf

Run a phone lookup instead of the default batch:

    docker run --rm --env-file .env carrion carrion 4045551234 "Atlanta, GA"

Or use Compose (mounts `./resumes` and reads `.env` automatically):

    docker compose run --rm carrion

Notes:
- `.env` must contain `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` (and optional
  `ANTHROPIC_API_KEY` for resume experience extraction).
- `/data` is read-write: `vetting-log.tsv` is written back into it so the record
  persists on your host.
- `carrion-vet /data` accepts a directory (batch every PDF) or a single PDF path.

## How the vetting works

The composite verdict combines the phone risk (High/Medium/Low) with a count of
flags. It is a **decision aid, not a verdict** — the itemized reasons are what
matter, and a human makes the call.

Offline cross-checks (`carrion-vet`, no network beyond the phone lookup):

- Area code vs. claimed location (geo mismatch).
- Missing/absent LinkedIn URL.
- Email domain vs. listed employers (informational).
- Overlapping or large-gap employment date ranges.

Phone risk flags a number High for: invalid, VoIP line type, known VoIP/virtual
carrier, non-US number, SMS-pumping block-list, or a high pumping-risk score;
Medium for elevated pumping score or unavailable carrier data.

## Privacy notes

- `carrion-vet` sends the resume's **text** to the Anthropic API to extract the
  name and experience table. Phone, email, and LinkedIn are parsed locally.
- `vetting-log.tsv` contains applicant PII and is gitignored — do not commit it.
- `.env` is gitignored.

## Development

```bash
uv run pytest        # run the test suite
```

## Note

`caller.sh` (Twilio test-call script) is a separate, unrelated utility and is not
part of the carrion package.
