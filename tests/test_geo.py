from carrion.geo import resolve


def test_match_by_abbreviation():
    r = resolve("404", "Atlanta, GA")
    assert r.status == "MATCH"
    assert r.state_abbr == "GA"
    assert r.state_name == "Georgia"


def test_match_by_full_name():
    assert resolve("404", "Georgia").status == "MATCH"


def test_mismatch():
    r = resolve("404", "Dallas, TX")
    assert r.status == "MISMATCH"
    assert r.state_abbr == "GA"


def test_known_no_claim():
    r = resolve("212", None)
    assert r.status == "KNOWN"
    assert r.state_abbr == "NY"


def test_tollfree():
    assert resolve("800", "CA").status == "TOLLFREE"


def test_unknown():
    assert resolve("999", "CA").status == "UNKNOWN"
