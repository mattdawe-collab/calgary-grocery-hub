"""
Run the public Calgary Grocery Hub publication chain.

Order matters:
0. Preflight: an AI backend must be available (Claude CLI logged in), or the
   run stops and alerts the private Telegram chat before anything is published.
1. Refresh deal data.
2. Generate weekly reports (store, category, Facebook post).
3. Commit and push data CSVs to main.
4. Rebuild and publish the weekly page + snapshot cards to GitHub Pages.
5. Verify a live snapshot card.
6. Send Telegram only after the public links are live.
7. Send a short success/failure summary to the private alert chat.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

from ai_backends import select_backend, usable_backend
from tools.generate_static_snapshots import DEFAULT_OUTPUT, generate

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)


class ChainError(RuntimeError):
    pass


def preflight_ai_backend() -> str:
    """Prove an AI backend answers before anything is scraped or published.

    Three months of silently degraded runs (Jun-Sep 2026) is why this exists,
    and 2026-10-21 is why it now *verifies* instead of reading the
    environment: an expired CLI login and an API key with no credit balance
    both look fine until the first real call. Set AI_REQUIRE_BACKEND=0 to
    allow a statistical-only run.
    """
    backend = usable_backend(verbose=True)
    if backend["type"] == "statistical" and _config("AI_REQUIRE_BACKEND", "1") != "0":
        tried = "; ".join(
            f"{a['backend']}: {a['reason']}" for a in backend.get("attempts", []) if not a["ok"]
        ) or backend["reason"]
        raise ChainError(
            "No AI backend answered, stopping before anything is published. "
            f"Tried - {tried}. (Set AI_REQUIRE_BACKEND=0 to run statistical-only.)"
        )
    return backend["type"]


def send_alert(text: str, post=requests.post) -> bool:
    """Send an ops message to the PRIVATE alert chat (never the public channel)."""
    token = _config("TELEGRAM_BOT_TOKEN")
    chat_id = _config("TELEGRAM_ALERT_CHAT_ID")
    if not token or not chat_id:
        print("[alert skipped] TELEGRAM_ALERT_CHAT_ID (private chat) and TELEGRAM_BOT_TOKEN are needed for ops alerts.")
        print(f"[alert text] {text}")
        return False
    try:
        response = post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True},
            timeout=30,
        )
        response.raise_for_status()
        return bool(response.json().get("ok"))
    except Exception as exc:  # alerting must never mask the real failure
        print(f"[alert failed] {exc}")
        return False


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def load_env_file_into_environ(path: Path) -> None:
    """Make .env visible to this process, not just to its subprocesses.

    The chain runs the AI preflight in-process. It used to merge .env only
    into the environment handed to child processes, so the preflight read
    os.environ, found no ANTHROPIC_API_KEY, and stopped the run with the key
    sitting in .env the whole time. setdefault keeps a real environment
    variable winning over the file.
    """
    for key, value in _load_env_file(path).items():
        os.environ.setdefault(key, value)


ENV_FILE_VALUES = _load_env_file(ROOT / ".env")
load_env_file_into_environ(ROOT / ".env")


def _config(name: str, default: str = "") -> str:
    return os.environ.get(name) or ENV_FILE_VALUES.get(name) or default


def _subprocess_env(base_url: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for key, value in ENV_FILE_VALUES.items():
        env.setdefault(key, value)
    if base_url:
        env["PUBLIC_DASHBOARD_URL"] = base_url.rstrip("/")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def _format_cmd(cmd: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in cmd)


def run_step(name: str, cmd: list[str], env: dict[str, str] | None = None, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    print(f"\n== {name} ==")
    print(f"$ {_format_cmd(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=env, text=True)
    if result.returncode != 0:
        raise ChainError(f"{name} failed with exit code {result.returncode}")
    return result


def git_output(args: list[str], cwd: Path = ROOT) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise ChainError(f"git {' '.join(args)} failed: {message}")
    return result.stdout.strip()


def git_quiet(args: list[str], cwd: Path = ROOT) -> int:
    return subprocess.run(["git", *args], cwd=cwd).returncode


def remote_url() -> str:
    return _config("PUBLICATION_GIT_REMOTE") or git_output(["remote", "get-url", "origin"])


def github_pages_url(remote: str) -> str:
    configured = _config("PUBLIC_DASHBOARD_URL") or _config("DASHBOARD_PUBLIC_URL")
    if configured:
        return configured.rstrip("/")

    match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$", remote)
    if not match:
        raise ChainError("Could not infer GitHub Pages URL. Set PUBLIC_DASHBOARD_URL in .env.")
    return f"https://{match.group('owner')}.github.io/{match.group('repo')}"


def ensure_no_staged_changes() -> None:
    if git_quiet(["diff", "--cached", "--quiet"]) != 0:
        raise ChainError("Refusing to continue because git already has staged changes.")


def commit_and_push_data(push_ref: str) -> bool:
    ensure_no_staged_changes()
    run_step("Stage data files", ["git", "add", "current_flyers.csv", "historical_archive.csv"])

    if git_quiet(["diff", "--cached", "--quiet"]) == 0:
        print("No data changes to commit.")
        return False

    datestamp = datetime.now().strftime("%Y-%m-%d")
    run_step("Commit data files", ["git", "commit", "-m", f"Update deal data {datestamp}"])
    run_step("Push data to main", ["git", "push", "origin", push_ref])
    return True


def publish_snapshots(output_dir: Path, remote: str) -> None:
    publish_dir = Path(tempfile.mkdtemp(prefix="calgary-grocery-gh-pages-")).resolve()
    try:
        for item in output_dir.iterdir():
            destination = publish_dir / item.name
            if item.is_dir():
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)

        run_step("Initialize gh-pages worktree", ["git", "init", "-q"], cwd=publish_dir)
        run_step("Create gh-pages branch", ["git", "checkout", "-b", "gh-pages"], cwd=publish_dir)
        run_step("Stage snapshot site", ["git", "add", "-A"], cwd=publish_dir)
        run_step("Commit snapshot site", ["git", "commit", "-m", "Publish static deal snapshots"], cwd=publish_dir)
        run_step("Set gh-pages remote", ["git", "remote", "add", "origin", remote], cwd=publish_dir)
        run_step("Push snapshot site", ["git", "push", "--force", "origin", "gh-pages"], cwd=publish_dir)
    finally:
        shutil.rmtree(publish_dir, ignore_errors=True)


def first_snapshot_id(output_dir: Path, requested_id: str | None = None) -> str:
    deals_dir = output_dir / "share" / "deals"
    if requested_id and (deals_dir / requested_id / "index.html").exists():
        return requested_id
    ids = sorted(
        (path.name for path in deals_dir.iterdir() if path.is_dir()),
        key=lambda value: int(value) if value.isdigit() else value,
    )
    if not ids:
        raise ChainError("No generated snapshot pages found to verify.")
    return ids[0]


def verify_live_snapshot(base_url: str, deal_id: str, marker: str, timeout_seconds: int, interval_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    url = f"{base_url.rstrip('/')}/share/deals/{deal_id}/"
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        cache_buster = f"{url}?v={int(time.time())}"
        try:
            request = Request(cache_buster, headers={"Cache-Control": "no-cache", "User-Agent": "CalgaryGroceryHubPublisher/1.0"})
            with urlopen(request, timeout=20) as response:
                body = response.read().decode("utf-8", errors="replace")
                if response.status == 200 and marker in body:
                    print(f"Verified live snapshot on attempt {attempt}: {url}")
                    return
                print(f"Snapshot attempt {attempt}: HTTP {response.status}, marker not found yet.")
        except HTTPError as exc:
            print(f"Snapshot attempt {attempt}: HTTP {exc.code}, waiting.")
        except URLError as exc:
            print(f"Snapshot attempt {attempt}: {exc.reason}, waiting.")
        time.sleep(interval_seconds)
    raise ChainError(f"Timed out waiting for live snapshot marker at {url}")


def telegram_groups(args: argparse.Namespace) -> list[str | None]:
    if args.telegram_main:
        groups: list[str | None] = [None]
    else:
        groups = []

    configured_groups = args.telegram_group
    if configured_groups is None:
        raw = _config("PUBLICATION_TELEGRAM_GROUPS", "proteins,vegetables,pantry_others")
        configured_groups = [part.strip() for part in raw.split(",") if part.strip()]

    for group in configured_groups:
        groups.append(None if group.lower() == "main" else group)
    return groups


def send_telegram_messages(args: argparse.Namespace, base_url: str) -> None:
    groups = telegram_groups(args)
    if not groups:
        print("No Telegram groups configured; skipping Telegram send.")
        return

    env = _subprocess_env(base_url)
    for group in groups:
        label = "main digest" if group is None else f"{group} digest"
        cmd = [sys.executable, "send_telegram_digest.py", "--optional"]
        if group is not None:
            cmd.extend(["--group", group])
        if args.dry_run_telegram:
            cmd.append("--dry-run")
        run_step(f"Send Telegram {label}", cmd, env=env)



def run_summary(base_url: str, elapsed_minutes: int, backend: str = "") -> str:
    """Build the post-run Telegram alert.

    "Complete" on its own is what let three months of degraded runs pass
    unnoticed, so the alert carries the numbers that say whether the run was
    any good: how many deals, how many worth a trip, and how the scoring was
    actually produced.
    """
    lines = [f"\u2705 Calgary Grocery Hub - run complete in {elapsed_minutes} min"]
    if backend:
        lines.append(f"Backend: {backend}")
    warnings: list[str] = []

    try:
        import pandas as pd

        from data_quality import parse_dates

        deals = pd.read_csv(ROOT / "current_flyers.csv", low_memory=False)
        scores = pd.to_numeric(deals.get("deal_score"), errors="coerce").fillna(0)
        strong = int((scores >= 80).sum())

        start = parse_dates(deals["Valid_From"]).dropna() if "Valid_From" in deals else None
        end = parse_dates(deals["Valid_Until"]).dropna() if "Valid_Until" in deals else None
        if start is not None and len(start) and end is not None and len(end):
            lines.append(
                f"Week: {start.dt.strftime('%Y-%m-%d').mode().iloc[0]} to "
                f"{end.dt.strftime('%Y-%m-%d').mode().iloc[0]}"
            )
        lines.append(f"{len(deals):,} deals - {strong:,} worth a trip (80+)")

        confidence = deals.get("ai_confidence")
        if confidence is not None:
            confidence = confidence.astype(str)
            model = int(confidence.isin(["claude_code", "gemini", "anthropic", "claude"]).sum())
            cached = int((confidence == "cached").sum())
            fallback = int((confidence == "statistical").sum())
            lines.append(f"Scoring: {model:,} model / {cached:,} cached / {fallback:,} fallback")
            if len(deals) and fallback / len(deals) > 0.10:
                warnings.append(
                    f"WARNING: {fallback / len(deals):.0%} of items fell back to statistical scoring. "
                    "Check `claude auth status`."
                )
        if len(deals) and strong / len(deals) < 0.02:
            warnings.append("WARNING: almost nothing scored 80+. Check the history archive.")
    except Exception as exc:  # the alert must never break the run
        warnings.append(f"(could not summarise deal data: {exc})")

    lines.extend(warnings)
    lines.append(f"{base_url.rstrip('/')}/")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Calgary Grocery Hub public publication chain.")
    parser.add_argument("--skip-ai-preflight", action="store_true", help="Do not require an AI backend before running.")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip get_deals.py.")
    parser.add_argument("--skip-reports", action="store_true", help="Skip weekly_report_generator.py.")
    parser.add_argument("--skip-data-push", action="store_true", help="Skip committing and pushing CSV data.")
    parser.add_argument("--skip-snapshot-publish", action="store_true", help="Generate snapshots but do not push gh-pages.")
    parser.add_argument("--skip-telegram", action="store_true", help="Skip Telegram sends.")
    parser.add_argument("--dry-run-telegram", action="store_true", help="Print Telegram messages instead of sending.")
    parser.add_argument("--telegram-main", action="store_true", help="Also send the unfiltered main digest.")
    parser.add_argument("--telegram-group", action="append", help="Telegram category group to send. Defaults to PUBLICATION_TELEGRAM_GROUPS or proteins,vegetables,pantry_others.")
    parser.add_argument("--base-url", help="Public base URL for Telegram snapshot links.")
    parser.add_argument("--push-ref", default=_config("PUBLICATION_PUSH_REF", "HEAD:main"), help="Git refspec for data pushes.")
    parser.add_argument("--verify-deal-id", help="Specific deal id to verify on the public snapshot site.")
    parser.add_argument("--verify-marker", default="price-chart", help="HTML marker required before Telegram sends.")
    parser.add_argument("--pages-timeout", type=int, default=int(_config("PUBLICATION_PAGES_TIMEOUT", "300")))
    parser.add_argument("--pages-check-interval", type=int, default=int(_config("PUBLICATION_PAGES_CHECK_INTERVAL", "10")))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    remote = remote_url()
    base_url = (args.base_url or github_pages_url(remote)).rstrip("/")
    env = _subprocess_env(base_url)

    print("Calgary Grocery Hub publication chain")
    print(f"Project: {ROOT}")
    print(f"Public snapshot base: {base_url}")

    started = datetime.now()
    try:
        backend_used = ""
        if not getattr(args, "skip_ai_preflight", False):
            print("\n== Preflight: AI backend ==")
            backend_used = preflight_ai_backend()
            print(f"AI backend ready: {backend_used}")

        if not args.skip_scrape:
            run_step("Refresh flyer data", [sys.executable, "get_deals.py"], env=env)
        if not args.skip_reports:
            run_step("Generate weekly reports", [sys.executable, "weekly_report_generator.py"], env=env)
        if not args.skip_data_push:
            commit_and_push_data(args.push_ref)

        print("\n== Generate static snapshots ==")
        count = generate(args.output_dir, base_url + "/")
        print(f"Generated {count} snapshot page(s) in {args.output_dir}")

        verify_id = first_snapshot_id(args.output_dir, args.verify_deal_id)
        if not args.skip_snapshot_publish:
            publish_snapshots(args.output_dir, remote)
            verify_live_snapshot(base_url, verify_id, args.verify_marker, args.pages_timeout, args.pages_check_interval)
        else:
            print("Skipping gh-pages publish and live verification.")

        if not args.skip_telegram:
            if args.skip_snapshot_publish and not args.dry_run_telegram:
                raise ChainError("Refusing to send Telegram because snapshot publishing was skipped.")
            send_telegram_messages(args, base_url)
        else:
            print("Skipping Telegram send.")

    except Exception as exc:
        traceback.print_exc()
        print(f"\nERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        send_alert(f"\u274c Calgary Grocery Hub weekly run FAILED\n{exc}\n\nProject: {ROOT}")
        return 1

    elapsed = datetime.now() - started
    print("\nPublication chain complete.")
    summary = run_summary(base_url, int(elapsed.total_seconds() // 60), backend=backend_used)
    print(summary)
    if _config("TELEGRAM_ALERT_ON_SUCCESS", "1") != "0":
        send_alert(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
