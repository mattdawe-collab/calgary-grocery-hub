import pandas as pd
import pytest

from data_quality import normalize_archive_dates, parse_dates
from tools.repair_archive import backfill_classifications, dedupe_rows, repair_dates


def test_parse_dates_handles_mixed_formats_without_blanking():
    # pandas 2.x infers the format from the first value and, with
    # errors="coerce", silently turns every other format into NaT. This is
    # how 26,827 archive rows lost their Date between May and Sep 2026.
    s = pd.Series(["2025-12-12 00:00:00", "2026-05-13", "2026-09-10T03:00:00-04:00", "garbage", None])
    out = parse_dates(s)
    assert out.iloc[0] == pd.Timestamp("2025-12-12")
    assert out.iloc[1] == pd.Timestamp("2026-05-13")
    assert out.iloc[2] == pd.Timestamp("2026-09-10")
    assert pd.isna(out.iloc[3]) and pd.isna(out.iloc[4])
    assert out.dt.tz is None


def test_normalize_archive_dates_writes_plain_iso_days():
    df = pd.DataFrame({
        "Date": ["2025-12-12 00:00:00", "2026-05-13", None],
        "Valid_From": ["2026-05-07T03:00:00-04:00", "2026-05-14", "2026-05-21"],
        "Valid_Until": ["2026-05-13T23:59:59-04:00", "2026-05-20", None],
        "Item": ["a", "b", "c"],
    })
    out = normalize_archive_dates(df)
    assert out["Date"].tolist()[:2] == ["2025-12-12", "2026-05-13"]
    assert pd.isna(out["Date"].iloc[2])
    assert out["Valid_From"].tolist() == ["2026-05-07", "2026-05-14", "2026-05-21"]
    assert out["Valid_Until"].tolist()[:2] == ["2026-05-13", "2026-05-20"]
    assert out["Item"].tolist() == ["a", "b", "c"]          # untouched


def test_repair_dates_reconstructs_missing_date_from_flyer_start():
    df = pd.DataFrame({
        "Date": [None, "2026-04-29", None],
        "Valid_From": ["2026-05-07T03:00:00-04:00", "2026-04-30", None],
        "Valid_Until": ["2026-05-13T23:59:59-04:00", "2026-05-06", "2026-06-10"],
        "Store": ["A", "A", "A"], "Item": ["x", "y", "z"], "Price_Value": [1, 2, 3],
    })
    out, stats = repair_dates(df)
    assert out["Date"].tolist()[0] == "2026-05-06"           # Thursday flyer, Wednesday scrape
    assert out["Date"].tolist()[1] == "2026-04-29"           # existing date kept
    assert out["Date"].tolist()[2] == "2026-06-04"           # fallback: Valid_Until - 6 days
    assert stats["reconstructed"] == 2


def test_dedupe_rows_drops_repeat_scrapes_of_same_flyer_line():
    df = pd.DataFrame({
        "Date": ["2026-09-09", "2026-09-09", "2026-09-16"],
        "Store": ["Sobeys", "Sobeys", "Sobeys"],
        "Item": ["Bacon", "bacon ", "Bacon"],
        "Price_Value": [5.99, 5.99, 5.99],
        "ai_normalized_name": ["Bacon", "bacon ", "Bacon"],
    })
    out, removed = dedupe_rows(df)
    assert removed == 1
    assert len(out) == 2


def test_backfill_classifications_uses_trusted_names_only():
    df = pd.DataFrame({
        "Date": ["2026-01-10", "2026-07-15", "2026-07-15"],
        "Store": ["A", "B", "B"],
        "Item": ["NO NAME BACON 500 g", "NO NAME BACON 500 g", "MYSTERY ITEM"],
        "Price_Value": [4.99, 5.49, 1.0],
        "ai_normalized_name": ["Bacon", "NO NAME BACON 500 g", "MYSTERY ITEM"],
        "ai_category": ["Pork", "Other", "Other"],
        "ai_sub_category": ["Bacon", "General", "General"],
    })
    out, filled = backfill_classifications(df)
    assert filled == 1
    assert out.loc[1, "ai_normalized_name"] == "Bacon"
    assert out.loc[1, "ai_category"] == "Pork"
    assert out.loc[1, "ai_sub_category"] == "Bacon"
    assert out.loc[2, "ai_normalized_name"] == "MYSTERY ITEM"   # nothing trusted to copy


def test_archive_health_flags_missing_dates():
    from tools.repair_archive import archive_health

    good = pd.DataFrame({"Date": ["2026-09-09"] * 10, "Item": ["x"] * 10})
    assert archive_health(good)["ok"] is True

    bad = pd.DataFrame({"Date": ["2026-09-09"] * 5 + [None] * 5, "Item": ["x"] * 10})
    health = archive_health(bad)
    assert health["ok"] is False
    assert health["no_date"] == 5
    assert "date" in health["message"].lower()


def test_archive_health_tolerates_a_few_bad_rows():
    df = pd.DataFrame({"Date": ["2026-09-09"] * 199 + [None], "Item": ["x"] * 200})
    assert archive_health_ok(df)


def archive_health_ok(df):
    from tools.repair_archive import archive_health

    return archive_health(df)["ok"]
