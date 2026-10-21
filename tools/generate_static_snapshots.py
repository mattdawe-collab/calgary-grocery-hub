"""
Generate the public weekly page plus static deal snapshot pages.

This mirrors the FastAPI /share/deals/{id} route but writes plain HTML files so
the snapshots can be served from static hosts such as GitHub Pages.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.data import store
from api.routes.share import render_deal_snapshot_html
from tools.weekly_page import build_page_model, render_weekly_page


DEFAULT_OUTPUT = ROOT / "static_snapshots"


def _clean_output(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def generate(output_dir: Path, base_url: str) -> int:
    _clean_output(output_dir)
    store.load()

    count = 0
    deals_dir = output_dir / "share" / "deals"
    for deal_id in store.current.index:
        payload = store.get_deal_history(int(deal_id))
        if payload is None:
            continue
        page_dir = deals_dir / str(int(deal_id))
        page_dir.mkdir(parents=True, exist_ok=True)
        page = render_deal_snapshot_html(payload, base_url)
        (page_dir / "index.html").write_text(page, encoding="utf-8")
        count += 1

    _write_weekly_page(output_dir, base_url)
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    return count


def _write_weekly_page(output_dir: Path, base_url: str) -> None:
    """Root index.html = the public 'This Week's Deals' page (every deal, linked to its card)."""
    latest = None
    latest_path = ROOT / "reports" / "weekly_reports_latest.json"
    if latest_path.exists():
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Warning: could not read {latest_path.name}: {exc}")
    model = build_page_model(store.current, latest, base_url)
    (output_dir / "index.html").write_text(render_weekly_page(model), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate static deal snapshot pages.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--base-url",
        default="https://mattdawe-collab.github.io/calgary-grocery-hub/",
        help="Public base URL used by footer links.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/") + "/"
    count = generate(args.output_dir, base_url)
    print(f"Generated {count} snapshot page(s) in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
