"""The panel: http://127.0.0.1:18790, served from inside the orb.

Reads from two places: the PC (psutil, pc.ps1, the orb's log) and your agent (chat; with OpenClaw also tokens,
automations, sessions and logs through its gateway, see gateway.py).
Buttons (modes, chat, agent tasks, automations) require a key generated on every start that only travels inside
the page served here, plus Host/Origin checks: a website open in your browser can't press them.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from . import brain, settings

PORT = 18790
LOG = settings.DATA / "jarvis.log"
PC_PS1 = settings.ROOT / "skills" / "jarvis-pc" / "pc.ps1"
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
KEY = secrets.token_urlsafe(24)  # one per orb start
HERE = Path(__file__).parent

# What the panel's buttons ask your agent to do. The skills (skills/) teach the agent how.
TASKS = {
    "personalize": "[PANEL] The user pressed 'Personalize JARVIS'. Run your jarvis-personalize skill now: start the "
                   "interview with its first question. Remember: you keep your current personality unless they say otherwise.",
    "create-mode": "[PANEL] The user pressed 'Create a mode'. Run your jarvis-modes skill now and start with its first question.",
}

_cache: dict[str, tuple[float, object]] = {}
_gateway = None
_mode = {"name": None, "state": "free", "result": "", "time": "", "active": None}
_chat = {"waiting": False, "error": ""}


def kind() -> str:
    return settings.load()["agent"]["kind"]


def gateway():
    global _gateway
    if _gateway is None:
        from .gateway import Gateway
        _gateway = Gateway()
    return _gateway


def _cached(key: str, sec: float, compute: Callable[[], object]) -> object:
    """Expensive things are recomputed at most every `sec`. A broken source returns {"error": …} and the rest lives on."""
    when, value = _cache.get(key, (0.0, None))
    if time.time() - when > sec:
        try:
            value = compute()
        except Exception as e:  # noqa: BLE001
            value = {"error": f"{type(e).__name__}: {e}"[:240]}
        _cache[key] = (time.time(), value)
    return value


def _ps(*args: str, timeout: int = 20) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PC_PS1), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    return r.stdout.strip()


def _when(ms: float | None, fmt: str = "%d/%m %H:%M") -> str:
    return time.strftime(fmt, time.localtime(ms / 1000)) if ms else ""


# ---------- the PC ----------

def timings(n: int = 14) -> list[dict]:
    """From the orb's log: "18:35:12 timings voice: understand 1.2s | agent 4.2s | speak 6.6s"."""
    pattern = re.compile(r"^(\d\d:\d\d):\d\d timings (\w+): understand ([\d.]+)s \| agent ([\d.]+)s \| speak ([\d.]+)s")
    try:
        lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
    except OSError:
        return []
    rows = [m.groups() for m in map(pattern.match, lines) if m]
    return [{"time": h, "via": v, "understand": float(u), "agent": float(a), "speak": float(s)} for h, v, u, a, s in rows[-n:]]


def music() -> dict:
    text = _ps("music", "status", timeout=10)
    m = re.match(r"^(\w+) (playing|paused|stopped): (.*?) - (.*)$", text)
    if not m:
        return {"text": text or "Nothing playing"}
    app, state, artist, title = m.groups()
    return {"app": app, "state": state, "artist": artist, "title": title}


def pc() -> dict:
    import psutil
    disks = []
    for p in psutil.disk_partitions():
        try:
            u = psutil.disk_usage(p.mountpoint)
            disks.append({"letter": p.device[:2], "free_gb": round(u.free / 2**30), "pct": u.percent})
        except OSError:
            continue
    procs = sorted(psutil.process_iter(["name", "memory_info"]),
                   key=lambda p: p.info["memory_info"].rss if p.info["memory_info"] else 0, reverse=True)[:6]
    ram = psutil.virtual_memory()
    return {"cpu": psutil.cpu_percent(interval=0.3), "ram_pct": ram.percent,
            "ram_used": round(ram.used / 2**30, 1), "ram_total": round(ram.total / 2**30, 1),
            "since": time.strftime("%d/%m %H:%M", time.localtime(psutil.boot_time())), "disks": disks,
            "processes": [{"name": p.info["name"], "mb": round(p.info["memory_info"].rss / 2**20)} for p in procs]}


def crashes() -> dict:
    """Blue screens (1001), hard shutdowns (41) and corrected hardware errors (WHEA 19) in 30 days."""
    script = (
        "$e = Get-WinEvent -FilterHashtable @{LogName='System'; Id=41,1001,19; StartTime=(Get-Date).AddDays(-30)} -ErrorAction SilentlyContinue | "
        "? { ($_.Id -ne 1001 -or $_.ProviderName -match 'WER') -and ($_.Id -ne 19 -or $_.ProviderName -match 'WHEA') }; "
        "$e | % { [pscustomobject]@{ id = $_.Id; when = $_.TimeCreated.ToString('dd/MM HH:mm'); "
        "code = [regex]::Match($_.Message, '0x[0-9a-fA-F]{8,}').Value } } | ConvertTo-Json -Compress")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    events = json.loads(r.stdout) if r.stdout.strip() else []
    events = events if isinstance(events, list) else [events]
    return {"bluescreens": [e for e in events if e["id"] == 1001],
            "shutdowns": sum(e["id"] == 41 for e in events), "hardware": sum(e["id"] == 19 for e in events)}


def orb_log(n: int = 40) -> list[str]:
    try:
        return LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []


def modes() -> list[dict]:
    return [{"id": m.get("id"), "title": m.get("title") or m.get("id"), "description": m.get("description", ""),
             "icon": m.get("icon", "bolt"), "confirm": m.get("confirm", ""), "sticky": bool(m.get("exit_message"))}
            for m in settings.modes() if m.get("id")]


# ---------- your agent ----------

def main_session() -> dict:
    """OpenClaw main session: model, context used and whether it's working right now."""
    session = settings.load()["agent"]["session"]
    for s in gateway().call("sessions.list", {"limit": 30, "sortBy": "activity"}).get("sessions", []):
        if s.get("key") == session:
            return {"model": s.get("model"), "context": s.get("totalTokens") or 0,
                    "context_max": s.get("contextTokens") or 0, "working": bool(s.get("hasActiveRun"))}
    return {}


def _session_name(key: str, label: str | None = None) -> str:
    if label:
        return label
    if key == settings.load()["agent"]["session"]:
        return "Main (orb and panel)"
    m = re.search(r"(whatsapp|telegram|discord|signal):direct:(\S+)", key)
    if m:
        return f"{m.group(1).title()} {m.group(2)}"
    return re.sub(r"^agent:[^:]+:(explicit:)?", "", key)


def tokens() -> dict:
    g = gateway()
    cost = g.call("usage.cost", {"days": 30}, timeout=40)
    sessions = g.call("sessions.usage", {"limit": 60}, timeout=40).get("sessions", [])
    by_model: dict[str, int] = {}
    rows = []
    for s in sessions:
        u = s.get("usage") or {}
        for m in u.get("modelUsage") or []:
            name = f"{m.get('provider', '')}/{m.get('model', '')}".strip("/") or "unknown"
            by_model[name] = by_model.get(name, 0) + int((m.get("totals") or m).get("totalTokens") or 0)
        counts = u.get("messageCounts") or {}
        rows.append({"session": _session_name(s.get("key", ""), s.get("label")), "tokens": u.get("totalTokens") or 0,
                     "cost": u.get("totalCost") or 0, "messages": counts.get("total", 0), "errors": counts.get("errors", 0)})
    rows.sort(key=lambda r: r["tokens"], reverse=True)
    t, today = cost.get("totals", {}), time.strftime("%Y-%m-%d")
    return {"total": t.get("totalTokens", 0), "input": t.get("input", 0), "output": t.get("output", 0),
            "cache": t.get("cacheRead", 0), "cost": round(t.get("totalCost", 0), 2),
            "today": next((d["totalTokens"] for d in cost.get("daily", []) if d["date"] == today), 0),
            "daily": [{"date": d["date"][5:], "tokens": d["totalTokens"]} for d in cost.get("daily", [])],
            "sessions": rows[:10],
            "models": sorted(({"model": k, "tokens": v} for k, v in by_model.items() if v), key=lambda x: -x["tokens"])}


def automations() -> list[dict]:
    out = []
    for j in gateway().call("cron.list", {"includeDisabled": True}).get("jobs", []):  # without it, paused ones vanish
        st, h = j.get("state") or {}, j.get("schedule") or {}
        every = {"every": f"every {round(h.get('everyMs', 0) / 60000)} min", "cron": f"cron {h.get('expr', '')}",
                 "at": "once"}.get(h.get("kind"), h.get("kind", ""))
        out.append({"id": j["id"], "name": re.sub(r"^(Reminder|Recordatorio):\s*", "", j.get("displayName") or j.get("name") or ""),
                    "enabled": j.get("enabled", False), "every": every,
                    "next": _when(st.get("nextRunAtMs") or j.get("nextRunAtMs")), "last": _when(st.get("lastRunAtMs")),
                    "status": st.get("lastStatus") or "", "channel": (j.get("delivery") or {}).get("channel") or "",
                    "internal": (j.get("declarationKey") or "").startswith(("heartbeat:", "memory-core"))})
    return out


def sessions() -> list[dict]:
    return [{"name": _session_name(s.get("key", ""), s.get("displayName") or s.get("label")), "model": s.get("model") or "",
             "tokens": s.get("totalTokens") or 0, "active": bool(s.get("hasActiveRun")),
             "last": _when(s.get("lastActivityAt") or s.get("updatedAt"))}
            for s in gateway().call("sessions.list", {"limit": 40, "sortBy": "activity"}).get("sessions", [])]


def chat() -> list[dict]:
    if kind() != "openclaw":  # other agents: the conversation the orb itself keeps
        return [{"role": m["role"], "text": m["content"], "tools": [], "time": ""} for m in brain._history[-40:]]
    out = []
    for m in gateway().call("chat.history", {"sessionKey": settings.load()["agent"]["session"], "limit": 40}).get("messages", []):
        parts = m.get("content") if isinstance(m.get("content"), list) else [{"type": "text", "text": m.get("content", "")}]
        text = " ".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
        tools = [p.get("name", "").replace("mcp__openclaw__", "") for p in parts if p.get("type") == "toolcall"]
        if text or tools:
            out.append({"role": m.get("role"), "text": text, "tools": tools, "time": _when(m.get("timestamp"), "%H:%M")})
    return out


def logs() -> dict:
    lines = []
    for raw in gateway().call("logs.tail", {"limit": 60}).get("lines", []):
        try:
            d = json.loads(raw)
        except ValueError:
            lines.append({"time": "", "level": "", "source": "", "text": raw[:300]})
            continue
        meta, source = d.get("_meta") or {}, d.get("0", "")
        try:
            source = " ".join(str(v) for v in json.loads(source).values()) if source.startswith("{") else source
        except ValueError:
            pass
        text = d.get("1")
        text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
        stamp = meta.get("date", "")
        try:
            from datetime import datetime
            stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")
        except ValueError:
            pass
        lines.append({"time": stamp, "level": meta.get("logLevelName", ""), "source": source[:40], "text": text[:300]})
    return {"gateway": lines[::-1]}


# ---------- actions (POST with the key only) ----------

def _in_thread(f: Callable[[], None]) -> None:
    threading.Thread(target=f, daemon=True).start()


_MODE_WORDS = {"modo", "mode", "juguemos", "jugar", "jugamos", "lets", "let's", "play", "activa", "activar", "pon", "pone", "poné", "el", "la", "de", "a", "al", "jarvis", "hey", "on"}


def mode_for(text: str) -> dict | None:
    """'modo forza' / 'juguemos f1' / 'work mode' -> that mode, right here: no agent, no tokens, can't fail halfway."""
    import difflib
    import unicodedata
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9']+", plain)
    if not words or len(words) > 6 or {"salir", "sal", "exit", "leave", "quit", "crea", "crear", "create"} & set(words) or not {"modo", "mode", "juguemos", "jugamos", "play"} & set(words):
        return None
    rest = " ".join(w for w in words if w not in _MODE_WORDS)
    names = {}
    for m in settings.modes():
        for n in (m.get("id"), m.get("title")):
            if n:
                names[unicodedata.normalize("NFKD", n.lower()).encode("ascii", "ignore").decode()] = m
    hit = difflib.get_close_matches(rest, names, n=1, cutoff=0.6)
    return names[hit[0]] if hit else None


def run_mode(mode_id: str, leaving: bool = False) -> str | None:
    mode = next((m for m in settings.modes() if m.get("id") == mode_id), None)
    if mode is None:
        return "Unknown mode."
    if _mode["state"] == "running":
        return "A mode is already running."

    def work() -> None:
        _mode.update(name=mode.get("title") or mode_id, state="running", result="", time=time.strftime("%H:%M"))
        try:
            if leaving:
                result = "JARVIS: " + brain.ask("[PANEL] " + mode["exit_message"], timeout=120)
                _mode["active"] = None
            else:
                result = _ps("mode", mode_id, timeout=120)
                if mode.get("tell_agent"):
                    result += "\nJARVIS: " + brain.ask("[PANEL] " + mode["tell_agent"], timeout=120)
                _mode["active"] = mode_id if mode.get("exit_message") else _mode["active"]
            _mode.update(state="done", result=result)
        except Exception as e:  # noqa: BLE001
            _mode.update(state="error", result=f"{type(e).__name__}: {e}"[:300])

    _in_thread(work)
    return None


def send_chat(text: str) -> str | None:
    if _chat["waiting"]:
        return "JARVIS is still answering your last message."

    def work() -> None:
        _chat.update(waiting=True, error="")
        try:
            brain.ask(text)
        except Exception as e:  # noqa: BLE001
            _chat["error"] = f"{type(e).__name__}: {e}"[:200]
        finally:
            _chat["waiting"] = False
            _cache.pop("chat", None)

    _in_thread(work)
    return None


def automation(job_id: str, action: str) -> str | None:
    g = gateway()
    if action == "run":
        g.call("cron.run", {"id": job_id})
    elif action in ("pause", "resume"):
        g.call("cron.update", {"id": job_id, "patch": {"enabled": action == "resume"}})
    else:
        return "Unknown action."
    _cache.pop("automations", None)
    return None


# ---------- server ----------

# ---------- control: model, music, quick actions, settings ----------

OPENCLAW_JSON = Path.home() / ".openclaw" / "openclaw.json"
TOGGLES = ("speak_english", "interruptible")


def models() -> dict:
    """OpenClaw: the primary model and the ones its allowlist lets you pick. Others: read-only."""
    if kind() != "openclaw":
        return {"current": settings.load()["agent"].get("model", ""), "allowed": [], "fallbacks": [], "can_set": False}
    d = json.loads(OPENCLAW_JSON.read_text(encoding="utf-8-sig"))["agents"]["defaults"]
    model = d.get("model", {})
    allowed = d.get("modelPolicy", {}).get("allow") or sorted(k for k in d.get("models", {}) if "*" not in k)
    return {"current": model.get("primary", ""), "fallbacks": model.get("fallbacks", []), "allowed": allowed, "can_set": True}


def control_info() -> dict:
    s = settings.load()
    return {"models": _cached("models", 10, models), "settings": {k: bool(s[k]) for k in TOGGLES},
            "restart": bool(s["agent"].get("restart_command"))}


def control(action: str, value: str) -> str | None:
    """Buttons of the Control section. Returns an error, or None."""
    if action == "model":
        info = models()
        if not info["can_set"] or value not in info["allowed"]:
            return "That model isn't in your agent's allowed list."
        r = subprocess.run(["openclaw.cmd", "config", "set", "agents.defaults.model.primary", value], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
        _cache.pop("models", None); _cache.pop("main", None)
        return None if r.returncode == 0 else (r.stderr or r.stdout).strip()[-240:] or "openclaw config set failed."
    if action == "music" and value in ("play", "pause", "next", "previous"):
        _in_thread(lambda: (_ps("music", value), _cache.pop("music", None)))
    elif action == "volume" and value in ("up", "down", "mute"):
        _ps("volume", value)
    elif action == "setting" and value in TOGGLES:
        settings.save(value, not settings.load()[value])
    elif action == "restart_agent":
        brain._last_restart = 0.0
        return None if brain.restart() else "Set agent.restart_command in data/settings.json first."
    elif action == "screenshot":
        _in_thread(lambda: os.startfile(_ps("screenshot")))
    elif action == "folder":
        os.startfile(settings.DATA)
    else:
        return "Unknown action."
    return None


def status(orb: Callable[[], dict]) -> dict:
    up = _cached("agent", 5, brain.alive)
    return {"now": time.strftime("%H:%M:%S"), "agent": up, "kind": kind(), "orb": orb(),
            "main": _cached("main", 6, main_session) if up and kind() == "openclaw" else {},
            "timings": _cached("timings", 3, timings), "music": _cached("music", 8, music),
            "pc": _cached("pc", 5, pc), "crashes": _cached("crashes", 300, crashes),
            "modes": modes(), "mode": _mode, "chat": _chat}


OPENCLAW_ONLY = {"/api/tokens": ("tokens", 60, tokens), "/api/automations": ("automations", 8, automations),
                 "/api/sessions": ("sessions", 10, sessions), "/api/logs": ("logs", 4, logs)}
ICONS = {"/static/orb-192.png": (192, False), "/static/orb-512.png": (512, False),
         "/static/orb-maskable.png": (512, True), "/static/orb.ico": (0, False), "/favicon.ico": (0, False)}


def start(orb: Callable[[], dict]) -> str | None:
    """Starts the panel in a thread. Returns its URL, or None if the port is busy."""
    page = HERE / "panel.html"  # read on every visit: editing it doesn't need an orb restart

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8") -> None:
            try:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Frame-Options", "DENY")
                self.end_headers()
                self.wfile.write(body)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass  # the browser left mid-answer

        def _json(self, data, code: int = 200) -> None:
            self._send(code, json.dumps(data, ensure_ascii=False).encode())

        def do_GET(self) -> None:  # noqa: N802
            if self.headers.get("Host") not in HOSTS:  # odd names pointing to 127.0.0.1 (DNS rebinding)
                return self._json({"error": "host"}, 403)
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                ident = settings.identity()
                html = page.read_text(encoding="utf-8").replace("__KEY__", KEY).replace("__LANG__", settings.load()["language"])
                for k in ("name", "short", "letter", "color"):
                    html = html.replace(f"__{k.upper()}__", ident[k])
                return self._send(200, html.encode(), "text/html; charset=utf-8")
            if path in ICONS:  # the orb icon in your agent's letter and color
                from .icon import draw, ico
                ident = settings.identity()
                if path.endswith(".ico"):
                    return self._send(200, ico(ident["letter"], ident["color"]), "image/x-icon")
                size, maskable = ICONS[path]
                return self._send(200, draw(ident["letter"], ident["color"], size, maskable), "image/png")
            if path == "/static/manifest.webmanifest":
                ident = settings.identity()
                manifest = json.loads((HERE / "static" / "manifest.webmanifest").read_text(encoding="utf-8"))
                manifest.update(name=ident["name"], short_name=ident["short"])
                return self._send(200, json.dumps(manifest).encode(), "application/manifest+json")
            if path == "/api/orblog":
                return self._json(orb_log()[::-1])
            if path == "/api/status":
                return self._json(status(orb))
            if path == "/api/control":
                return self._json(control_info())
            if path == "/api/chat":
                return self._json(_cached("chat", 2, chat) if _cached("agent", 5, brain.alive) else {"error": "agent_down"})
            if path in OPENCLAW_ONLY:
                if kind() != "openclaw":
                    return self._json({"error": "openclaw_only"})
                if not _cached("agent", 5, brain.alive):
                    return self._json({"error": "agent_down"})
                return self._json(_cached(*OPENCLAW_ONLY[path]))
            self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            origin = self.headers.get("Origin")
            if (self.headers.get("Host") not in HOSTS or (origin and origin.split("//")[-1] not in HOSTS)
                    or not secrets.compare_digest(self.headers.get("X-Jarvis-Key", ""), KEY)):
                return self._json({"error": "forbidden"}, 403)
            try:
                size = min(int(self.headers.get("Content-Length") or 0), 20000)
                data = json.loads(self.rfile.read(size) or b"{}")
                path = self.path.split("?")[0]
                if path == "/api/mode":
                    error = run_mode(str(data.get("id", "")), bool(data.get("leave")))
                elif path == "/api/chat":
                    text = str(data.get("text", "")).strip()[:4000]
                    m = mode_for(text) if text else None
                    error = run_mode(m["id"]) if m else (send_chat(text) if text else "Empty message.")
                elif path == "/api/control":
                    error = control(str(data.get("action", "")), str(data.get("value", "")))
                elif path == "/api/task":
                    task = TASKS.get(str(data.get("task", "")))
                    error = send_chat(task) if task else "Unknown task."
                elif path == "/api/automation":
                    error = automation(str(data.get("id", "")), str(data.get("action", ""))) if kind() == "openclaw" else "OpenClaw only."
                else:
                    return self._json({"error": "not found"}, 404)
            except Exception as e:  # noqa: BLE001
                error = f"{type(e).__name__}: {e}"[:240]
            self._json({"ok": not error, "error": error})

        def log_message(self, *_args) -> None:  # no noise in the log
            pass

    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        print(f"Panel: couldn't open port {PORT}: {e}")
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{PORT}"


if __name__ == "__main__":  # self-test of every read (presses no buttons)
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    reads = [("pc", pc), ("crashes", crashes), ("modes", modes)]
    if brain.alive() and kind() == "openclaw":
        reads += [("main", main_session), ("tokens", tokens), ("automations", automations), ("sessions", sessions),
                  ("chat", chat), ("logs", logs)]
    for name, f in reads:
        t0 = time.time()
        value = f()
        print(f"{name:12} {time.time() - t0:4.1f}s", json.dumps(value, ensure_ascii=False)[:160])
    assert _session_name("agent:main:whatsapp:direct:+100") == "Whatsapp +100"
    print("panel ok")
