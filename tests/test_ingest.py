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
