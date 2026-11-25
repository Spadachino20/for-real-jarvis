"""Reminders that live on this PC: JARVIS says them out loud himself, no server needed.

  python -m jarvis.reminders add <when> "<what>" [daily|weekdays|weekly]    when: 2026-11-25T16:30, 16:30 or +10m / +2h
  python -m jarvis.reminders list | remove <id>
Self-check: python -m jarvis.reminders --check
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Callable

from . import settings

FILE = settings.DATA / "reminders.json"
TEXT = {"en": ("Reminder, sir: {}.", "You had a reminder at {}, sir: {}."), "es": ("Recordatorio, señor: {}.", "Tenía un recordatorio a las {}, señor: {}.")}


def load() -> list[dict]:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save(all_: list[dict]) -> None:  # ponytail: no lock; two writes in the same instant would lose one
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(all_, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(FILE)


def when(text: str, now: datetime) -> datetime:
    if m := re.fullmatch(r"\+(\d+)\s*([mhd])", text):
        return now + timedelta(**{{"m": "minutes", "h": "hours", "d": "days"}[m[2]]: int(m[1])})
    if m := re.fullmatch(r"(\d{1,2}):(\d{2})", text):
        at = now.replace(hour=int(m[1]), minute=int(m[2]), second=0, microsecond=0)
        return at if at > now else at + timedelta(days=1)
    at = datetime.fromisoformat(text)
    return (at.astimezone() if at.tzinfo else at).replace(tzinfo=None)


def following(at: datetime, repeat: str, now: datetime) -> datetime | None:
    """The next time of a repeating one (None: it was only once)."""
    if not repeat:
        return None
    while at <= now or (repeat == "weekdays" and at.weekday() > 4):
        at += timedelta(days=7 if repeat == "weekly" else 1)
    return at


def say(r: dict, now: datetime, lang: str) -> str:
    at, t = datetime.fromisoformat(r["at"]), TEXT.get(lang, TEXT["en"])
    what = r["text"].rstrip(".")
    return t[1].format(at.strftime("%H:%M"), what) if now - at > timedelta(minutes=5) else t[0].format(what)


def watch(speak: Callable[[str], bool]) -> None:
    """Runs forever in a thread. Away from the PC: it waits until you're back. speak() False (he's busy): tries again."""
    from . import proactive
    while True:
        time.sleep(5)
        try:
            now = datetime.now()
            due = [r for r in load() if datetime.fromisoformat(r["at"]) <= now]
            if not due or proactive.idle_seconds() > 300 or getattr(proactive, "locked", lambda: False)():
                continue
            s = settings.load()
            for r in due:
                if not speak(say(r, now, "en" if s["speak_english"] else s["language"])):
                    break
                nxt = following(datetime.fromisoformat(r["at"]), r.get("repeat", ""), now)
                rest = [x for x in load() if x["id"] != r["id"]]
                save(rest + [{**r, "at": nxt.isoformat(timespec="minutes")}] if nxt else rest)
        except Exception as e:  # noqa: BLE001 — never kill the thread
            print("reminders:", type(e).__name__, e)


def main(args: list[str]) -> str:
    if args[:1] == ["add"] and len(args) >= 3:
        repeat = args[3] if len(args) > 3 else ""
        if repeat not in ("", "daily", "weekdays", "weekly"):
            return "repeat: daily, weekdays or weekly"
        all_, now = load(), datetime.now()
        at = when(args[1], now)
        if at <= now - timedelta(minutes=1):
            return f"NOT saved: {at:%Y-%m-%d %H:%M} is already past (now {now:%Y-%m-%d %H:%M})."
        new = max([r["id"] for r in all_], default=0) + 1
        save(all_ + [{"id": new, "at": at.isoformat(timespec="seconds"), "text": args[2], "repeat": repeat}])
        return f"Saved #{new}: {at:%a %Y-%m-%d %H:%M} {repeat} - {args[2]}"
    if args[:1] == ["remove"] and len(args) == 2:
        all_ = load()
        rest = [r for r in all_ if str(r["id"]) != args[1]]
        save(rest)
        return "Removed." if len(rest) < len(all_) else "There's no reminder with that id."
    if args[:1] == ["list"]:
        return "\n".join(f"#{r['id']} {r['at']} {r.get('repeat', '')} - {r['text']}" for r in load()) or "No reminders."
    return __doc__ or ""


if __name__ == "__main__":
    if "--check" in sys.argv:
        n = datetime(2026, 11, 25, 15, 0)  # a Wednesday
        assert when("+10m", n) == datetime(2026, 11, 25, 15, 10) and when("16:30", n).day == 25 and when("8:00", n).day == 26
        assert following(n, "", n) is None and following(n, "daily", n).day == 26 and following(datetime(2026, 11, 27, 9), "weekdays", datetime(2026, 11, 27, 9)).day == 30
        assert say({"at": "2026-11-25T14:00", "text": "agua"}, n, "es").startswith("Tenía") and say({"at": "2026-11-25T15:00", "text": "agua."}, n, "es") == "Recordatorio, señor: agua."
        print("reminders ok")
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(main(sys.argv[1:]))
