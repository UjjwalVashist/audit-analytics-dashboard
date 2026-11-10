"""Every planted anomaly in the generated data must be found by its check."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "data")]

from audit_checks import checks  # noqa: E402
from generate_sample import generate  # noqa: E402


@pytest.fixture(scope="module")
def data():
    df, planted = generate(seed=7)  # a different seed than the shipped sample
    return df, planted, {r.key: r.flagged for r in checks.run_all(df)}


def test_duplicates_found(data):
    _, planted, found = data
    assert set(planted["duplicates"]) <= set(found["duplicates"]["BELNR"])


def test_every_gap_found(data):
    _, planted, found = data
    gaps = found["number_gaps"]
    missing = {n for a, b in zip(gaps["first_missing"], gaps["last_missing"]) for n in range(a, b + 1)}
    assert missing == set(planted["number_gaps"])


def test_weekend_and_holiday_postings_found(data):
    _, planted, found = data
    assert set(found["weekend_holiday"]["BELNR"]) == set(planted["weekend_holiday"])


def test_round_amounts_found(data):
    _, planted, found = data
    assert set(found["round_amounts"]["BELNR"]) == set(planted["round_amounts"]) | set(planted["override"])


def test_segregation_of_duties_found(data):
    _, planted, found = data
    assert set(found["segregation_of_duties"]["BELNR"]) == set(planted["segregation_of_duties"])


def test_below_limit_found_and_user_stands_out(data):
    _, planted, found = data
    flagged = found["below_limit"]
    assert set(planted["below_limit"]) <= set(flagged["BELNR"])
    assert flagged.iloc[0]["USNAM"] == "KOCH_J"  # sorted by how often each user does it


def test_benford_flags_the_splitting_user(data):
    df, _, _ = data
    by_user = checks.benford_by_user(df)
    assert by_user.iloc[0]["USNAM"] == "KOCH_J"
    assert by_user.iloc[0]["conformity"] == "nonconformity"
    assert by_user.iloc[0]["most_overrepresented_digit"] == 4


def test_benford_on_clean_data_conforms():
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(1)
    clean = pd.DataFrame({"DMBTR": np.exp(rng.normal(6, 2, 20000))})
    _, mad, conformity = checks.benford(clean)
    assert conformity == "close conformity", mad


def test_missing_columns_are_reported(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("BELNR,DMBTR\n1,10\n")
    with pytest.raises(ValueError, match="Missing columns"):
        checks.load_entries(f)


def test_exception_list_is_an_excel_file(data):
    df, _, _ = data
    assert checks.exception_list(checks.run_all(df))[:2] == b"PK"  # .xlsx is a zip file


@pytest.mark.parametrize("key", ["post_closing", "after_hours", "missing_description", "rare_users"])
def test_new_isa_240_checks_find_their_planted_entries(data, key):
    _, planted, found = data
    extra = set(planted["override"]) if key != "rare_users" else set()  # the override entries hit these too
    assert set(found[key]["BELNR"]) == set(planted[key]) | extra


def test_override_entries_get_the_highest_risk_score(data):
    df, planted, _ = data
    scores = checks.risk_scores(df, checks.run_all(df))
    top = scores.head(len(planted["override"]))
    assert set(top["BELNR"]) == set(planted["override"]) and set(top["level"]) == {"High"}
    assert top.iloc[0]["tests"] == 5


def test_risk_levels_follow_the_points():
    import pandas as pd
    df = pd.DataFrame({"BELNR": [1, 2, 3], "DMBTR": [1.0, 2.0, 3.0]})
    results = [checks.CheckResult("a", "A", "", pd.DataFrame({"BELNR": [1, 2]}), weight=1),
               checks.CheckResult("b", "B", "", pd.DataFrame({"BELNR": [1, 3]}), weight=3)]
    levels = dict(zip(*checks.risk_scores(df, results)[["BELNR", "level"]].T.values))
    assert levels == {1: "High", 2: "Low", 3: "High"}


def test_checks_that_need_optional_columns_skip_without_them(tmp_path):
    f = tmp_path / "old.csv"
    f.write_text("BELNR,BUDAT,HKONT,DMBTR,LIFNR,USNAM,FREIGABE\n1,2025-01-02,400000,10,V1,A,B\n")
    found = {r.key: r.flagged for r in checks.run_all(checks.load_entries(f))}
    assert all(found[k].empty for k in ("post_closing", "after_hours", "missing_description"))


def test_completeness_reconciles_the_population(data):
    df, planted, _ = data
    c = checks.completeness(df)
    assert c["postings"] == len(df) and c["missing_numbers"] == len(planted["number_gaps"])
    assert c["duplicate_keys"] == 0 and c["months_covered"] == 12
