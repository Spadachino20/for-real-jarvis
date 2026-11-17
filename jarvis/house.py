"""Two houses, one JARVIS. Same workspace (SOUL, USER, memory, skills); only the program he runs in changes.

  big   = OpenClaw (gateway, automatic memory, full panel)          ~1.6-2 GB
  light = one `claude` kept open by the orb (brain.ClaudeCLI)        ~300 MB

Game modes move him to the light house (OpenClaw is closed to free RAM); any other mode brings him home.
He takes the conversation with him both ways, so the move doesn't cut the thread.
Needs settings "agent_openclaw" (the OpenClaw agent config); without it there's only one house.
"""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from . import brain, settings

GATEWAY_VBS = Path.home() / ".openclaw" / "gateway.vbs"
_moving = threading.Lock()


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


def to_light() -> None:
    """Game time: close OpenClaw and answer from one `claude` that RESUMES OpenClaw's own conversation:
    the same thread, the same memory, just a lighter house."""
    big = settings.load().get("agent_openclaw")
    if not big or where() == "light":
        return
    with _moving:
        if sid := openclaw_cli_session():
            (settings.DATA / "light-session.txt").write_text(sid)
        brain._cli.stop()
        brain._cli.handoff = "[You moved to your light house: game mode, OpenClaw is closed to free RAM. Same you, same conversation.]"
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
        subprocess.Popen(["explorer.exe", str(GATEWAY_VBS)])  # outside any job: closing Claude won't take it down
        import socket
        for _ in range(60):  # OpenClaw takes ~1 min to come up
            try:
                socket.create_connection(("127.0.0.1", 18789), timeout=2).close()
                break
            except OSError:
                time.sleep(5)
        else:
            print("house: OpenClaw didn't come up; staying in the light house")
            return
        time.sleep(20)  # let it finish loading before it gets questions
        with brain._cli.lock:  # never mid-answer
            settings.save("agent", big)
            brain._cli.stop()  # free its ~300 MB; OpenClaw takes the conversation from here
        brain._cli.log = []
        print(time.strftime("%H:%M:%S"), "house: back home (OpenClaw)")


def follow_mode(mode: dict) -> None:
    """Called after a mode runs."""
    threading.Thread(target=to_light if mode.get("game") else to_big, daemon=True).start()
