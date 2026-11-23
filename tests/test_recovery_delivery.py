from datetime import datetime, timezone
from email.message import EmailMessage
from unittest.mock import MagicMock

import pytest

import recovery_delivery as delivery
from recovery_watch import early_batch


@pytest.mark.parametrize(("day", "hour", "ready"), [
    (23, 19, False), (23, 22, True), (26, 22, False), (28, 22, False),
])
def test_after_close_and_holidays(day, hour, ready):
    assert delivery.session_ready(datetime(2026, 11, day, hour, tzinfo=timezone.utc)) is ready


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


def test_smtp_verification_and_delivery_use_existing_recipient(tmp_path,monkeypatch):
    for name,val in {"SENDER_EMAIL":"from@example.org","SENDER_PASSWORD":"test",
                     "RECEIVER_EMAIL":"to@example.org"}.items():
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
    assert b"to@example.org" not in pending.read_bytes()
