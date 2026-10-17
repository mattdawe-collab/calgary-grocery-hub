import argparse
import pytest
from tools import run_publication_chain as chain

@pytest.mark.parametrize("failure", [AttributeError("date parsing failed"), OSError("disk unavailable")])
def test_main_alerts_on_unexpected_snapshot_failure(monkeypatch, failure):
    alerts, sends = [], []
    monkeypatch.setattr(chain, "parse_args", lambda: argparse.Namespace(
        skip_scrape=True, skip_reports=True, skip_data_push=True,
        skip_snapshot_publish=False, skip_telegram=False, skip_ai_preflight=True,
        base_url="https://example.test", output_dir=chain.DEFAULT_OUTPUT))
    monkeypatch.setattr(chain, "remote_url", lambda: "https://github.com/x/y.git")
    monkeypatch.setattr(chain, "generate", lambda *a: (_ for _ in ()).throw(failure))
    monkeypatch.setattr(chain, "send_alert", lambda text: alerts.append(text) or True)
    monkeypatch.setattr(chain, "send_telegram_messages", lambda *a: sends.append(a))
    assert chain.main() == 1
    assert len(alerts) == 1
    assert str(failure) in alerts[0]
    assert not sends
