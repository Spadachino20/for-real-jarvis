"""Settings: data/settings.json on top of these defaults. Everything personal lives in data/ (git-ignored)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FILE = DATA / "settings.json"
MODES = DATA / "modes.json"

DEFAULTS = {
    # Who JARVIS really is: your agent. "openclaw" (full panel) or "hermes" / "openai" (any OpenAI-compatible agent).
    "agent": {
        "kind": "openclaw",
        "url": "http://127.0.0.1:18789",       # Hermes: http://127.0.0.1:8642
        "model": "openclaw/main",              # Hermes: hermes-agent
        "session": "agent:main:main",          # OpenClaw session the orb shares with the Control UI
        "token": "",                           # empty + openclaw = read from ~/.openclaw/openclaw.json
        "restart_command": "",                 # optional: run when the agent is down (e.g. a scheduled task)
    },
    "language": "en",                          # "en" or "es": what you speak and the panel's language
    "speak_english": True,                     # spoken answers in English even if you speak another language
    "voice": "bm_lewis",                       # Kokoro voice, or "elevenlabs:<name>" with data/elevenlabs.key
    "microphone": "",                          # part of the device name; empty = Windows default
    "output": "",                              # part of the device name; empty = Windows default
    "hotkey": "ctrl+shift+j",                  # press = saying "Jarvis"
    "whatsapp_contacts": [],                   # names JARVIS may message by voice ("tell Ana I'm late"), always asking first
    "interruptible": True,                     # keep the mic on while JARVIS talks so you can cut him off (headphones)
    "orb_gain": 8.0,                           # how much the orb rings open with the volume
    "whisper_model": "small",                  # "large-v3-turbo" understands more in noise, slower on CPU
    "vocabulary": "Jarvis, Spotify, YouTube, Chrome, WhatsApp, OpenClaw, Claude.",
    # How your agent knows a message came from the mic. Self-explaining, so no agent setup is needed.
    "voice_tags": {"spoken": "[VOICE: read aloud - answer in 1-2 short sentences, no lists or markdown] ",
                   "spoken_english": "[VOICE: read aloud in English - answer in English, 1-2 short sentences, no lists or markdown] "},
}


def _merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load() -> dict:
    try:
        return _merge(DEFAULTS, json.loads(FILE.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError):
        return _merge(DEFAULTS, {})


def save(key: str, value) -> None:
    try:
        current = json.loads(FILE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        current = {}
    current[key] = value
    DATA.mkdir(exist_ok=True)
    FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


IDENTITY = DATA / "identity.json"  # your agent writes it (jarvis-personalize skill); delete it to go back to JARVIS


def identity() -> dict:
    """Who the orb shows: {"name": "F.R.I.D.A.Y.", "letter": "F", "color": "#ff8a3d"} from data/identity.json.
    Also the short name (FRIDAY) and the words that wake it (its name + "jarvis", always)."""
    import re
    try:
        ident = json.loads(IDENTITY.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        ident = {}
    short = re.sub(r"[^A-Za-z0-9 ]", "", ident.get("name") or "JARVIS").strip() or "JARVIS"
    color = ident.get("color") or "#38e1ff"
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = "#38e1ff"
    wake = {"jarvis", short.lower(), *[w.lower() for w in ident.get("wake") or []]}
    return {"name": ident.get("name") or "J.A.R.V.I.S.", "short": short.upper(),
            "letter": (ident.get("letter") or short[0]).upper()[:1], "color": color, "wake": sorted(wake)}


def modes() -> list[dict]:
    """Your modes (data/modes.json). The repo ships none: JARVIS builds them with you."""
    try:
        return json.loads(MODES.read_text(encoding="utf-8-sig")).get("modes", [])
    except (OSError, ValueError):
        return []


if __name__ == "__main__":
    assert _merge({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}}) == {"a": {"b": 1, "c": 3}}
    i = identity()
    assert i["letter"] and i["color"].startswith("#") and "jarvis" in i["wake"]
    print("settings ok:", load()["agent"]["kind"], i["short"], i["color"])
