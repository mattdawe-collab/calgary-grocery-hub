import pandas as pd
from api.data import DataStore, modal_datetime


def test_mixed_offsets_preserve_flyer_calendar_dates():
    dates = pd.Series(["2026-10-21T23:59:59-04:00"] * 2 +
                      ["2026-12-23T23:59:59-05:00", "invalid"])
    assert modal_datetime(dates).date().isoformat() == "2026-10-21"


def test_insights_support_mixed_offsets_and_formats():
    store = DataStore()
    store.current = pd.DataFrame({
        "Store": ["A", "A", "B"], "deal_score": [80., 90., 70.],
        "Valid_From": ["2026-10-15", "2026-10-15T03:00:00-04:00", "2026-11-01T00:00:00-05:00"],
        "Valid_Until": ["2026-10-21T23:59:59-04:00"] * 2 + ["2026-12-23T23:59:59-05:00"],
    })
    result = store._compute_insights()
    assert result["valid_from"].startswith("2026-10-15")
    assert result["valid_until"].startswith("2026-10-21")
    assert result["valid_until_max"].startswith("2026-12-23")
    assert result["extended_flyer_count"] == 1
