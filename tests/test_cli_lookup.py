from unittest.mock import patch

from carrion.lookup import LookupResult
from carrion.config import Config


def _lookup_result():
    return LookupResult(
        phone="+14045551234", national="(404) 555-1234", country="US",
        calling_code="1", area_code="404", valid=True, carrier="AT&T",
        line_type="mobile", mcc="310", mnc="410", error_code="None",
        pump_score="2", pump_category="low", pump_blocked="False",
        risk_level="Low", risk_reasons=["Appears standard"], raw={})


def test_main_lookup_runs(capsys, tmp_path, monkeypatch):
    from carrion import cli
    cfg = Config("AC", "tok", None)
    with patch.object(cli, "load_config", return_value=cfg), \
         patch.object(cli, "lookup", return_value=_lookup_result()):
        monkeypatch.chdir(tmp_path)
        rc = cli.main_lookup(["4045551234", "Dallas, TX"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "COMPOSITE VERDICT" in out
    assert "not match" in out.lower() or "GEO" in out or "Georgia" in out
