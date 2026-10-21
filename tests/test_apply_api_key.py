import pytest

from tools.apply_api_key import mask, set_env_value, validate_key


# ---------------------------------------------------------------------------
# Writing the key into .env
# ---------------------------------------------------------------------------
def test_replaces_an_existing_key_and_leaves_everything_else_alone(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "﻿# Config\nANTHROPIC_API_KEY=sk-ant-old\nPOSTAL_CODE=T3M1M9\n"
        "TELEGRAM_BOT_TOKEN=abc\n",
        encoding="utf-8-sig",
    )
    set_env_value(env, "ANTHROPIC_API_KEY", "sk-ant-new")
    text = env.read_text(encoding="utf-8-sig")
    assert "ANTHROPIC_API_KEY=sk-ant-new" in text
    assert "sk-ant-old" not in text
    assert "POSTAL_CODE=T3M1M9" in text
    assert "TELEGRAM_BOT_TOKEN=abc" in text
    assert text.count("ANTHROPIC_API_KEY=") == 1


def test_appends_when_the_setting_is_absent(tmp_path):
    env = tmp_path / ".env"
    env.write_text("POSTAL_CODE=T3M1M9\n", encoding="utf-8-sig")
    set_env_value(env, "ANTHROPIC_API_KEY", "sk-ant-new")
    text = env.read_text(encoding="utf-8-sig")
    assert "ANTHROPIC_API_KEY=sk-ant-new" in text
    assert "POSTAL_CODE=T3M1M9" in text


def test_keeps_the_byte_order_mark_the_project_writes(tmp_path):
    # .env is read with utf-8-sig elsewhere; dropping the BOM or writing
    # cp1252 would corrupt the Telegram token's characters.
    env = tmp_path / ".env"
    env.write_text("﻿ANTHROPIC_API_KEY=old\nX=café\n", encoding="utf-8-sig")
    set_env_value(env, "ANTHROPIC_API_KEY", "new")
    raw = env.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "café" in env.read_text(encoding="utf-8-sig")


def test_a_commented_line_is_not_mistaken_for_the_setting(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# ANTHROPIC_API_KEY=example\nANTHROPIC_API_KEY=real\n", encoding="utf-8-sig")
    set_env_value(env, "ANTHROPIC_API_KEY", "new")
    text = env.read_text(encoding="utf-8-sig")
    assert "# ANTHROPIC_API_KEY=example" in text
    assert "ANTHROPIC_API_KEY=new" in text
    assert "ANTHROPIC_API_KEY=real" not in text


def test_a_backup_is_written_before_changing_anything(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=old\n", encoding="utf-8-sig")
    backup = set_env_value(env, "ANTHROPIC_API_KEY", "new")
    assert backup.exists()
    assert "old" in backup.read_text(encoding="utf-8-sig")


# ---------------------------------------------------------------------------
# Guard rails
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["", "   ", "PASTE_YOUR_KEY_HERE", "your_anthropic_api_key_here", "hunter2"])
def test_rejects_something_that_is_not_a_key(bad):
    ok, why = validate_key(bad)
    assert ok is False and why


def test_accepts_a_real_looking_key():
    ok, why = validate_key("sk-ant-api03-" + "A" * 90)
    assert ok is True and why == ""


def test_tolerates_quotes_and_whitespace_from_a_paste():
    ok, _ = validate_key('  "sk-ant-api03-' + "A" * 90 + '"  ')
    assert ok is True


def test_the_key_is_never_printed_in_full():
    key = "sk-ant-api03-" + "B" * 90
    shown = mask(key)
    assert key not in shown
    assert shown.startswith("sk-ant-")
    assert len(shown) < 30
