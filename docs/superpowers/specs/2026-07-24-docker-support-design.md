# Design: Docker support + carrion-vet batch mode

**Date:** 2026-07-24
**Status:** Approved (design), pending spec review
**Branch:** pdf-ingestion (builds on the Python package restructure)

## Goal

Let the user run carrion in Docker, mounting a local directory of resume PDFs.
As part of this, extend `carrion-vet` to accept a directory (batch-process every
PDF in it) in addition to a single PDF, and write the vetting log into that
directory so it persists through the mount.

## Decisions (from brainstorming)

- `carrion-vet <path>` accepts **either** a single `.pdf` file (current behavior)
  **or** a directory — a directory processes every `*.pdf` in it (batch).
- **One writable mount** at `/data`; resumes are read from it and
  `vetting-log.tsv` is written back into it.
- Credentials via `docker run --env-file .env` (mounting `.env` also works). No
  code change needed — `load_config` already reads env vars.
- `ANTHROPIC_API_KEY` is optional; without it, experience extraction is skipped
  (graceful degradation already implemented). Recommended for full dossiers.

## Non-goals

- Publishing the image to a registry.
- Multi-arch build matrices.
- Changing the phone-only `carrion` command's behavior.

## Part 1 — `carrion-vet` batch mode (code)

### Behavior
- If the target path is a directory: glob `*.pdf` (case-insensitive), sorted;
  process each; print one dossier per resume; append each to a shared log.
- If the target is a file: unchanged single-resume behavior.
- **Log location:** written into the target directory — `<dir>/vetting-log.tsv`
  for a directory target, or `<parent-of-file>/vetting-log.tsv` for a single
  file. This lands the log in the mounted `/data` folder automatically and is
  sensible natively (log sits with the resumes). `--no-log` still suppresses it.
- **Per-file resilience:** a PDF that raises `NoTextError` (scanned/image) is
  reported to stdout and skipped; batch continues. In single-file mode a
  `NoTextError` still exits non-zero (unchanged).
- Empty directory (no PDFs) → clear message, exit non-zero.

### Refactor
Extract a helper from the current `main_vet` body:
`vet_one(pdf_path, config, *, log_path, no_log) -> int` — runs the existing
pipeline (ingest → extract → lookup → geo → checks → composite → render → log)
for one resume, returns 0 on success / 2 on `NoTextError`. `main_vet` resolves
the target into a list of PDF paths + the log path, then loops `vet_one`.

Files touched: `carrion/cli.py` (main_vet + vet_one). `report.log` already takes
a `path` argument, so no change there.

### Tests (`tests/test_cli_vet.py`, added)
- Directory with 2 dummy `.pdf` files (mock `extract_text`/`extract_resume`/
  `lookup`) → both dossiers printed; log at `<dir>/vetting-log.tsv` has header +
  2 rows.
- One PDF in the batch raises `NoTextError` → its error is printed, the other is
  still processed, exit 0.
- Empty directory → non-zero exit, message printed.
- Existing single-file tests continue to pass (log now lands next to the file —
  update the existing assertions to read from the file's parent dir).

## Part 2 — Docker artifacts

### `Dockerfile`
```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY carrion ./carrion
RUN uv sync --frozen --no-dev
ENTRYPOINT ["uv", "run"]
CMD ["carrion-vet", "/data"]
```
`ENTRYPOINT uv run` keeps both commands reachable — the default `CMD` batches
`/data`, and `docker run … <img> carrion 4045551234 "Atlanta, GA"` runs the
phone lookup. `--no-dev` skips pytest in the image.

### `.dockerignore`
Exclude: `.venv/`, `.git/`, `.claude/`, `docs/`, `tests/`, `vetting-log.tsv`,
`.env`, `__pycache__/`, `*.pyc`.

### `docker-compose.yml`
```yaml
services:
  carrion:
    build: .
    env_file: .env
    volumes:
      - ./resumes:/data
    command: carrion-vet /data
```
Everyday use: `docker compose run --rm carrion`.

### README
Add a "Docker" section: `docker build -t carrion .`; batch run with
`--env-file .env -v $PWD/resumes:/data`; phone-lookup run form; the compose
shortcut; note that `.env` supplies Twilio + optional Anthropic creds and the
log is written into the mounted folder.

## Error handling

- Missing Twilio creds in the container → the existing `load_config` `ValueError`
  surfaces (clear message), exit non-zero.
- No Anthropic key → experience extraction skipped per resume (existing
  behavior); dossier still produced.
- Unreadable/scanned PDF → skipped in batch, fatal in single-file mode.

## Testing / verification

- Unit tests as above (`uv run pytest`), all mocked — no network, no real PDFs,
  no Docker required in CI.
- Manual smoke check (documented, not automated): `docker build -t carrion .`
  succeeds, and `docker compose run --rm carrion` against a folder with one real
  PDF produces a dossier and writes `resumes/vetting-log.tsv` on the host.

## Compatibility

- Single-file `carrion-vet` invocation is unchanged except the log now lands next
  to the resume instead of the current working directory.
- The phone-only `carrion` command is untouched.
- No new Python dependencies.
