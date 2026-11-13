"""JARVIS speaks first: alerts when the PC is in trouble, and a "welcome back" when you sit down again.

Local checks only (psutil, Windows idle time): no agent, no tokens. Turn off in data/settings.json:
"alerts": false / "welcome_back": false.
"""
from __future__ import annotations

import ctypes
import json
import time
from typing import Callable

from . import settings

AWAY = 10 * 60      # this long without touching mouse or keyboard counts as "away"
COOLDOWN = 30 * 60  # the same alert at most every 30 minutes

TEXT = {
    "en": {"ram": "Sir, memory is at {n} percent. Something is eating it: {top}.",
           "disk": "Sir, drive {d} has only {n} gigabytes left.",
           "battery": "Sir, battery at {n} percent and not charging.",
           "back": "Welcome back, sir. It's {time}.", "where": " You were in {app}.",
           "reminder": " Next reminder: {name}, {when}."},
    "es": {"ram": "Señor, la memoria está al {n} por ciento. La que más consume: {top}.",
           "disk": "Señor, al disco {d} le quedan solo {n} gigas.",
           "battery": "Señor, batería al {n} por ciento y sin cargar.",
           "back": "Bienvenido de vuelta, señor. Son las {time}.", "where": " Estabas en {app}.",
           "reminder": " Próximo recordatorio: {name}, {when}."},
}


def idle_seconds() -> float:
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO))
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000


def alerts(t: dict, ram_limit: int = 92) -> dict[str, str]:
    """What's wrong right now, by kind (kind = cooldown key)."""
    import psutil
    out = {}
    ram = psutil.virtual_memory().percent
    if ram >= ram_limit:
        top = max(psutil.process_iter(["name", "memory_info"]),
                  key=lambda p: p.info["memory_info"].rss if p.info["memory_info"] else 0)
        out["ram"] = t["ram"].format(n=round(ram), top=(top.info["name"] or "?").removesuffix(".exe"))
    for p in psutil.disk_partitions():
        try:
            free = psutil.disk_usage(p.mountpoint).free / 2**30
        except OSError:
            continue
        if free < 5:
            out["disk" + p.device[:1]] = t["disk"].format(d=p.device[:1], n=round(free, 1))
    battery = psutil.sensors_battery()
    if battery and not battery.power_plugged and battery.percent <= 15:
        out["battery"] = t["battery"].format(n=round(battery.percent))
    return out


def welcome(t: dict) -> str:
    text = t["back"].format(time=time.strftime("%H:%M"))
    try:
        last = json.loads((settings.DATA / "where.json").read_text(encoding="utf-8"))[-1]
        text += t["where"].format(app=last["program"])
    except (OSError, ValueError, IndexError, KeyError):
        pass
    if settings.load()["agent"]["kind"] == "openclaw":
        try:
            from .panel import automations
            soon = sorted((a for a in automations() if a["enabled"] and a["next"] and not a["internal"]),
                          key=lambda a: a["next"][3:5] + a["next"][:2] + a["next"][6:])  # dd/mm HH:MM -> mmddHH:MM
            if soon:
                text += t["reminder"].format(name=soon[0]["name"], when=soon[0]["next"])
        except Exception:  # noqa: BLE001 — the greeting works without it
            pass
    return text


def watch(speak: Callable[[str], None]) -> None:
    """Runs forever in a thread. speak() shows and says a line (and skips it if JARVIS is busy)."""
    last: dict[str, float] = {}
    was_away = False
    while True:
        time.sleep(15)
        s = settings.load()
        lang = "en" if s["speak_english"] or s["language"] not in TEXT else s["language"]
        t = TEXT[lang]
        try:
            idle = idle_seconds()
            away = s.get("away_minutes", 10) * 60  # tune it (1 = quick test)
            if idle > away:
                was_away = True
            elif was_away:  # you just came back
                was_away = False
                if s.get("welcome_back", True):
                    speak(welcome(t))
            if s.get("alerts", True) and idle < away:  # no one to warn if you're away
                for kind, text in alerts(t, s.get("ram_alert", 92)).items():
                    if time.time() - last.get(kind, 0) > COOLDOWN:
                        last[kind] = time.time()
                        speak(text)
        except Exception as e:  # noqa: BLE001 — never kill the thread
            print("proactive:", type(e).__name__, e)


if __name__ == "__main__":
    print("idle", round(idle_seconds()), "s |", alerts(TEXT["es"]) or "no alerts", "|", welcome(TEXT["es"]))
