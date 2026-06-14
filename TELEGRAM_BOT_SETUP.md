# Public Telegram Bot Setup

This guide sets up the Calgary Grocery Hub Telegram digest for public use.

The current bot integration is broadcast-only: `send_telegram_digest.py` sends
the weekly deal message to one configured chat. It does not yet handle public
commands, subscriptions, replies, moderation, or per-user preferences.

## Recommended Public Setup

Use a public Telegram channel as the public surface, and add the bot as a
posting admin.

This is safer than launching directly into a public group because:

- only admins can post;
- subscribers can follow/share without creating moderation work;
- the bot does not need to read user messages;
- one scheduled digest reaches everyone;
- the bot token remains server-side in `.env`.

Use a public group only after you add inbound command handling, moderation
rules, spam controls, and rate limits.

## Create The Bot

1. Open Telegram and message `@BotFather`.
2. Run `/newbot`.
3. Choose a public display name, for example `Calgary Grocery Deals`.
4. Choose a username ending in `bot`, for example `CalgaryDealsBot`.
5. Copy the token into `.env` as `TELEGRAM_BOT_TOKEN`.

Treat the token like a password. Anyone with the token can control the bot. If
it is ever exposed, use BotFather's `/token` flow to rotate it and update `.env`.

## Public Profile Checklist

Use BotFather to make the bot look trustworthy before sharing it:

- `/setdescription`: short first-run explanation.
- `/setabouttext`: one-line profile summary.
- `/setuserpic`: recognizable logo or simple grocery/deals image.
- `/setcommands`: only add commands that actually work.

Suggested description:

```text
Weekly Calgary grocery deal picks with score, confidence, and why-it-matters notes. Broadcast-only for now.
```

Suggested about text:

```text
Calgary grocery deals, stock-up picks, and weekly shopping guidance.
```

Do not advertise `/start`, `/help`, alerts, subscriptions, or personal lists
until the code supports them.

## Create The Public Channel

1. Create a Telegram channel.
2. Give it a clear public name, for example `Calgary Grocery Deals`.
3. Set a public username, for example `@CalgaryGroceryDeals`.
4. Add the bot as an administrator.
5. Give the bot only the permission it needs: posting messages.

For a public channel, set:

```dotenv
TELEGRAM_CHAT_ID=@CalgaryGroceryDeals
```

For a private channel or group, add the bot, post a test message in that chat,
then run:

```powershell
python send_telegram_digest.py --get-updates
```

Copy the printed `chat_id` into `.env`.

## Configure `.env`

Minimum public-channel configuration:

```dotenv
TELEGRAM_BOT_TOKEN=123456789:replace_with_real_token
TELEGRAM_CHAT_ID=@CalgaryGroceryDeals
TELEGRAM_MIN_SCORE=80
TELEGRAM_DIGEST_LIMIT=12
TELEGRAM_STORE_FILTER=
TELEGRAM_CATEGORY_FILTER=
```

Recommended defaults for public launch:

- `TELEGRAM_MIN_SCORE=80`: keeps the public digest focused.
- `TELEGRAM_DIGEST_LIMIT=12`: keeps the message readable and under Telegram's
  message length limit.
- leave store/category filters blank for the main public channel.
- create separate channels later if you want store-specific or category-specific
  feeds.

## Test Privately First

Before posting publicly, send the dry-run to your console:

```powershell
python send_telegram_digest.py --dry-run --limit 12 --min-score 80
```

Check that:

- the flyer dates are correct;
- the message has `Stock up`, `Buy this week`, and `Compare first` sections;
- the top items are actually grocery-relevant;
- prices and unit prices look sane;
- no test/private wording appears;
- the output is under one Telegram message.

Then create a private test channel, add the bot as admin, set
`TELEGRAM_CHAT_ID` to that test channel, and run:

```powershell
python send_telegram_digest.py
```

Only switch `TELEGRAM_CHAT_ID` to the public channel after the test post looks
right.

## Publish The Weekly Digest

Manual public send:

```powershell
python send_telegram_digest.py
```

Focused protein digest:

```powershell
python send_telegram_digest.py --group proteins
```

Quiet send without notification sound:

```powershell
python send_telegram_digest.py --silent
```

Scheduled weekly run:

```powershell
python get_deals.py
python weekly_report_generator.py
python send_telegram_digest.py --optional
```

The `--optional` flag lets scheduled jobs skip Telegram cleanly if the token or
chat ID is missing.

## Public-Facing Safety Rules

- Never commit `.env`, bot tokens, or real chat IDs that identify private chats.
- Keep the bot as a channel poster, not a broad group admin.
- Use a separate test bot and test channel for experiments.
- Do not disable group privacy mode unless the bot genuinely needs to read all
  group messages.
- Do not enable public group usage until inbound spam/rate-limit handling exists.
- Rotate the token immediately if it appears in logs, screenshots, commits, or
  chat.
- Keep public messages short, factual, and caveated as deal guidance, not
  guarantees.

## What The Current Digest Sends

The digest is optimized for a public audience:

- total grocery items and count above the score threshold;
- action counts for `Stock up`, `Buy this week`, and `Compare first`;
- best store stops by actionable picks;
- compact sections by action;
- score and confidence, shown as `S90/C68`;
- 1-2 evidence bullets per item, such as `Lowest seen` or `70% below avg`.

Example:

```text
* Stock up: $0.64 Corn @ Walmart (S100/C88) - 90% below avg $6.08; Lowest seen
```

## Future Interactive Bot Work

Do not treat the public bot as interactive until these are implemented:

- `/start` and `/help` handlers;
- opt-in subscription flow;
- per-user store/category preferences;
- spam/rate limits;
- allowlist/admin controls;
- safe error handling for malformed updates;
- webhook or polling worker supervision;
- logging that excludes tokens and private user content.

Until then, the public channel is the right launch path.

## References

- Telegram Bot tutorial: https://core.telegram.org/bots/tutorial
- Telegram Bot features and privacy mode: https://core.telegram.org/bots/features
