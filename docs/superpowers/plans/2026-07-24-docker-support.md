# Docker Support + carrion-vet Batch Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run carrion in Docker with a mounted directory of resume PDFs, and extend `carrion-vet` to batch-process a directory (in addition to a single PDF), writing the vetting log into the target directory.

**Architecture:** Refactor `main_vet` into a reusable `vet_one` helper plus a dispatcher that handles a file or a directory of `*.pdf`. Add a Dockerfile on the official uv image with `ENTRYPOINT ["uv","run"]`, a `.dockerignore`, and a `docker-compose.yml` wiring the `/data` volume + `.env`.

**Tech Stack:** Python 3.11+, uv, pytest; Docker (`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`) + Docker Compose.

---

## File Structure

- Modify: `carrion/cli.py` — refactor `main_vet`, add `vet_one` + `_pdfs_in`.
- Modify: `tests/test_cli_vet.py` — add batch/empty/skip tests.
- Create: `Dockerfile`, `.dockerignore`, `docker-compose.yml`.
- Modify: `README.md` — add Docker section.

---

## Task 1: carrion-vet batch mode

**Files:**
- Modify: `carrion/cli.py`
- Test: `tests/test_cli_vet.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_cli_vet.py` (the file already imports `patch`, `Config`, `ResumeData`, `ExperienceRow`, `_lookup_result`, and defines `SAMPLE`):
```python
def test_main_vet_directory_batch(capsys, tmp_path):
    from carrion import cli
    cfg = Config("AC", "tok", "sk-ant")
    (tmp_path / "a.pdf").write_text("x")
    (tmp_path / "b.pdf").write_text("x")
    resume = ResumeData(name="Jane Doe", location="Atlanta, GA",
        experience=[ExperienceRow(company="Acme", role="Eng",
                                  start="2020", end="2023")])
    with patch.object(cli, "load_config", return_value=cfg), \
         patch.object(cli, "extract_text", return_value=SAMPLE), \
         patch.object(cli, "extract_resume", return_value=resume), \
         patch.object(cli, "lookup", return_value=_lookup_result()):
        rc = cli.main_vet([str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.count("COMPOSITE VERDICT") == 2
    log_lines = (tmp_path / "vetting-log.tsv").read_text().splitlines()
    assert log_lines[0].startswith("timestamp\t")
    assert len(log_lines) == 3  # header + 2 rows


def test_main_vet_directory_skips_bad_pdf(capsys, tmp_path):
    from carrion import cli
    cfg = Config("AC", "tok", "sk-ant")
    (tmp_path / "good.pdf").write_text("x")
    (tmp_path / "zbad.pdf").write_text("x")

    def fake_text(path):
        return "" if path.endswith("zbad.pdf") else SAMPLE

    resume = ResumeData(name="Jane Doe", location="Atlanta, GA", experience=[])
    with patch.object(cli, "load_config", return_value=cfg), \
         patch.object(cli, "extract_text", side_effect=fake_text), \
         patch.object(cli, "extract_resume", return_value=resume), \
         patch.object(cli, "lookup", return_value=_lookup_result()):
        rc = cli.main_vet([str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.count("COMPOSITE VERDICT") == 1
    assert "zbad.pdf" in out


def test_main_vet_empty_directory(capsys, tmp_path):
    from carrion import cli
    cfg = Config("AC", "tok", None)
    with patch.object(cli, "load_config", return_value=cfg):
        rc = cli.main_vet([str(tmp_path)])
    assert rc == 2
    assert "No PDF" in capsys.readouterr().out
```

- [ ] **Step 2: Run the new tests, confirm they FAIL**

Run: `uv run pytest tests/test_cli_vet.py -v`
Expected: the 3 new tests FAIL (directory path currently treated as a file → `PdfReader`/`NoTextError` path, wrong behavior). The 2 existing tests still pass.

- [ ] **Step 3: Refactor `main_vet` and add helpers**

In `carrion/cli.py`, add `import os` at the top (with the other stdlib imports). Replace the entire existing `main_vet` function with:
```python
def vet_one(pdf_path: str, config, *, log_path: str, no_log: bool) -> int:
    try:
        text = require_text(extract_text(pdf_path))
    except NoTextError as exc:
        print(f"Error ({pdf_path}): {exc}")
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
        log(dossier, timestamp=_now(), path=log_path)
    return 0


def _pdfs_in(directory: str) -> list[str]:
    return sorted(
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if name.lower().endswith(".pdf")
    )


def main_vet(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    no_log = "--no-log" in argv
    argv = [a for a in argv if a != "--no-log"]
    if not argv:
        print("Usage: carrion-vet <resume.pdf | directory> [--no-log]")
        return 1

    target = argv[0]
    config = load_config()

    if os.path.isdir(target):
        pdfs = _pdfs_in(target)
        if not pdfs:
            print(f"No PDF files found in {target}")
            return 2
        log_path = os.path.join(target, "vetting-log.tsv")
        for i, pdf in enumerate(pdfs):
            if i:
                print()
            vet_one(pdf, config, log_path=log_path, no_log=no_log)
        return 0

    log_path = os.path.join(os.path.dirname(target) or ".", "vetting-log.tsv")
    return vet_one(target, config, log_path=log_path, no_log=no_log)
```

- [ ] **Step 4: Run the full vet test file, confirm all pass**

Run: `uv run pytest tests/test_cli_vet.py -v`
Expected: 5 passed (2 original + 3 new).

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: all pass (previously 42, now 45).

- [ ] **Step 6: Commit**

```bash
git add carrion/cli.py tests/test_cli_vet.py
git commit -m "feat: carrion-vet batch-processes a directory; log lands in target dir"
```

---

## Task 2: Docker artifacts

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `docker-compose.yml`

- [ ] **Step 1: Create `.dockerignore`**

```
.venv/
.git/
.claude/
docs/
tests/
vetting-log.tsv
.env
__pycache__/
*.pyc
resumes/
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install dependencies against the locked versions first (better layer caching).
COPY pyproject.toml uv.lock ./
COPY carrion ./carrion
RUN uv sync --frozen --no-dev

# Mount a host directory of resumes at /data (read-write: the log is written here).
# Default command batch-processes /data; override to run the phone lookup, e.g.:
#   docker run --env-file .env <img> carrion 4045551234 "Atlanta, GA"
ENTRYPOINT ["uv", "run"]
CMD ["carrion-vet", "/data"]
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
services:
  carrion:
    build: .
    env_file: .env
    volumes:
      - ./resumes:/data
    command: carrion-vet /data
```

- [ ] **Step 4: Build the image (smoke check)**

Run: `docker build -t carrion .`
Expected: build succeeds; final image tagged `carrion`. (If Docker is unavailable in this environment, skip and note it — the build must be run on the user's machine.)

- [ ] **Step 5: Verify the entrypoint resolves the CLI (smoke check)**

Run: `docker run --rm carrion carrion` (no phone arg → usage line)
Expected: prints `Usage: carrion <phone_number> [claimed_location] [--full]`. Confirms `uv run` entrypoint + console script work. (Skip if Docker unavailable.)

- [ ] **Step 6: Commit**

```bash
git add Dockerfile .dockerignore docker-compose.yml
git commit -m "feat: add Docker image + compose with /data volume mount"
```

---

## Task 3: README Docker section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a Docker section**

Insert a `## Docker` section into `README.md` (after the Usage section):
```markdown
## Docker

Build the image:

    docker build -t carrion .

Batch-vet a local folder of resumes (log is written into the same folder):

    docker run --rm --env-file .env -v "$PWD/resumes:/data" carrion

Vet a single resume in the mounted folder:

    docker run --rm --env-file .env -v "$PWD/resumes:/data" carrion carrion-vet /data/jane.pdf

Run a phone lookup instead of the default batch:

    docker run --rm --env-file .env carrion carrion 4045551234 "Atlanta, GA"

Or use Compose (mounts ./resumes and reads .env automatically):

    docker compose run --rm carrion

Notes:
- `.env` must contain `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` (and optional
  `ANTHROPIC_API_KEY` for resume experience extraction).
- The mounted `/data` folder is read-write: `vetting-log.tsv` is written back
  into it so the record persists on your host.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document Docker usage + volume mount"
```

---

## Self-Review Notes

- **Spec coverage:** batch directory + single file (Task 1), log-in-target-dir
  (Task 1, `log_path`), per-file skip on NoTextError + empty-dir message
  (Task 1 tests), Dockerfile with uv base + `ENTRYPOINT uv run` + `/data` CMD
  (Task 2), `.dockerignore` (Task 2), `docker-compose.yml` (Task 2), README
  Docker section incl. env-file + optional Anthropic key + log persistence
  (Task 3). All spec items mapped.
- **Type/behavior consistency:** `vet_one(pdf_path, config, *, log_path, no_log)`
  and `_pdfs_in(directory)` are defined in Task 1 and used only there; `log()`
  already accepts `path=`. `main_vet` return codes: 1 (usage), 2 (empty dir /
  single-file NoTextError), 0 (success incl. batch with skips).
- **No placeholders.**
- **Known limitation:** Docker build/run steps (Task 2 steps 4–5) require Docker;
  if unavailable in the execution environment they are documented as
  user-machine smoke checks rather than automated.
