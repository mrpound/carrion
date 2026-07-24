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
