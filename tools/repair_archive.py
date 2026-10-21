"""
One-off repair and ongoing hygiene for historical_archive.csv.

What it fixes
-------------
1. Missing Date cells. pandas 2.x inferred a single date format from the first
   row and coerced every other format to NaT, so 26,827 rows (May-Sep 2026)
   lost their Date. Anything without a Date is invisible to the 180-day
   history window, which is what made "usual price" thin. The scrape date is
   reconstructed from the flyer window: runs happen the Wednesday before a
   Thursday flyer start, so Date = Valid_From - 1 day (falling back to
   Valid_Until - 6 days).
2. Mixed on-disk date formats, normalized to plain YYYY-MM-DD.
3. Duplicate rows: the same store/item/price on the same day.
4. Classifications lost to the Jun-Sep 2026 AI outage, backfilled from the
   same item name's trusted classification elsewhere in the archive.

Usage
-----
    python tools/repair_archive.py --dry-run     # report only, writes nothing
    python tools/repair_archive.py               # repair, backup first
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_quality import normalize_archive_dates, parse_dates

ARCHIVE = ROOT / "historical_archive.csv"
BACKUP_DIR = ROOT / "archive" / "old_csvs"

KEY_COLUMNS = ["Date", "Store", "Item", "Price_Value"]


def _norm_text(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().str.replace(r"\s+", " ", regex=True)


def repair_dates(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Fill missing Date from the flyer window; return (df, stats).

    Dates come back as plain YYYY-MM-DD strings so the file has one format.
    """
    out = df.copy()
    dates = parse_dates(out["Date"]) if "Date" in out.columns else pd.Series(pd.NaT, index=out.index)
    missing_before = int(dates.isna().sum())

    valid_from = parse_dates(out["Valid_From"]) if "Valid_From" in out.columns else pd.Series(pd.NaT, index=out.index)
    valid_until = parse_dates(out["Valid_Until"]) if "Valid_Until" in out.columns else pd.Series(pd.NaT, index=out.index)

    # Scrape runs the day before the flyer starts; otherwise 6 days before it ends.
    rebuilt = (valid_from - pd.Timedelta(days=1)).fillna(valid_until - pd.Timedelta(days=6))
    dates = dates.fillna(rebuilt)

    out["Date"] = dates.dt.strftime("%Y-%m-%d").where(dates.notna())
    stats = {
        "missing_before": missing_before,
        "reconstructed": missing_before - int(dates.isna().sum()),
        "still_missing": int(dates.isna().sum()),
    }
    return out, stats


def dedupe_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop repeat scrapes of the same flyer line (same day/store/item/price)."""
    if not set(KEY_COLUMNS).issubset(df.columns):
        return df, 0
    key = pd.DataFrame({
        "d": parse_dates(df["Date"]).dt.strftime("%Y-%m-%d").fillna("nodate"),
        "s": _norm_text(df["Store"]),
        "i": _norm_text(df["Item"]),
        "p": pd.to_numeric(df["Price_Value"], errors="coerce").round(2).astype(str),
    })
    keep = ~key.duplicated(keep="last")     # newest row for a given line wins
    return df[keep].copy(), int((~keep).sum())


def _trusted_mask(df: pd.DataFrame) -> pd.Series:
    """Rows whose AI columns came from a model, not the statistical fallback."""
    norm = _norm_text(df["ai_normalized_name"])
    item = _norm_text(df["Item"])
    sub = df["ai_sub_category"].astype(str).str.strip()
    cat = df["ai_category"].astype(str).str.strip()
    return (
        df["ai_normalized_name"].notna()
        & (norm != "")
        & (norm != item)
        & (sub != "") & (sub != "General") & (sub != "nan")
        & (cat != "") & (cat != "Other") & (cat != "nan")
    )


def backfill_classifications(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Copy a trusted classification onto untrusted rows with the same item name."""
    needed = {"Item", "ai_normalized_name", "ai_category", "ai_sub_category"}
    if not needed.issubset(df.columns):
        return df, 0

    out = df.copy()
    trusted = _trusted_mask(out)
    if not trusted.any():
        return out, 0

    keys = _norm_text(out["Item"])
    lookup = (
        out.loc[trusted, ["ai_normalized_name", "ai_category", "ai_sub_category"]]
        .assign(_k=keys[trusted])
        .drop_duplicates("_k", keep="last")
        .set_index("_k")
    )

    fill = (~trusted) & keys.isin(lookup.index)
    if not fill.any():
        return out, 0

    source = lookup.reindex(keys[fill])
    for column in ("ai_normalized_name", "ai_category", "ai_sub_category"):
        out.loc[fill, column] = source[column].to_numpy()
    return out, int(fill.sum())


MAX_UNDATED_SHARE = 0.01


def archive_health(df: pd.DataFrame) -> dict:
    """Cheap check that the archive is still usable for history lookups.

    A row without a Date is invisible to the 180-day window, so a batch of
    them quietly thins "usual price" instead of failing loudly. That is
    exactly how the May-Sep 2026 gap went unnoticed for four months.
    """
    if df is None or len(df) == 0:
        return {"ok": False, "rows": 0, "no_date": 0, "message": "archive is empty"}
    no_date = int(parse_dates(df["Date"]).isna().sum()) if "Date" in df.columns else len(df)
    share = no_date / len(df)
    ok = share <= MAX_UNDATED_SHARE
    message = (
        ""
        if ok
        else (
            f"{no_date:,} of {len(df):,} archive rows ({share:.1%}) have no usable Date and "
            f"are excluded from price history. Run: python tools/repair_archive.py"
        )
    )
    return {"ok": ok, "rows": len(df), "no_date": no_date, "share": share, "message": message}


def summarize(df: pd.DataFrame, label: str) -> dict:
    dates = parse_dates(df["Date"])
    trusted = _trusted_mask(df) if {"ai_normalized_name", "ai_category", "ai_sub_category"}.issubset(df.columns) else pd.Series(False, index=df.index)
    within_180 = int((dates >= (pd.Timestamp.now() - pd.Timedelta(days=180))).sum())
    print(
        f"{label}: {len(df):,} rows | no Date {int(dates.isna().sum()):,} | "
        f"in 180-day window {within_180:,} | trusted classifications {int(trusted.sum()):,}"
    )
    return {"rows": len(df), "no_date": int(dates.isna().sum()), "within_180": within_180}


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair historical_archive.csv.")
    parser.add_argument("--dry-run", action="store_true", help="Report only; write nothing.")
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    args = parser.parse_args()

    if not args.archive.exists():
        print(f"ERROR: {args.archive} not found", file=sys.stderr)
        return 1

    df = pd.read_csv(args.archive, low_memory=False)
    before = summarize(df, "before")
    rows_in = len(df)

    df, date_stats = repair_dates(df)
    print(f"  dates: {date_stats['reconstructed']:,} reconstructed, {date_stats['still_missing']:,} still missing")

    df, removed = dedupe_rows(df)
    print(f"  duplicates removed: {removed:,}")

    df, filled = backfill_classifications(df)
    print(f"  classifications backfilled: {filled:,}")

    df = normalize_archive_dates(df)
    after = summarize(df, "after")

    if len(df) > rows_in:
        print("ERROR: repair added rows; refusing to write", file=sys.stderr)
        return 1

    if args.dry_run:
        print("\nDry run: nothing written.")
        return 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"historical_archive_prerepair_{stamp}.csv"
    shutil.copy2(args.archive, backup)
    print(f"\nBackup: {backup}")

    temp = args.archive.with_suffix(".csv.tmp")
    df.to_csv(temp, index=False)
    temp.replace(args.archive)
    print(f"Wrote {args.archive} ({after['rows']:,} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
