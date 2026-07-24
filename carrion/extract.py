from pydantic import BaseModel

MODEL = "claude-opus-4-8"

_PROMPT = (
    "Extract the candidate's full name, their stated location (city/state or "
    "country if present), and their work experience as a list of rows with "
    "company, role/title, start, and end (use the dates exactly as written; "
    "use null for anything not present). Only use information explicitly in "
    "the resume text. Do not infer or invent.\n\nResume text:\n"
)


class ExperienceRow(BaseModel):
    company: str | None = None
    role: str | None = None
    start: str | None = None
    end: str | None = None


class ResumeData(BaseModel):
    name: str | None = None
    location: str | None = None
    experience: list[ExperienceRow] = []


def extract_resume(text: str, config, client=None) -> ResumeData | None:
    if not config.anthropic_api_key:
        return None
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        response = client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            output_format=ResumeData,
            messages=[{"role": "user", "content": _PROMPT + text}],
        )
        return response.parsed_output
    except Exception:
        return None
