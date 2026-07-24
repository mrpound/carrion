from unittest.mock import MagicMock

from carrion.config import Config
from carrion.extract import extract_resume, ResumeData, ExperienceRow


def _cfg(key):
    return Config(twilio_account_sid="AC", twilio_auth_token="t",
                  anthropic_api_key=key)


def test_returns_none_without_key():
    assert extract_resume("some text", _cfg(None)) is None


def test_parses_resume_with_mocked_client():
    parsed = ResumeData(name="Jane Doe", location="Atlanta, GA",
        experience=[ExperienceRow(company="Acme", role="Engineer",
                                  start="2020", end="2023")])
    fake_client = MagicMock()
    fake_client.messages.parse.return_value = MagicMock(parsed_output=parsed)

    result = extract_resume("resume text", _cfg("sk-ant"),
                            client=fake_client)
    assert result.name == "Jane Doe"
    assert result.experience[0].company == "Acme"
    fake_client.messages.parse.assert_called_once()


def test_returns_none_on_api_error():
    fake_client = MagicMock()
    fake_client.messages.parse.side_effect = RuntimeError("boom")
    assert extract_resume("resume text", _cfg("sk-ant"),
                          client=fake_client) is None
