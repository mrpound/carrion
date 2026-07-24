import pytest
from carrion.config import load_config


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxx")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    cfg = load_config(env_path="/nonexistent")
    assert cfg.twilio_account_sid == "ACxxx"
    assert cfg.twilio_auth_token == "tok"
    assert cfg.anthropic_api_key == "sk-ant"


def test_load_config_reads_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text('TWILIO_ACCOUNT_SID="AC1"\nTWILIO_AUTH_TOKEN=tok2\n# comment\n')
    cfg = load_config(env_path=str(env))
    assert cfg.twilio_account_sid == "AC1"
    assert cfg.twilio_auth_token == "tok2"
    assert cfg.anthropic_api_key is None


def test_load_config_missing_twilio_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    with pytest.raises(ValueError, match="TWILIO"):
        load_config(env_path=str(tmp_path / "missing.env"))
