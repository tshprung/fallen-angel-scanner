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
from recovery_watch import latest_session
from ai_research import atomic_json


def session_ready(now, state):
    session = latest_session(now).isoformat()
    completed = state.get("last_completed_delivery_session") or state["preview_through"]
    return session > completed


def record_completion(state_path, coverage_path=None):
    state = json.loads(state_path.read_text(encoding="utf-8"))
    # A queued follow-up is acknowledged before a later scan can advance last_scan.
    session = (json.loads(coverage_path.read_text(encoding="utf-8"))["date"]
               if coverage_path is not None else state["last_scan"])
    if session != state["last_scan"] or session < state.get("last_completed_delivery_session", ""):
        raise ValueError("Scan coverage does not match the delivery session")
    state["last_completed_delivery_session"] = session
    atomic_json(state_path, state)


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
    sender, recipient = (os.environ[k].strip() for k in ("SENDER_EMAIL", "RECEIVER_EMAIL"))
    if not sender or not recipient:
        raise ValueError("Missing sender or recipient")
    if any(c in sender + recipient for c in "\r\n"):
        raise ValueError("Unexpected line break inside an email address")
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
    parser.add_argument("action", choices=["ready", "verify", "send", "queue", "complete", "complete-queued"])
    parser.add_argument("--kind", choices=["early", "followup"])
    args = parser.parse_args()
    state_path = Path("recovery_watch_state.json")
    if args.action == "ready":
        state = json.loads(state_path.read_text(encoding="utf-8"))
        print("true" if session_ready(datetime.now(timezone.utc), state) else "false")
    elif args.action == "complete":
        record_completion(state_path, Path("data/recovery/coverage.json"))
    elif args.action == "complete-queued":
        if not Path("recovery_pending/followup.eml").is_file():
            parser.error("No queued follow-up to acknowledge")
        record_completion(state_path)
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
