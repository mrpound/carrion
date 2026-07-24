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
