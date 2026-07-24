from carrion.lookup import normalize_number, assess_risk, parse_response


def test_normalize_10_digit():
    assert normalize_number("4045551234") == "+14045551234"


def test_normalize_11_digit():
    assert normalize_number("14045551234") == "+14045551234"


def test_normalize_strips_formatting():
    assert normalize_number("(404) 555-1234") == "+14045551234"


def _fields(**over):
    base = {
        "phone_number": "+14045551234", "national_format": "(404) 555-1234",
        "country_code": "US", "calling_country_code": "1", "valid": True,
        "line_type_intelligence": {"carrier_name": "AT&T", "type": "mobile",
            "mobile_country_code": "310", "mobile_network_code": "410",
            "error_code": None},
        "sms_pumping_risk": {"sms_pumping_risk_score": 5,
            "carrier_risk_category": "low", "number_blocked": False,
            "error_code": None},
    }
    base.update(over)
    return base


def test_mobile_is_low_risk():
    res = parse_response(_fields())
    assert res.risk_level == "Low"
    assert res.carrier == "AT&T"
    assert res.area_code == "404"


def test_voip_type_is_high():
    f = _fields(line_type_intelligence={"carrier_name": "Twilio",
        "type": "nonFixedVoip", "mobile_country_code": None,
        "mobile_network_code": None, "error_code": None})
    res = parse_response(f)
    assert res.risk_level == "High"


def test_no_carrier_data_is_medium():
    f = _fields(line_type_intelligence={"carrier_name": None, "type": None,
        "mobile_country_code": None, "mobile_network_code": None,
        "error_code": 60600})
    res = parse_response(f)
    assert res.risk_level == "Medium"


def test_non_us_is_high():
    res = parse_response(_fields(country_code="CA"))
    assert res.risk_level == "High"


def test_high_pump_score_is_high():
    f = _fields(sms_pumping_risk={"sms_pumping_risk_score": 80,
        "carrier_risk_category": "high", "number_blocked": False,
        "error_code": None})
    assert parse_response(f).risk_level == "High"


def test_assess_risk_returns_reasons():
    level, reasons = assess_risk(valid=True, line_type="nonFixedVoip",
        carrier="Twilio", country="US", error_code="None",
        pump_blocked="False", pump_score="0")
    assert level == "High"
    assert any("VoIP" in r for r in reasons)
