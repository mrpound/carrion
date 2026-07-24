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
