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


def to_light() -> None:
    """Game time: grab the last talk from OpenClaw, close it, answer from one `claude`."""
    big = settings.load().get("agent_openclaw")
    if not big or where() == "light":
        return
    with _moving:
        recent = []
        try:
            from .panel import gateway
            h = gateway().call("chat.history", {"sessionKey": big["session"], "limit": 30})
            for m in (h.get("messages", h) if isinstance(h, dict) else h)[-30:]:
                c = m.get("content")
                text = " ".join(p.get("text", "") for p in c if p.get("type") == "text") if isinstance(c, list) else str(c or "")
                if text.strip() and m.get("role") in ("user", "assistant"):
                    recent.append(("ST: " if m["role"] == "user" else "JARVIS: ") + text.strip()[:400])
        except Exception as e:  # noqa: BLE001 — move anyway; his memory files still have the past
            print("house: couldn't read the last talk:", e)
        brain._cli.handoff = ("[You just moved to your light house (game mode: OpenClaw is closed to free RAM). Same you, "
                              "same files. This is what you and ST were just talking about:]\n" + "\n".join(recent[-20:]))
        brain._cli.log = []
        settings.save("agent", {**big, "kind": "claude-cli", "model": "claude-haiku-5-5",
                                "workspace": big.get("workspace") or str(Path.home() / "jarvis")})
        _gateway_procs()
        print(time.strftime("%H:%M:%S"), "house: moved to the light house")
    threading.Thread(target=brain._warm_cli, daemon=True).start()


def to_big() -> None:
    """Back from the game: start OpenClaw; he keeps answering from the light house until it's up, then moves home
    and leaves OpenClaw a note with what you talked about while you played."""
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
        time.sleep(10)
        if brain._cli.log:
            try:
                from .panel import gateway
                gateway().call("chat.inject", {"sessionKey": big["session"], "label": "light house", "message":
                               "[While ST played, you answered from your light house. What you talked about:]\n"
                               + "\n".join(brain._cli.log[-20:])[-6000:]})
            except Exception as e:  # noqa: BLE001
                print("house: couldn't hand the talk back:", e)
        settings.save("agent", big)
        brain._cli.stop()  # free its ~300 MB
        brain._cli.log = []
        print(time.strftime("%H:%M:%S"), "house: back home (OpenClaw)")


def follow_mode(mode: dict) -> None:
    """Called after a mode runs."""
    threading.Thread(target=to_light if mode.get("game") else to_big, daemon=True).start()
