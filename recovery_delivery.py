"""Deliver the pilot's two generated emails to the configured scanner inbox."""
import argparse
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import format_datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import smtplib
import ssl

from fallen_angel_scanner import SMTP_SERVER, SMTP_PORT
from recovery_prices import NY
from recovery_watch import latest_session


def session_ready(now):
    return latest_session(now) == now.astimezone(NY).date()


def queue_message(kind, directory, pending):
    rows = json.loads((directory / (kind + ".json")).read_text(encoding="utf-8"))["rows"]
    if not rows:
        print(f"No {kind} updates to email.")
        return
    if pending.exists():
        raise RuntimeError("Previous delivery is still pending")
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes((directory / (kind + ".eml")).read_bytes())


def smtp(pending=None):
    sender, recipient = os.environ["SENDER_EMAIL"], os.environ["RECEIVER_EMAIL"]
    if not sender.strip() or not recipient.strip():
        raise ValueError("Missing sender or recipient")
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=40) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(sender, os.environ["SENDER_PASSWORD"])
        if pending is None:
            code, _ = server.noop()
            if code != 250:
                raise RuntimeError("SMTP readiness check failed")
            print("Mail server accepted authenticated readiness check.")
            return
        raw = pending.read_bytes()
        msg = BytesParser(policy=policy.SMTP).parsebytes(raw)
        msg["From"], msg["To"] = sender, recipient
        msg["Date"] = format_datetime(datetime.now(timezone.utc))
        msg["Message-ID"] = f"<{sha256(raw).hexdigest()}@{sender.split('@')[-1]}>"
        if server.send_message(msg):
            raise RuntimeError("Mail server refused a recipient")
        print(f"Mail server accepted the {pending.stem} email.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["ready", "verify", "send", "queue"])
    parser.add_argument("--kind", choices=["early", "followup"])
    args = parser.parse_args()
    if args.action == "ready":
        print("true" if session_ready(datetime.now(timezone.utc)) else "false")
    elif args.action == "verify":
        smtp()
    else:
        if not args.kind:
            parser.error("--kind required for delivery")
        path = Path("recovery_pending") / (args.kind + ".eml")
        if args.action == "queue":
            queue_message(args.kind, Path("data/recovery"), path)
        else:
            smtp(path)
