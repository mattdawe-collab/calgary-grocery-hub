# Calgary Grocery Hub Publication Chain

Use this chain for the public Telegram bot. It makes sure Telegram links are live
before a message is posted.

## Scheduled Flow

The existing Windows task `Calgary Grocery Hub Weekly` runs every Wednesday at
8:00 AM and points at `rundeals_scheduled.bat`.

That batch should call:

```bat
python tools\run_publication_chain.py
```

The chain runs in this order:

1. `get_deals.py` refreshes `current_flyers.csv` and `historical_archive.csv`.
2. `weekly_report_generator.py` creates the weekly text reports.
3. Updated data CSVs are committed and pushed to `main`.
4. Static snapshot cards are rebuilt under `static_snapshots\`.
5. The snapshot site is force-published to the `gh-pages` branch.
6. A live GitHub Pages card is verified for the `price-chart` marker.
7. Telegram sends only after the public card check passes.

By default, Telegram sends three public messages:

1. Proteins, with whole raw base proteins first and prepared proteins last.
2. Vegetables.
3. Pantry and other grocery items.

Each category has its own default item limit so it should fit in one Telegram
message. Override with `TELEGRAM_PROTEINS_LIMIT`,
`TELEGRAM_VEGETABLES_LIMIT`, or `TELEGRAM_PANTRY_OTHERS_LIMIT` only if you are
comfortable with Telegram splitting a category into multiple messages.

## Environment

Required in `.env`:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=@CalgaryGroceryDeals
PUBLIC_DASHBOARD_URL=https://mattdawe-collab.github.io/calgary-grocery-hub
PUBLICATION_TELEGRAM_GROUPS=proteins,vegetables,pantry_others
```

Optional:

```env
PUBLICATION_PUSH_REF=HEAD:main
PUBLICATION_PAGES_TIMEOUT=300
PUBLICATION_PAGES_CHECK_INTERVAL=10
```

## Test Without Posting

```bat
python tools\run_publication_chain.py --skip-scrape --skip-reports --skip-data-push --skip-snapshot-publish --skip-telegram
python tools\run_publication_chain.py --skip-scrape --skip-reports --skip-data-push --skip-snapshot-publish --dry-run-telegram
```

The second command prints the Telegram digest without sending it. Real Telegram
sends still require a successful snapshot publish and live verification.
