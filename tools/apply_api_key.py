"""
Put a new Anthropic API key in place, prove it works, then refresh the site.

Run it from PowerShell:

    cd "\\\\NASD66196\\Python Projects\\Weekly Deals"
    python tools\\apply_api_key.py "sk-ant-api03-..."

Stages, in order, each one gating the next:

1. Validate the key looks like a key and write it to .env (backing .env up).
2. Verify it with a real API call. A key with no credit balance authenticates
   and then fails every call, so "it saved" is not proof of anything.
3. Run the full publication chain: scrape, score, write the reports, publish
   the page and the snapshot cards, send the Telegram digests.

Stage 3 is skipped automatically if stage 2 fails, so a dead key can never
burn half an hour and publish a statistical-only page. Pass --no-run to stop
after verification.

The key is never printed in full and never echoed to the console.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ENV_FILE = ROOT / ".env"
PLACEHOLDERS = {
    "paste_your_key_here",
    "your_anthropic_api_key_here",
    "sk-ant-...",
    "<key>",
}


def mask(key: str) -> str:
    """A form of the key that is safe to print."""
    key = (key or "").strip().strip('"').strip("'")
    if len(key) <= 14:
        return "sk-ant-..."
    return f"{key[:11]}...{key[-4:]}"


def validate_key(key) -> tuple[bool, str]:
    """Catch an empty paste or a placeholder before touching .env."""
    key = (key or "").strip().strip('"').strip("'")
    if not key:
        return False, "no key supplied - paste it between the quotes"
    if key.lower() in PLACEHOLDERS:
        return False, "that is the placeholder text, not a key"
    if not key.startswith("sk-ant-"):
        return False, "an Anthropic API key starts with 'sk-ant-'"
    if len(key) < 40:
        return False, f"that key looks truncated ({len(key)} characters)"
    return True, ""


def set_env_value(path: Path, name: str, value: str) -> Path:
    """Set one setting in a .env file, preserving everything else.

    Reads and writes utf-8-sig: the project's .env carries a byte order mark
    and non-ASCII values, and Windows PowerShell would otherwise rewrite it
    as cp1252 and corrupt them.
    """
    original = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    backup = path.with_suffix(path.suffix + ".bak")
    if path.exists():
        shutil.copy2(path, backup)

    pattern = re.compile(rf"^(\s*){re.escape(name)}\s*=.*$")
    lines = original.splitlines()
    replaced = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue                      # a commented example is not the setting
        if pattern.match(line):
            lines[i] = f"{name}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{name}={value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return backup


def _stage(number: int, title: str) -> None:
    print(f"\n=== {number}. {title} ===", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a new Anthropic API key and refresh the site.")
    parser.add_argument("api_key", help="the new key, in quotes")
    parser.add_argument("--no-run", action="store_true", help="set and verify the key, but do not publish")
    args = parser.parse_args()

    key = args.api_key.strip().strip('"').strip("'")

    _stage(1, "Checking and saving the key")
    ok, why = validate_key(key)
    if not ok:
        print(f"STOPPED: {why}")
        return 2
    backup = set_env_value(ENV_FILE, "ANTHROPIC_API_KEY", key)
    print(f"Saved {mask(key)} to {ENV_FILE}")
    print(f"Previous .env backed up to {backup.name}")

    _stage(2, "Verifying the key with a real API call")
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE, override=True)
    from ai_backends import anthropic_model, usable_backend

    backend = usable_backend(verbose=True)
    if backend["type"] == "statistical":
        print("\nSTOPPED: no AI backend answered, so nothing was published.")
        print("The key is saved; fix the problem above and re-run this command.")
        return 1
    if backend["type"] != "anthropic":
        print(f"\nNote: the API did not answer, so the run would use '{backend['type']}' instead.")
    else:
        print(f"API is live. Scoring on {anthropic_model('scoring')}, "
              f"write-ups on {anthropic_model('report')}.")

    if args.no_run:
        print("\n--no-run given: stopping before publishing.")
        return 0

    _stage(3, "Refreshing the deals (this takes about 20-30 minutes)")
    print("Scrape, score, write the reports, publish the page, send Telegram.\n", flush=True)
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "run_publication_chain.py")],
        cwd=ROOT,
    )
    if result.returncode != 0:
        print("\nThe publication chain failed - see the errors above.")
        return result.returncode

    print("\nDone. The public page is refreshed and the digests have been sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
