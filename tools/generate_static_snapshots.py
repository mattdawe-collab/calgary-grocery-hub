"""
Generate static deal snapshot pages for public Telegram links.

This mirrors the FastAPI /share/deals/{id} route but writes plain HTML files so
the snapshots can be served from static hosts such as GitHub Pages.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.data import store
from api.routes.share import render_deal_snapshot_html


DEFAULT_OUTPUT = ROOT / "static_snapshots"


def _clean_output(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def _write_index(output_dir: Path, base_url: str, count: int) -> None:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Calgary Grocery Hub Snapshots</title>
  <style>
    body {{
      margin: 0;
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f8fafc;
      color: #0f172a;
    }}
    main {{
      max-width: 680px;
      margin: 0 auto;
      padding: 28px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 28px;
    }}
    p {{
      color: #475569;
      line-height: 1.5;
    }}
  </style>
</head>
<body>
  <main>
    <h1>Calgary Grocery Hub Snapshots</h1>
    <p>{count:,} current deal snapshot pages generated {escape(generated)}.</p>
    <p>Telegram deal links open individual <code>/share/deals/&lt;id&gt;</code> pages from this static site.</p>
    <p>Base URL: <a href="{escape(base_url)}">{escape(base_url)}</a></p>
  </main>
</body>
</html>"""
    (output_dir / "index.html").write_text(html, encoding="utf-8")
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")


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

    _write_index(output_dir, base_url, count)
    return count


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
