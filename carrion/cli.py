import os
import sys
from datetime import datetime

from .config import load_config
from .lookup import lookup
from .geo import resolve
from .checks import geo_flag, run_checks, composite, Flag
from .report import Dossier, render, log
from .ingest import extract_text, extract_contacts, require_text, NoTextError, Contacts
from .extract import extract_resume, ResumeData


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
