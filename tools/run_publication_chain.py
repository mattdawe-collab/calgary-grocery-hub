"""
Run the public Calgary Grocery Hub publication chain.

Order matters:
1. Refresh deal data.
2. Generate weekly reports.
3. Commit and push data CSVs to main.
4. Rebuild and publish static snapshot cards to GitHub Pages.
5. Verify a live snapshot card.
6. Send Telegram only after the public links are live.
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
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.generate_static_snapshots import DEFAULT_OUTPUT, generate

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)


class ChainError(RuntimeError):
    pass


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


ENV_FILE_VALUES = _load_env_file(ROOT / ".env")


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
    temp_root = Path(tempfile.gettempdir()).resolve()
    publish_dir = (temp_root / "calgary-grocery-gh-pages").resolve()
    if not str(publish_dir).lower().startswith(str(temp_root).lower()):
        raise ChainError(f"Refusing to clean unsafe temp path: {publish_dir}")
    if publish_dir.exists():
        shutil.rmtree(publish_dir)
    publish_dir.mkdir(parents=True)

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Calgary Grocery Hub public publication chain.")
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

    try:
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

    except ChainError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    print("\nPublication chain complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
