"""Stand-in for the `claude` CLI used by tests. Behaviour is driven by env vars."""
import json
import os
import sys

args = sys.argv[1:]
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
stdin_text = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
prompt_in = stdin_text if stdin_text else (args[-1] if args else "")

# Record how we were invoked so tests can assert on it.
record = os.environ.get("FAKE_CLAUDE_RECORD")
if record:
    with open(record, "w", encoding="utf-8") as fh:
        json.dump({"args": args, "cwd": os.getcwd(), "stdin_len": len(stdin_text), "stdin_head": stdin_text[:40], "env": {k: v for k, v in os.environ.items()}}, fh)

if mode == "auth_error":
    print(json.dumps({"type": "result", "is_error": True,
                      "result": "Failed to authenticate: OAuth session expired and could not be refreshed"}))
    sys.exit(0)
if mode == "crash":
    print("boom", file=sys.stderr)
    sys.exit(1)
if mode == "hang":
    import time
    time.sleep(30)
    sys.exit(0)

text = os.environ.get("FAKE_CLAUDE_TEXT", '[{"a": 1}]')
if mode == "echo_items":
    # Behave like the real scorer: read the ITEMS block out of the prompt and
    # return one scored object per item, in reverse order to prove callers
    # match on name rather than position.
    prompt = prompt_in
    block = prompt.split("ITEMS TO ANALYZE:", 1)[1].split("\n\nFor each item", 1)[0]
    items = json.loads(block)
    out = [{"item": it["item"], "category": "Pork", "subcategory": "Bacon",
            "normalized_name": "Bacon", "score": 77, "rating": "Good Buy",
            "explanation": "fake"} for it in reversed(items)]
    if os.environ.get("FAKE_CLAUDE_DROP_LAST"):
        out = out[1:]
    text = json.dumps(out)
if mode == "report":
    # Narrative report: long enough to pass the length guard, ends with hashtags.
    text = ("Calgary deals this week. " * 60).strip() + "\n#YYCDeals #CalgaryGrocery #GroceryDeals"

if "--output-format" in args and args[args.index("--output-format") + 1] == "json":
    print(json.dumps({"type": "result", "is_error": False, "result": text, "session_id": "x"}))
else:
    print(text)
