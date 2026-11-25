from datetime import datetime, timezone
from email.message import EmailMessage
import json
from unittest.mock import MagicMock

import pytest

import recovery_delivery as delivery
from recovery_watch import early_batch


@pytest.mark.parametrize(("day", "hour", "completed", "ready"), [
    (23, 19, "2026-11-20", False), (23, 22, "2026-11-20", True),
    (24, 6, "2026-11-20", True), (24, 6, "2026-11-23", False),
    (24, 22, "2026-11-23", True), (26, 22, "2026-11-25", False),
    (28, 22, "2026-11-27", False),
])
def test_after_close_and_holidays(day, hour, completed, ready):
    state = {"last_completed_delivery_session":completed}
    assert delivery.session_ready(datetime(2026, 11, day, hour, tzinfo=timezone.utc), state) is ready


def test_partial_scan_is_still_due_until_delivery_completes(tmp_path):
    state = {"preview_through": "2026-11-20", "last_scan": "2026-11-23"}
    now = datetime(2026, 11, 24, 6, tzinfo=timezone.utc)
    assert delivery.session_ready(now, state)
    path, coverage = tmp_path / "state.json", tmp_path / "coverage.json"
    path.write_text(json.dumps(state))
    coverage.write_text('{"date":"2026-11-20"}')
    with pytest.raises(ValueError):
        delivery.record_completion(path, coverage)
    coverage.write_text('{"date":"2026-11-23"}')
    delivery.record_completion(path, coverage)
    assert not delivery.session_ready(now, json.loads(path.read_text()))


def test_preview_backlog_does_not_fill_first_live_email():
    event = dict(cap=10, latest_close=10, ticker="OLD", day="2026-11-19", key="old")
    fresh = dict(event, ticker="NEW", day="2026-11-23", key="new")
    state = {"preview_through":"2026-11-20", "watch":{"old":event,"new":fresh}}
    assert early_batch(state,"2026-11-23") == [fresh]


def test_empty_updates_and_retry_preserve_pending_message(tmp_path):
    pending = tmp_path / "pending" / "early.eml"
    (tmp_path / "early.json").write_text('{"rows":[]}')
    delivery.queue_message("early",tmp_path,pending)
    assert not pending.exists()
    (tmp_path / "early.json").write_text('{"rows":[{}]}')
    (tmp_path / "early.eml").write_bytes(b"Subject: Test\r\n\r\nBody")
    delivery.queue_message("early",tmp_path,pending)
    with pytest.raises(RuntimeError,match="pending"):
        delivery.queue_message("early",tmp_path,pending)
    assert pending.read_bytes() == (tmp_path / "early.eml").read_bytes()


@pytest.mark.parametrize("early,followup,expected", [
    (["A","B"],["B","C"],["A","B","C"]), ([],["C"],["C"]), (["A"],[],["A"]), ([],[],[]),
])
def test_one_daily_digest(tmp_path, early, followup, expected):
    for stage,tickers in (("early",early),("followup",followup)):
        rows = [dict(ticker=t,latest_close=10,latest_reference=15) for t in tickers]
        if stage == "followup":
            for row in rows:
                row.update(status="Research hold",brief="Debt unverified.",quote=None)
        (tmp_path / (stage+".json")).write_text(json.dumps({"rows":rows}))
    (tmp_path / "coverage.json").write_text('{"date":"2026-11-24"}')
    delivery.compose_digest(tmp_path,datetime.now(timezone.utc))
    digest=json.loads((tmp_path / "digest.json").read_text())
    assert [r["ticker"] for r in digest["rows"]] == expected
    body=(tmp_path / "digest.html").read_text(encoding="utf-8")
    assert body.count("<b>") == len(expected)
    for ticker in followup:
        assert ticker+" upside unknown</b> · Research hold. Debt unverified." in body
    pending=tmp_path / "pending" / "digest.eml"
    delivery.queue_message("digest",tmp_path,pending)
    assert pending.exists() == bool(expected)


def test_smtp_verification_and_delivery_use_existing_recipient(tmp_path,monkeypatch):
    for name,val in {"SENDER_EMAIL":"from@example.org\r\n","SENDER_PASSWORD":"test",
                     "RECEIVER_EMAIL":"to@example.org\n"}.items():
        monkeypatch.setenv(name,val)
    smtp = MagicMock()
    monkeypatch.setattr(delivery.smtplib,"SMTP",smtp)
    server = smtp.return_value.__enter__.return_value
    server.noop.return_value = (250,b"ok")
    delivery.smtp()
    server.send_message.assert_not_called()
    msg = EmailMessage()
    msg["Subject"] = "Recovery watch"
    msg.set_content("Price alert.")
    pending = tmp_path / "early.eml"
    pending.write_bytes(msg.as_bytes())
    server.send_message.return_value = {}
    delivery.smtp(pending)
    sent = server.send_message.call_args.args[0]
    assert sent["To"] == "to@example.org" and sent["Message-ID"]
    assert sent["From"] == "from@example.org" and sent["Message-ID"].endswith("@example.org>")
    assert b"to@example.org" not in pending.read_bytes()
