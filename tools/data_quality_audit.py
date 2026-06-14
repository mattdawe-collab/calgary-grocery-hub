"""
Generate a data-quality audit for the current flyer CSV.

This is read-only for source data: it loads current_flyers.csv, applies the
shared quality rules in memory, and writes a timestamped Markdown report under
archive/data_quality_audits/.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_quality import (
    add_quality_metadata,
    filter_grocery_relevant,
    repair_category,
    sanitize_unit_prices,
)


CURRENT_FLYERS = ROOT / "current_flyers.csv"
AUDIT_DIR = ROOT / "archive" / "data_quality_audits"


def _value_counts(series: pd.Series, limit: int = 12) -> list[tuple[str, int]]:
    counts = series.fillna("").astype(str).value_counts().head(limit)
    return [(str(k), int(v)) for k, v in counts.items()]


def _flag_counts(series: pd.Series) -> dict[str, int]:
    counts: dict[str, int] = {}
    for flags in series.fillna("").astype(str):
        for flag in [part.strip() for part in flags.split(";") if part.strip()]:
            counts[flag] = counts.get(flag, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def build_audit(csv_path: Path = CURRENT_FLYERS) -> tuple[str, pd.DataFrame]:
    df = pd.read_csv(csv_path, low_memory=False)
    original_rows = len(df)

    cleaned, excluded = filter_grocery_relevant(df)
    cleaned, unit_issue_count = sanitize_unit_prices(cleaned)

    categories = cleaned.apply(
        lambda row: repair_category(row.get("Item", ""), row.get("ai_category", "Other")),
        axis=1,
        result_type="expand",
    )
    cleaned["display_category"] = categories[0]
    cleaned["category_source"] = categories[1]
    cleaned = add_quality_metadata(cleaned)

    original_other = int((df.get("ai_category", pd.Series(dtype=str)).astype(str) == "Other").sum())
    cleaned_other = int((cleaned["display_category"].astype(str) == "Other").sum())
    corrected = int((cleaned["category_source"].astype(str) == "corrected").sum())
    inferred = int((cleaned["category_source"].astype(str) == "inferred").sum())
    avg_quality = round(float(cleaned["data_quality_score"].mean()), 1) if len(cleaned) else 0

    lines = [
        "# Data Quality Audit",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Source: `{csv_path.name}`",
        f"- Source rows: {original_rows:,}",
        f"- Dashboard/report rows after grocery filter: {len(cleaned):,}",
        f"- Non-grocery/general-merchandise rows excluded: {len(excluded):,}",
        f"- Suspicious unit prices cleared: {unit_issue_count:,}",
        f"- Raw `Other` categories: {original_other:,}",
        f"- Display `Other` categories after repair: {cleaned_other:,}",
        f"- Corrected categories: {corrected:,}",
        f"- Inferred categories: {inferred:,}",
        f"- Average data quality score: {avg_quality}",
        "",
        "## Category Counts",
        "",
    ]

    for category, count in _value_counts(cleaned["display_category"]):
        lines.append(f"- {category}: {count:,}")

    lines.extend(["", "## Quality Flags", ""])
    flags = _flag_counts(cleaned["quality_flags"])
    if flags:
        for flag, count in flags.items():
            lines.append(f"- {flag}: {count:,}")
    else:
        lines.append("- None")

    lines.extend(["", "## Excluded Samples", ""])
    if len(excluded):
        for _, row in excluded[["Store", "Item", "Price_Value"]].head(30).iterrows():
            lines.append(f"- {row.get('Store', '')}: {row.get('Item', '')} (${row.get('Price_Value', '')})")
    else:
        lines.append("- None")

    lines.extend(["", "## Top Clean Deals", ""])
    score_col = "deal_score" if "deal_score" in cleaned.columns else "ai_deal_score"
    if score_col in cleaned.columns and len(cleaned):
        top = cleaned.sort_values(score_col, ascending=False).head(20)
        for _, row in top.iterrows():
            lines.append(
                "- "
                f"{row.get('Store', '')}: {row.get('Item', '')} "
                f"(${row.get('Price_Value', '')}) "
                f"score {row.get(score_col, '')} "
                f"[{row.get('display_category', '')}]"
            )
    else:
        lines.append("- No scored rows found")

    return "\n".join(lines) + "\n", cleaned


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a current flyer data-quality audit.")
    parser.add_argument("--csv", type=Path, default=CURRENT_FLYERS)
    parser.add_argument("--out-dir", type=Path, default=AUDIT_DIR)
    args = parser.parse_args()

    report, _ = build_audit(args.csv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"QUALITY_AUDIT_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path.write_text(report, encoding="utf-8")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
