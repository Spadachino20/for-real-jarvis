"""Two houses, one JARVIS. Same workspace (SOUL, USER, memory, skills); only the program he runs in changes.

  big   = OpenClaw (gateway, automatic memory, full panel)          ~1.6-2 GB
  light = one `claude` kept open by the orb (brain.ClaudeCLI)        ~300 MB

Game modes move him to the light house (OpenClaw is closed to free RAM); any other mode brings him home.
With settings "start_house": "light" he lives in the light house: he starts there when the PC does and goes to
OpenClaw only when you ask ("mudate a OpenClaw" / "switch to OpenClaw").
He takes the conversation with him both ways, so the move doesn't cut the thread.
Needs settings "agent_openclaw" (the OpenClaw agent config); without it there's only one house.
"""
from __future__ import annotations

import re
import subprocess
import threading
import time
from pathlib import Path

from . import brain, settings

GATEWAY_VBS = Path.home() / ".openclaw" / "gateway.vbs"
_moving = threading.Lock()
_stay = threading.Event()  # asked to stay light while he was on his way to OpenClaw
announce = None            # set by __main__: says one line when a move you asked for ends
GAME = "game mode, OpenClaw is closed to free RAM"


def _gateway_procs() -> None:
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process | ? { ($_.Name -eq 'node.exe' -and $_.CommandLine -like '*openclaw*') "
                    "-or ($_.Name -eq 'wscript.exe' -and $_.CommandLine -like '*gateway.vbs*') } | "
                    "% { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }"],
                   capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)


def where() -> str:
    return "light" if settings.load()["agent"]["kind"] == "claude-cli" else "big"


def openclaw_cli_session(key: str = "agent:main:main") -> str | None:
    """The `claude` conversation OpenClaw runs your main chat in (read straight from its database, no gateway)."""
    import json
    import sqlite3
    db = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "openclaw-agent.sqlite"
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        row = c.execute("select entry_json from session_nodes where session_key = ?", (key,)).fetchone()
        return (json.loads(row[0]).get("cliSessionIds") or {}).get("claude-cli") if row else None
    except Exception as e:  # noqa: BLE001
        print("house: couldn't read OpenClaw's session:", e)
        return None


def gateway_up() -> bool:
    import socket
    try:
        socket.create_connection(("127.0.0.1", 18789), timeout=2).close()
        return True
    except OSError:
        return False


def to_light(why: str = GAME) -> None:
    """Close OpenClaw and answer from one `claude` that RESUMES OpenClaw's own conversation:
    the same thread, the same memory, just a lighter house."""
    big = settings.load().get("agent_openclaw")
    if not big:
        return
    if where() == "light":
        if _moving.locked():
            _stay.set()  # he was on his way to OpenClaw: to_big closes it again
        return
    with _moving:
        if sid := openclaw_cli_session():
            (settings.DATA / "light-session.txt").write_text(sid)
        brain._cli.stop()
        brain._cli.handoff = f"[You are in your light house: {why}. Same you, same conversation.]"
        brain._cli.log = []
        settings.save("agent", {**big, "kind": "claude-cli", "model": "claude-haiku-5-5",
                                "workspace": big.get("workspace") or str(Path.home() / "jarvis")})
        _gateway_procs()
        print(time.strftime("%H:%M:%S"), "house: moved to the light house, conversation", sid)
    threading.Thread(target=brain._warm_cli, daemon=True).start()


def to_big() -> None:
    """Back from the game: start OpenClaw; he keeps answering from the light house until it's up. OpenClaw resumes
    the same `claude` conversation, so what you said while playing is already in it."""
    big = settings.load().get("agent_openclaw")
    if not big or where() == "big" or _moving.locked():
        return
    with _moving:
        _stay.clear()
        if not gateway_up():
            subprocess.Popen(["explorer.exe", str(GATEWAY_VBS)])  # outside any job: closing Claude won't take it down
        for _ in range(60):  # OpenClaw takes ~1 min to come up
            if gateway_up() or _stay.is_set():
                break
            time.sleep(5)
        else:
            print("house: OpenClaw didn't come up; staying in the light house")
            _tell("OpenClaw no levantó, señor. Sigo en la casa liviana.", "OpenClaw didn't come up, sir. I'm staying in the light house.")
            return
        if _stay.wait(20):  # else 20 s: let it finish loading before it gets questions
            _gateway_procs()
            print(time.strftime("%H:%M:%S"), "house: move cancelled, staying in the light house")
            return
        with brain._cli.lock:  # never mid-answer
            settings.save("agent", big)
            brain._cli.stop()  # free its ~300 MB; OpenClaw takes the conversation from here
            sid = settings.DATA / "light-session.txt"
            if sid.exists() and sid.read_text().strip() != openclaw_cli_session():  # he started a new conversation meanwhile
                brain.note(f"you two also talked in your light house; it's by day in {brain.TALKS} (read it if he refers to it)")
        brain._cli.log = []
        print(time.strftime("%H:%M:%S"), "house: back home (OpenClaw)")
    _tell("Ya estoy en OpenClaw, señor.", "I'm in OpenClaw now, sir.")


def _tell(es: str, en: str) -> None:
    s = settings.load()
    if announce:
        announce(en if s["speak_english"] or s["language"] != "es" else es)


def lives_light() -> bool:
    return settings.load().get("start_house") == "light"


def start() -> None:
    """When the orb starts: home is the light house (unless OpenClaw is already running: you asked for it earlier)."""
    if lives_light() and where() == "big" and not gateway_up():
        to_light("it's where you live now; OpenClaw is off and you move there only when he asks")


def follow_mode(mode: dict) -> None:
    """Called after a mode runs."""
    if mode.get("game"):
        threading.Thread(target=to_light, daemon=True).start()
    elif not lives_light():
        threading.Thread(target=to_big, daemon=True).start()


_CLAW = r"open\s*-?\s*(?:claw|clau|clou|clow|clo\b|crow|claude)\w*"  # and how the ears mishear it
_GO = (r"\b(?:m[uú]d|mov|muev|move|p[aá]s[aáeé]|cambi|volv|vuelv|vete|and[aá]\b|anda\b|ir\b|ve\b|us[aáeé]|[aá]br|activ|"
       r"pr[eé]nd|enc(?:end|iend|i[eé]nd)|con[eé]ct|go\b|switch|use\b|start)\w*")
_LEAVE = r"\b(?:cerr|cierr|ci[eé]rr|apag|ap[aá]g|sal\b|sal[ií]|deja|close|stop|quit|leave|turn off)\w*"


def wanted(text: str) -> str | None:
    """"big" / "light" if the text asks him to change houses, else None."""
    t = text.lower().strip(" ¿?¡!.,")
    t = re.sub(r"^(?:oye |hey )?jarvis\W+", "", t)
    if len(t.split()) > 12 or re.match(r"(?:no|qu[eé]|c[oó]mo|por qu[eé]|cu[aá]ndo|d[oó]nde|est[aá]|hay|sigue|what|how|why|when|is|are|don'?t)\b", t):
        return None
    big, light = re.search(_CLAW + r"|casa grande|big house", t), re.search(r"casa (?:liviana|ligera|chica)|light house", t)
    rest = re.sub(_CLAW, " ", t)  # "open" in its own name isn't a verb
    if light:
        return "light" if re.search(_GO, rest) else None
    if big:
        return "light" if re.search(_LEAVE, rest) else "big" if re.search(_GO, rest) else None
    return None


def move_reply(text: str, lang: str = "en") -> str | None:
    """Voice/chat shortcut: "mudate a OpenClaw", "volvé a la casa liviana", "cerrá OpenClaw"."""
    es = lang == "es"
    if not (to := wanted(text)) or not settings.load().get("agent_openclaw"):
        return None
    if to == "light":
        if where() == "light" and not _moving.locked():
            return "Ya estoy en la casa liviana, señor." if es else "I'm already in the light house, sir."
        brain.note("moved to the light house because he asked")
        threading.Thread(target=to_light, args=("he asked you to come back to it, OpenClaw is closed",), daemon=True).start()
        return "Vuelvo a la casa liviana, señor." if es else "Back to the light house, sir."
    if where() == "big":
        return "Ya estoy en OpenClaw, señor." if es else "I'm already in OpenClaw, sir."
    if _moving.locked():
        return "Ya me estoy mudando, señor." if es else "I'm already on my way, sir."
    brain.note("is moving to OpenClaw because he asked")
    threading.Thread(target=to_big, daemon=True).start()
    return ("Me mudo a OpenClaw, señor. Le aviso cuando esté ahí." if es
            else "Moving to OpenClaw, sir. I'll tell you when I'm there.")


if __name__ == "__main__":
    for t in ("Mudate a OpenClaw", "Jarvis, múdate a Open Claw.", "quiero que te mudes a openclaw", "pasate a open cloud", "volvé a la casa grande",
              "Usa OpenClaw", "switch to OpenClaw", "andá a openclaw por favor", "Muda a Open Claude"):
        assert wanted(t) == "big", t
    for t in ("volvé a la casa liviana", "Vuelve a la casa ligera", "cerrá OpenClaw", "apaga open claw", "go back to the light house"):
        assert wanted(t) == "light", t
    for t in ("qué es OpenClaw", "OpenClaw", "Open Claw.", "no te mudes a openclaw", "¿Cómo uso OpenClaw?", "abrí Discord", "poné el modo trabajo",
              "pasame la captura", "abre Claude", "está prendido openclaw"):
        assert wanted(t) is None, (t, wanted(t))
    print("house ok")
