# Calgary Grocery Hub

A local weekly grocery deal aggregator for Calgary. It pulls current flyer data
from Flipp, enriches items with AI/statistical scoring, maintains historical
price context, and serves a React dashboard through FastAPI.

## Current Shape

- Scraper: `get_deals.py`
- Report generator: `weekly_report_generator.py`
- Current data: `current_flyers.csv`
- Historical data: `historical_archive.csv`
- API and production server: `api/main.py`
- React dashboard source: `dashboard/src/`
- Legacy dashboard: `dashboard.py` (Streamlit)

The React dashboard is the revived default path. FastAPI serves both `/api/*`
and the built React app from `dashboard/dist/`.

## Quick Start

Install Python dependencies:

```powershell
cd "Z:\Weekly Deals"
python -m pip install -r requirements.txt
```

Install and build the React dashboard:

```powershell
cd "Z:\Weekly Deals\dashboard"
npm install
npm run build
```

Verify the install:

```powershell
cd "Z:\Weekly Deals"
python verify_installation.py
```

Start the dashboard:

```powershell
cd "Z:\Weekly Deals"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Open: `http://localhost:8000`

You can also double-click `start_dashboard.bat`; it starts the FastAPI server
from the current project folder and builds the React dashboard if `dist/` is
missing.

## Refresh Weekly Deals

The full weekly run is:

```powershell
cd "Z:\Weekly Deals"
python get_deals.py
python weekly_report_generator.py
```

For the existing Windows flow, run `rundeals.bat` or schedule
`rundeals_scheduled.bat`.

Notes:

- `POSTAL_CODE` comes from `.env`; default is `T3M1M9`.
- AI classification and the weekly write-ups run through the **Claude Code
  CLI** on this machine (your subscription, no per-token billing). See
  "AI backend" below.
- If no AI backend is available the scheduled run stops before publishing and
  alerts the private Telegram chat (`AI_REQUIRE_BACKEND=1`). Set it to `0` to
  allow a statistical-only run.

## AI backend

`ai_backends.py` picks a backend and, since 2026-10-21, **proves it answers**
before the run scrapes or publishes anything. Order (`AI_BACKEND=auto`):

1. `anthropic` - the Anthropic API, using `ANTHROPIC_API_KEY`. This is the
   primary because an API key does not expire. Scoring runs on
   `claude-sonnet-5-5`, the three write-ups on `claude-opus-5-5`.
2. `claude_code` - the local `claude` CLI, used when no API key is set or the
   key fails verification. Needs a one-time `claude login` as the Windows
   user that runs the scheduled task, and that login expires.
3. `statistical` - no model; keyword categories only. The chain refuses to
   publish on this unless `AI_REQUIRE_BACKEND=0`.

Why verification matters: an expired CLI login and an API key with no credit
balance both look healthy to anything that only reads environment variables.
Both have taken down a Wednesday run. Preflight now spends a few tokens on a
real round trip and names the exact problem.

```powershell
python ai_backends.py          # which backend would run, and why not the others
python verify_installation.py  # full preflight
```

Item names already classified in `historical_archive.csv` are reused without a
model call (`AI_NAME_CACHE=1`), and the three write-ups share one cached data
block, so only the first pays full price for it.

### Rough weekly cost on the API

About 35 scoring calls plus 3 write-ups per run. Estimated from this week's
flyer sizes, before prompt-cache savings:

| Pass | Model | Per week |
|---|---|---|
| Scoring (~1,400 items) | `claude-sonnet-5-5` | ~$1.00 |
| Scoring, cheaper option | `claude-haiku-5-5` | ~$0.05 |
| Three write-ups | `claude-opus-5-5` | ~$1.05 |

Caching the shared report data block cuts most of the write-up input cost
from the second report onward.

## Public weekly page

Each run publishes `static_snapshots/index.html` to the GitHub Pages root: a
"This Week's Deals" page with every deal, search and filters, and a link from
each row to its price-history card at `/share/deals/<id>/`. The Telegram
digests and the generated Facebook post (`weekly_post_FACEBOOK_*.txt`) link
to it. Regenerate locally with:

```powershell
python tools/generate_static_snapshots.py
```

## Environment

Copy `env.template` to `.env` and fill in the keys you want to use:

```dotenv
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
GEMINI_REPORT_MODEL=gemini-2.5-flash
POSTAL_CODE=T3M1M9
API_PORT=8000
STREAMLIT_PORT=8501
```

## Useful Commands

Build frontend:

```powershell
cd "Z:\Weekly Deals\dashboard"
npm run build
```

Run API locally:

```powershell
cd "Z:\Weekly Deals"
python -m uvicorn api.main:app --reload --port 8000
```

Run Vite dev server against the API:

```powershell
cd "Z:\Weekly Deals\dashboard"
npm run start
```

Check API data:

```powershell
Invoke-RestMethod http://localhost:8000/api/insights
```

Legacy Streamlit dashboard:

```powershell
streamlit run dashboard.py
```

Send a Telegram digest preview:

```powershell
python send_telegram_digest.py --dry-run
```

Send the Telegram digest for real:

```powershell
python send_telegram_digest.py
```

## Telegram Bot

1. Create a bot with Telegram's `@BotFather`.
2. Add `TELEGRAM_BOT_TOKEN` to `.env`.
3. Send any message to the bot from the Telegram chat you want to receive deals.
4. Run `python send_telegram_digest.py --get-updates`.
5. Copy the printed `chat_id` into `TELEGRAM_CHAT_ID` in `.env`.

Optional `.env` settings:

```dotenv
TELEGRAM_MIN_SCORE=80
TELEGRAM_DIGEST_LIMIT=12
TELEGRAM_STORE_FILTER=
TELEGRAM_CATEGORY_FILTER=
```

The weekly batch scripts call `send_telegram_digest.py --optional`, so they skip
Telegram cleanly until the token and chat ID are configured.

## Deployment

Railway uses:

- `Procfile`
- `railway.toml`
- `api/main.py`
- `dashboard/dist/`
- `current_flyers.csv`
- `historical_archive.csv`

`push_to_github.bat` stages the data CSVs and pushes to `main`. If Railway is
connected to GitHub, that push triggers the deploy.

## Data Files

`current_flyers.csv` contains the current scrape output, including deal scores,
AI categories, price basis, unit pricing, cross-store rank, and historical
comparison fields.

`historical_archive.csv` accumulates prior flyer observations and is used for
price history, lowest-ever detection, and recurring sale context.

## Troubleshooting

- Run `python verify_installation.py` first; it checks the current file layout,
  Python dependencies, data load, and local URLs.
- If `vite` is missing or the dashboard build fails, run `npm install` in
  `dashboard/`.
- If scripts crash on Windows console encoding, make sure you are using the
  revived entry points; they reconfigure stdout/stderr as UTF-8.
- If the dashboard loads but data looks stale, run the weekly refresh commands.
