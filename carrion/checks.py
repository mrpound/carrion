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
    return [int(y) for y in re.findall(r"(?:19|20)\d{2}", text)]


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
