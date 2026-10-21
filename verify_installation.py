"""
Calgary Grocery Hub installation and revival checker.

This verifies the current FastAPI + React layout and the legacy Streamlit
dashboard without making network calls or modifying data.
"""

from __future__ import annotations

import importlib
import os
import shutil
import socket
import subprocess
import sys
import warnings
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


ROOT = Path(__file__).resolve().parent


def status(ok: bool | None, label: str, detail: str = "") -> bool:
    prefix = "[OK]" if ok is True else "[WARN]" if ok is None else "[FAIL]"
    suffix = f" - {detail}" if detail else ""
    print(f"   {prefix} {label}{suffix}")
    return ok is not False


def importable(module_name: str) -> bool:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            importlib.import_module(module_name)
        return True
    except ImportError:
        return False


def modal_date_text(values) -> str | None:
    dates = values.dropna().astype(str).str.slice(0, 10)
    if dates.empty:
        return None
    mode = dates.mode()
    return str(mode.iloc[0] if not mode.empty else dates.max())


def main() -> int:
    print("=" * 64)
    print("Calgary Grocery Hub - Installation Checker")
    print("=" * 64)

    failures = 0

    print("\n1. Runtime")
    py_ok = sys.version_info >= (3, 10)
    failures += not status(py_ok, f"Python {sys.version.split()[0]}", "3.10+ recommended")

    node_version = None
    npm_version = None
    try:
        node_version = subprocess.check_output(["node", "--version"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        pass
    npm_exe = shutil.which("npm") or shutil.which("npm.cmd")
    if npm_exe:
        try:
            npm_version = subprocess.check_output(
                [npm_exe, "--version"],
                cwd=os.environ.get("SystemRoot", r"C:\Windows"),
                text=True,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            npm_version = None
    failures += not status(bool(node_version), f"Node {node_version or 'not found'}")
    failures += not status(bool(npm_version), f"npm {npm_version or 'not found'}")

    print("\n2. Project Files")
    required_files = [
        "get_deals.py",
        "weekly_report_generator.py",
        "current_flyers.csv",
        "historical_archive.csv",
        "api/main.py",
        "api/data.py",
        "dashboard/package.json",
        "dashboard/src/App.jsx",
    ]
    for rel in required_files:
        failures += not status((ROOT / rel).exists(), rel)

    dist_index = ROOT / "dashboard" / "dist" / "index.html"
    status(dist_index.exists(), "dashboard/dist/index.html", "run npm run build in dashboard if missing")

    print("\n3. Python Dependencies")
    deps = {
        "pandas": "pandas",
        "numpy": "numpy",
        "requests": "requests",
        "python-dotenv": "dotenv",
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "streamlit": "streamlit",
        "plotly": "plotly",
        "anthropic": "anthropic",
        "google-genai": "google.genai",
        "google-generativeai": "google.generativeai",
    }
    required_deps = {
        "pandas",
        "numpy",
        "requests",
        "python-dotenv",
        "fastapi",
        "uvicorn",
    }
    for package, module in deps.items():
        ok = importable(module)
        if package in required_deps:
            failures += not status(ok, package)
        else:
            status(ok if ok else None, package, "optional")

    print("\n4. Environment")
    env_path = ROOT / ".env"
    status(env_path.exists(), ".env", "copy env.template if missing")
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path)
    postal_code = os.getenv("POSTAL_CODE", "T3M1M9")
    status(True, f"POSTAL_CODE={postal_code}")
    anthropic_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    gemini_key = bool(os.getenv("GEMINI_API_KEY"))
    telegram_token = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
    telegram_chat = bool(os.getenv("TELEGRAM_CHAT_ID"))
    telegram_alert = bool(os.getenv("TELEGRAM_ALERT_CHAT_ID"))
    status(anthropic_key if anthropic_key else None, "ANTHROPIC_API_KEY", "optional paid fallback only")
    status(gemini_key if gemini_key else None, "GEMINI_API_KEY", "optional paid fallback only")
    status(telegram_token if telegram_token else None, "TELEGRAM_BOT_TOKEN", "optional deal digest")
    status(telegram_chat if telegram_chat else None, "TELEGRAM_CHAT_ID", "optional deal digest")
    status(telegram_alert if telegram_alert else None, "TELEGRAM_ALERT_CHAT_ID", "private chat for run alerts")

    print("\n4b. AI Backend")
    try:
        from ai_backends import anthropic_model, claude_cli_model, usable_backend

        # usable_backend makes a real call. An expired CLI login and an API
        # key with no credit balance both pass an environment-only check, and
        # both have taken down a Wednesday run.
        backend = usable_backend()
        for attempt in backend.get("attempts", []):
            status(attempt["ok"], f"{attempt['backend']} reachable", attempt["reason"] or None)
        failures += not status(
            backend["type"] != "statistical",
            f"backend that will run: {backend['type']}",
            "no AI backend answered - the weekly run will stop before publishing"
            if backend["type"] == "statistical" else None,
        )
        status(True, f"API models: scoring={anthropic_model('scoring')} report={anthropic_model('report')}")
        status(True, f"CLI models: scoring={claude_cli_model('scoring')} report={claude_cli_model('report')}")
    except Exception as exc:  # pragma: no cover - diagnostics only
        failures += not status(False, "ai_backends import", str(exc))

    print("\n5. Data Load")
    try:
        import pandas as pd

        current = pd.read_csv(ROOT / "current_flyers.csv", low_memory=False)
        historical = pd.read_csv(ROOT / "historical_archive.csv", low_memory=False)
        status(True, f"current_flyers.csv rows: {len(current):,}")
        status(True, f"historical_archive.csv rows: {len(historical):,}")
        try:
            from tools.repair_archive import archive_health

            health = archive_health(historical)
            failures += not status(
                health["ok"],
                f"archive dates usable ({len(historical) - health['no_date']:,}/{len(historical):,})",
                health["message"] or None,
            )
        except Exception as exc:  # pragma: no cover - diagnostics only
            status(None, "archive health check", str(exc))
        if {"Valid_From", "Valid_Until"}.issubset(current.columns):
            valid_from = modal_date_text(current["Valid_From"])
            valid_until = modal_date_text(current["Valid_Until"])
            max_until = current["Valid_Until"].dropna().astype(str).str.slice(0, 10).max()
            status(True, f"current flyer window: {valid_from} to {valid_until}")
            if valid_until and max_until and max_until != valid_until:
                status(None, "long-running flyer present", f"latest Valid_Until is {max_until}")
            if valid_until:
                expiry = pd.to_datetime(valid_until, errors="coerce")
                if pd.notna(expiry) and expiry.date() < pd.Timestamp.now().date():
                    status(None, "current_flyers.csv appears stale", f"expired {valid_until}")
        if "Store" in current.columns:
            status(True, f"stores: {current['Store'].nunique()}")
    except Exception as exc:
        failures += not status(False, "CSV data load", str(exc))

    print("\n6. API Data Layer")
    try:
        from api.data import store

        store.load()
        status(True, f"API loaded {len(store.current):,} current deals")
        status(True, f"API loaded {len(store.historical):,} historical records")
    except Exception as exc:
        failures += not status(False, "api.data store.load()", str(exc))

    print("\n7. Local URLs")
    try:
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
    except OSError:
        hostname = "unknown"
        ip_address = "127.0.0.1"
    status(True, f"Host: {hostname} ({ip_address})")
    status(True, "Production dashboard: http://localhost:8000")
    status(True, "API health check: http://localhost:8000/api/insights")
    status(True, "Vite dev dashboard: http://localhost:5173")
    status(True, "Legacy Streamlit: streamlit run dashboard.py")

    print("\n" + "=" * 64)
    if failures:
        print(f"Result: {failures} required check(s) failed.")
        return 1
    print("Result: core installation checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
