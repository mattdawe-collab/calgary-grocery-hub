"""
Calgary Grocery Hub - AI backend selection and the Claude Code CLI backend.

Why this exists
---------------
The scoring and report steps used to call Gemini / Anthropic APIs directly.
That path broke in June 2026 (gemini-2.5-flash "thinking" tokens ate the
output budget, then the Gemini project hit its spend cap). The preferred
backend is now the locally installed Claude Code CLI (``claude -p``), which
runs under the user's Claude subscription instead of per-token API billing.

Backend selection (``AI_BACKEND`` env var):
  auto (default) -> claude_code if the CLI is installed and logged in,
                    otherwise a paid API only when AI_ALLOW_PAID_FALLBACK=1,
                    otherwise statistical.
  claude_code    -> force the Claude CLI.
  anthropic      -> Anthropic API (ANTHROPIC_API_KEY).
  gemini         -> Gemini API (GEMINI_API_KEY).
  statistical    -> no AI at all.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_CLAUDE_MODEL = "opus"
# Bulk classification runs on Sonnet (fast, light on usage limits); the two
# narrative reports run on Opus.
DEFAULT_MODELS_BY_KIND = {"scoring": "sonnet", "report": "opus"}

# Anthropic API model IDs. Bulk classification runs on Sonnet, the two
# narrative reports on Opus. Override per task with ANTHROPIC_SCORING_MODEL
# / ANTHROPIC_REPORT_MODEL, or both with ANTHROPIC_MODEL.
DEFAULT_API_MODELS_BY_KIND = {
    "scoring": "claude-sonnet-5-5",
    "report": "claude-opus-5-5",
}
VERIFY_MAX_TOKENS = 4
DEFAULT_TIMEOUT_SECONDS = 600

# Env vars that must not reach the CLI subprocess.
#   * ANTHROPIC_* : if an API key is present the CLI bills the API instead of
#                   using the subscription login. The .env file has one.
#   * CLAUDECODE / CLAUDE_CODE_* : mark a nested Claude Code session; leaving
#                   them set makes the child CLI refuse or misbehave.
_SCRUB_EXACT = {
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "CLAUDECODE",
}
_SCRUB_PREFIXES = ("CLAUDE_CODE_",)


try:
    import anthropic
    ANTHROPIC_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - the SDK is in requirements.txt
    ANTHROPIC_SDK_AVAILABLE = False


class ClaudeCLIError(RuntimeError):
    """Raised when the Claude CLI could not produce a usable answer."""


def _split_args(value: str) -> list[str]:
    """Split a command string; keeps Windows backslashes (UNC paths) intact."""
    if os.name == "nt":
        return [token.strip('"') for token in shlex.split(value, posix=False)]
    return shlex.split(value)


# --------------------------------------------------------------------------
# Locating and configuring the CLI
# --------------------------------------------------------------------------
def claude_cli_command() -> list[str] | None:
    """Return the argv prefix for the Claude CLI, or None if not installed.

    ``CLAUDE_CLI_CMD`` overrides discovery (used by tests and by anyone whose
    scheduled task does not have the npm shim on PATH).
    """
    override = os.environ.get("CLAUDE_CLI_CMD", "").strip()
    if override:
        return _split_args(override)

    found = shutil.which("claude")
    if found:
        return [found]

    # Windows scheduled tasks often run without the user's PATH additions.
    appdata = os.environ.get("APPDATA")
    if appdata:
        for name in ("claude.cmd", "claude"):
            candidate = Path(appdata) / "npm" / name
            if candidate.exists():
                return [str(candidate)]
    return None


def claude_cli_cwd() -> str:
    """A local directory to launch the CLI from.

    The npm shim is a .cmd file run by cmd.exe, which refuses a UNC working
    directory ("UNC paths are not supported. Defaulting to Windows directory.")
    and exits 1. The project lives on a NAS, so never inherit its cwd; with
    --bare the CLI needs no project context anyway.
    """
    configured = os.environ.get("CLAUDE_CLI_CWD", "").strip()
    if configured and os.path.isdir(configured):
        return configured
    return tempfile.gettempdir()


def claude_cli_env() -> dict[str, str]:
    """Copy of os.environ with API keys and nested-session markers removed."""
    env = {}
    for key, value in os.environ.items():
        if key in _SCRUB_EXACT or key.startswith(_SCRUB_PREFIXES):
            continue
        env[key] = value
    env.setdefault("PYTHONUTF8", "1")
    return env


def claude_cli_model(kind: str = "scoring") -> str:
    """Model alias for a task kind: CLAUDE_CODE_<KIND>_MODEL, then CLAUDE_CODE_MODEL."""
    specific = os.environ.get(f"CLAUDE_CODE_{kind.upper()}_MODEL", "").strip()
    generic = os.environ.get("CLAUDE_CODE_MODEL", "").strip()
    return specific or generic or DEFAULT_MODELS_BY_KIND.get(kind, DEFAULT_CLAUDE_MODEL)


def claude_cli_logged_in() -> bool:
    """True when ``claude auth status`` reports a login. Cheap; no model call."""
    cmd = claude_cli_command()
    if not cmd:
        return False
    try:
        proc = subprocess.run(
            [*cmd, "auth", "status"],
            capture_output=True, text=True, env=claude_cli_env(), timeout=60, cwd=claude_cli_cwd(),
            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    try:
        return bool(json.loads(proc.stdout or "{}").get("loggedIn"))
    except json.JSONDecodeError:
        return False


# --------------------------------------------------------------------------
# Running a headless prompt
# --------------------------------------------------------------------------
def _cli_flags(model: str) -> list[str]:
    flags = [
        "-p",
        "--model", model,
        "--output-format", "json",
        "--no-session-persistence",
        "--tools", "",
        "--strict-mcp-config",
    ]
    # --bare would be faster, but it also skips reading the stored OAuth login
    # and the CLI then answers "Not logged in". Opt in only via CLAUDE_CLI_BARE=1.
    if os.environ.get("CLAUDE_CLI_BARE", "0") == "1":
        flags.append("--bare")
    effort = os.environ.get("CLAUDE_CODE_EFFORT", "").strip()
    if effort:
        flags.extend(["--effort", effort])
    extra = os.environ.get("CLAUDE_CLI_EXTRA_ARGS", "").strip()
    if extra:
        flags.extend(_split_args(extra))
    return flags


def run_claude_cli(prompt: str, model: str | None = None, timeout: int | None = None) -> str:
    """Run one headless ``claude -p`` call and return the model's text answer."""
    cmd = claude_cli_command()
    if not cmd:
        raise ClaudeCLIError("Claude CLI not found (install Claude Code or set CLAUDE_CLI_CMD)")
    model = model or claude_cli_model()
    timeout = timeout or int(os.environ.get("CLAUDE_CLI_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))

    # The prompt goes over stdin, never argv: on Windows the npm shim is a
    # .cmd run by cmd.exe, which caps the command line (~8 KB) and truncates an
    # argument at its first newline (the model then only sees line one).
    argv = [*cmd, *_cli_flags(model)]
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, env=claude_cli_env(),
            timeout=timeout, encoding="utf-8", errors="replace",
            input=prompt, cwd=claude_cli_cwd(),
        )
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCLIError(f"Claude CLI timed out after {timeout}s") from exc
    except OSError as exc:
        raise ClaudeCLIError(f"Could not start Claude CLI: {exc}") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise ClaudeCLIError(f"Claude CLI exit code {proc.returncode}: {detail}")

    stdout = (proc.stdout or "").strip()
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        # Older CLIs (or --output-format text) print the answer directly.
        if stdout:
            return stdout
        raise ClaudeCLIError("Claude CLI returned no output")

    if isinstance(payload, dict):
        result = payload.get("result")
        if payload.get("is_error"):
            raise ClaudeCLIError(f"Claude CLI error: {result or payload.get('subtype') or 'unknown'}")
        if isinstance(result, str) and result.strip():
            return result
        structured = payload.get("structured_output")
        if structured is not None:
            return json.dumps(structured)
        raise ClaudeCLIError("Claude CLI returned an empty result")
    return stdout


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json_array(text: str) -> list:
    """Pull the JSON array out of a model reply, tolerating fences and prose.

    Raises ValueError when no complete array can be decoded (e.g. truncated
    output), so callers fall back instead of silently using partial data.
    """
    if text is None:
        raise ValueError("empty response")
    candidates = [text.strip()]
    candidates.extend(m.strip() for m in _FENCE_RE.findall(text))
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, list):
                    return value
    raise ValueError("no complete JSON array found in response")


# --------------------------------------------------------------------------
# Backend selection
# --------------------------------------------------------------------------
def select_backend(verbose: bool = False) -> dict:
    """Decide which AI backend to use. Returns {'type': ..., 'reason': ...}."""
    requested = os.environ.get("AI_BACKEND", "auto").strip().lower() or "auto"
    allow_paid = os.environ.get("AI_ALLOW_PAID_FALLBACK", "").strip().lower() in {"1", "true", "yes"}
    have_cli = claude_cli_command() is not None
    have_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    have_gemini = bool(os.environ.get("GEMINI_API_KEY"))

    def pick(kind: str, reason: str) -> dict:
        if verbose:
            print(f"   🤖 AI backend: {kind} ({reason})")
        return {"type": kind, "reason": reason}

    login_hint = "run `claude login` in a terminal as this Windows user"

    if requested == "statistical":
        return pick("statistical", "AI_BACKEND=statistical")
    if requested == "claude_code":
        if not have_cli:
            return pick("statistical", "AI_BACKEND=claude_code but the Claude CLI is not installed")
        if not claude_cli_logged_in():
            return pick("statistical", f"AI_BACKEND=claude_code but the CLI is not logged in - {login_hint}")
        return pick("claude_code", "AI_BACKEND=claude_code")
    if requested == "anthropic":
        return pick("anthropic" if have_anthropic else "statistical", "AI_BACKEND=anthropic")
    if requested == "gemini":
        return pick("gemini" if have_gemini else "statistical", "AI_BACKEND=gemini")

    # auto: the API leads. A CLI login expires - it silently killed the
    # 2026-10-21 run - while an API key does not, so the key is the reliable
    # primary and the CLI is the standby.
    if have_anthropic:
        return pick("anthropic", "ANTHROPIC_API_KEY present")
    if have_cli and claude_cli_logged_in():
        return pick("claude_code", "no API key; Claude CLI logged in")
    cli_note = "Claude CLI not installed" if not have_cli else f"Claude CLI not logged in - {login_hint}"
    if allow_paid and have_gemini:
        return pick("gemini", f"no API key; {cli_note}; AI_ALLOW_PAID_FALLBACK=1")
    return pick("statistical", f"no ANTHROPIC_API_KEY; {cli_note}")


if __name__ == "__main__":
    # Smoke test: python ai_backends.py [--call]
    try:  # make .env visible when run directly as a diagnostic
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    except ImportError:
        pass
    print(f"Claude CLI: {claude_cli_command()}")
    print(f"Logged in: {claude_cli_logged_in()}")
    print(f"Selected backend: {select_backend()}")
    if "--call" in sys.argv:
        print(run_claude_cli('Reply with ONLY this JSON array: [{"ok": true}]'))


def anthropic_model(kind: str = "scoring") -> str:
    """Model ID for an Anthropic API call, by task kind."""
    specific = os.environ.get(f"ANTHROPIC_{kind.upper()}_MODEL", "").strip()
    generic = os.environ.get("ANTHROPIC_MODEL", "").strip()
    return specific or generic or DEFAULT_API_MODELS_BY_KIND.get(kind, "claude-sonnet-5-5")


# Failures that mean "this backend will not work today", as opposed to a blip
# worth retrying. A key with no credit balance authenticates fine and then
# fails every call, which is why "the key is set" was never a usable check.
_UNUSABLE_MARKERS = (
    "credit balance",
    "insufficient_quota",
    "authentication_error",
    "invalid x-api-key",
    "invalid api key",
    "permission_denied",
    "permission error",
    "401",
    "403",
)
_RETRYABLE_MARKERS = ("429", "rate_limit", "529", "overloaded", "500", "502", "503", "timeout")


def is_backend_unusable(error) -> bool:
    """True when an error means the backend itself is unavailable."""
    text = f"{type(error).__name__}: {error}".lower()
    if any(m in text for m in _RETRYABLE_MARKERS):
        return False
    return any(m in text for m in _UNUSABLE_MARKERS)


def _anthropic_client():
    if not ANTHROPIC_SDK_AVAILABLE:
        raise RuntimeError("anthropic SDK is not installed (pip install anthropic)")
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def response_text(response) -> str:
    """Join the text blocks of a Messages response, ignoring the rest.

    Current models think by default, so content[0] is a ThinkingBlock and
    reading content[0].text raises AttributeError. Every caller goes through
    here so thinking can never be mistaken for the answer, or leak into a
    published report.
    """
    parts = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", "") == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts)


def anthropic_request_kwargs(model: str, system: str, prompt: str, max_tokens: int,
                             effort: str | None = None) -> dict:
    """Build every Anthropic Messages request through one place.

    Preflight and the real scoring call must send the same parameters, or
    verification proves nothing. On 2026-10-21 they differed by one field and
    preflight passed while all 30 scoring batches returned 400
    "`temperature` is deprecated for this model". Current models reject
    sampling parameters, so none are sent. `effort` is optional and only set
    for the bulk classification pass.
    """
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    if effort:
        # Classification does not repay deep thinking: on a real 40-item
        # batch, low effort matched default output in 21s and 4,584 tokens
        # against 32s and 6,362. The narrative write-ups keep the default.
        kwargs["output_config"] = {"effort": effort}
    return kwargs


def verify_backend(kind: str, client=None) -> tuple[bool, str]:
    """Prove a backend can actually answer before the run commits to it.

    Returns (ok, reason). The Wednesday run used to discover a dead backend
    only after scraping; worse, an API key with no credits looks healthy to
    any check that just reads the environment. So this spends a few tokens
    on a real round trip.
    """
    if kind == "statistical":
        return True, ""

    if kind == "claude_code":
        return (True, "") if claude_cli_logged_in() else (
            False, "Claude CLI is not logged in - run `claude login` as this Windows user"
        )

    if kind == "anthropic":
        # Only demand the env key when we have to build the client ourselves.
        if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
            return False, "ANTHROPIC_API_KEY is not set"
        try:
            client = client if client is not None else _anthropic_client()
            client.messages.create(**anthropic_request_kwargs(
                model=anthropic_model("scoring"),
                system="Reply with exactly: OK",
                prompt="Reply with exactly: OK",
                max_tokens=VERIFY_MAX_TOKENS,
                effort=os.environ.get("ANTHROPIC_SCORING_EFFORT", "low"),
            ))
            return True, ""
        except Exception as exc:  # noqa: BLE001 - any failure means do not use it
            detail = str(exc)
            if "credit balance" in detail.lower():
                return False, (
                    "Anthropic API key has no credit balance - add credits at "
                    "console.anthropic.com under Plans & Billing"
                )
            return False, f"Anthropic API unavailable: {detail[:200]}"

    if kind == "gemini":
        return (True, "") if os.environ.get("GEMINI_API_KEY") else (False, "GEMINI_API_KEY is not set")

    return False, f"unknown backend {kind}"


def usable_backend(verbose: bool = False) -> dict:
    """Pick a backend and prove it works, walking the fallback order.

    Returns the chosen backend dict with an extra 'attempts' list recording
    what was tried and why each option was passed over.
    """
    requested = os.environ.get("AI_BACKEND", "auto").strip().lower() or "auto"
    order = [requested] if requested != "auto" else ["anthropic", "claude_code"]
    attempts = []
    for kind in order:
        if kind == "statistical":
            break
        ok, reason = verify_backend(kind)
        attempts.append({"backend": kind, "ok": ok, "reason": reason})
        if verbose:
            print(f"   {'OK  ' if ok else 'skip'} {kind}{'' if ok else f' - {reason}'}")
        if ok:
            return {"type": kind, "reason": "verified", "attempts": attempts}
    return {"type": "statistical", "reason": "no AI backend verified", "attempts": attempts}
