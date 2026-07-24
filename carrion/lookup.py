import re
from dataclasses import dataclass, field

import httpx

VOIP_CARRIER_KEYWORDS = [
    "TWILIO", "BANDWIDTH", "GOOGLE", "VONAGE", "MAGICJACK", "LINGO",
    "VOIP", "SKYPE", "TEXTPLUS", "TEXTNOW", "GOOGLE VOICE",
]


@dataclass
class LookupResult:
    phone: str
    national: str
    country: str
    calling_code: str
    area_code: str
    valid: bool | None
    carrier: str
    line_type: str
    mcc: str
    mnc: str
    error_code: str
    pump_score: str
    pump_category: str
    pump_blocked: str
    risk_level: str
    risk_reasons: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def normalize_number(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    return "+" + digits


def assess_risk(*, valid, line_type, carrier, country, error_code,
                pump_blocked, pump_score) -> tuple[str, list[str]]:
    level = "Low"
    reasons: list[str] = []

    if valid is False:
        level = "High"
        reasons.append("Number is not a valid phone number")

    if "VOIP" in (line_type or "").upper():
        level = "High"
        reasons.append(f"Number type is VoIP ({line_type})")

    carrier_upper = (carrier or "").upper()
    for kw in VOIP_CARRIER_KEYWORDS:
        if kw in carrier_upper:
            level = "High"
            reasons.append(f"Carrier is a known VoIP/virtual provider: {carrier}")
            break

    if valid is not False and country not in ("N/A", "US"):
        level = "High"
        reasons.append(f"Number is not US-based (country: {country})")

    if pump_blocked == "True":
        level = "High"
        reasons.append("Number is on Twilio's SMS-pumping block list")

    if pump_score.isdigit():
        score = int(pump_score)
        if score >= 66:
            level = "High"
            reasons.append(f"High SMS-pumping/fraud risk score ({score}/100)")
        elif score >= 33:
            if level != "High":
                level = "Medium"
            reasons.append(f"Elevated SMS-pumping/fraud risk score ({score}/100)")

    no_carrier = (carrier in ("N/A", "") or line_type in ("N/A", "")
                  or error_code != "None")
    if no_carrier:
        if level != "High":
            level = "Medium"
        if error_code != "None":
            reasons.append(
                f"Carrier lookup returned an error code ({error_code}) — "
                "carrier data unavailable")
        else:
            reasons.append("No identifiable carrier/type data returned")

    if not reasons:
        reasons.append("Appears to be a standard mobile or landline number")
    return level, reasons


def _s(value) -> str:
    return "N/A" if value is None else str(value)


def parse_response(data: dict) -> LookupResult:
    phone = data.get("phone_number") or "N/A"
    lti = data.get("line_type_intelligence") or {}
    pump = data.get("sms_pumping_risk") or {}

    carrier = _s(lti.get("carrier_name"))
    line_type = _s(lti.get("type"))
    err = lti.get("error_code")
    error_code = "None" if err is None else str(err)

    pb = pump.get("number_blocked")
    pump_blocked = "N/A" if pb is None else str(pb)
    ps = pump.get("sms_pumping_risk_score")
    pump_score = "N/A" if ps is None else str(ps)

    m = re.match(r"^\+1(\d{3})", phone)
    area_code = m.group(1) if m else "N/A"
    country = data.get("country_code") or "N/A"

    level, reasons = assess_risk(
        valid=data.get("valid"), line_type=line_type, carrier=carrier,
        country=country, error_code=error_code,
        pump_blocked=pump_blocked, pump_score=pump_score)

    return LookupResult(
        phone=phone, national=data.get("national_format") or "N/A",
        country=country, calling_code=data.get("calling_country_code") or "N/A",
        area_code=area_code, valid=data.get("valid"), carrier=carrier,
        line_type=line_type, mcc=_s(lti.get("mobile_country_code")),
        mnc=_s(lti.get("mobile_network_code")), error_code=error_code,
        pump_score=pump_score, pump_category=_s(pump.get("carrier_risk_category")),
        pump_blocked=pump_blocked, risk_level=level, risk_reasons=reasons,
        raw=data)


def lookup(phone: str, config) -> LookupResult:
    e164 = normalize_number(phone)
    url = (f"https://lookups.twilio.com/v2/PhoneNumbers/{e164}"
           "?Fields=line_type_intelligence,sms_pumping_risk")
    resp = httpx.get(
        url, auth=(config.twilio_account_sid, config.twilio_auth_token),
        timeout=20.0)
    return parse_response(resp.json())
