import os
from dataclasses import dataclass


@dataclass
class Config:
    twilio_account_sid: str
    twilio_auth_token: str
    anthropic_api_key: str | None


def _parse_dotenv(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                value = value.strip().strip('"')
                values[key.strip()] = value
    except FileNotFoundError:
        pass
    return values


def load_config(env_path: str = ".env") -> Config:
    dotenv = _parse_dotenv(env_path)

    def get(name: str) -> str | None:
        return os.environ.get(name) or dotenv.get(name)

    sid = get("TWILIO_ACCOUNT_SID")
    token = get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        raise ValueError(
            "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set in the "
            "environment or .env file"
        )
    return Config(
        twilio_account_sid=sid,
        twilio_auth_token=token,
        anthropic_api_key=get("ANTHROPIC_API_KEY"),
    )
