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


def test_west_virginia_does_not_match_virginia_code():
    # 540 is a Virginia area code; "West Virginia" must NOT match
    assert resolve("540", "Charleston, West Virginia").status == "MISMATCH"


def test_west_virginia_matches_wv_code():
    # 304 is a West Virginia area code
    assert resolve("304", "Charleston, West Virginia").status == "MATCH"


def test_lowercase_ok_not_matched_as_oklahoma():
    # 405 is Oklahoma (OK); the lowercase word "ok" in prose must not match
    assert resolve("405", "remote is ok with me").status == "MISMATCH"


def test_lowercase_in_not_matched_as_indiana():
    # 317 is Indiana (IN); the lowercase preposition "in" must not match
    assert resolve("317", "based in Chicago").status == "MISMATCH"
