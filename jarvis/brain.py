"""The brain is YOUR agent (OpenClaw or Hermes). The orb is only a door: there is no second brain here.

Both speak the OpenAI chat-completions API on localhost. OpenClaw keeps the conversation in one session
(the same one its Control UI shows); for other agents the orb sends the last few turns itself.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from pathlib import Path

from . import settings

SCREENSHOT = settings.DATA / "screen.jpg"
# "look at my screen", "what do you see", "mirá mi pantalla", "fijate", "¿qué ves?"
_WANTS_SCREEN = re.compile(r"\b(screen|look at|what do you see|pantalla|mir[aá](me|lo|la)?|fij[aá]te|qu[eé] ves|est[aá]s viendo)\b", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
DOWN = {"en": "Your agent isn't answering, sir. I'm trying to bring it back: give it a minute and ask again.",
        "es": "Tu agente no responde, señor. Lo estoy levantando: dame un minuto y volvé a preguntar."}


def _agent() -> dict:
    return settings.load()["agent"]


def token() -> str:
    a = _agent()
    if a.get("token"):
        return a["token"]
    if a["kind"] == "openclaw":  # read on every call, never stored or printed
        config = json.loads(Path.home().joinpath(".openclaw", "openclaw.json").read_text(encoding="utf-8"))
        return config["gateway"]["auth"]["token"]
    return ""


def _headers(session: str | None = None) -> dict:
    a, h = _agent() | ({"session": session} if session else {}), {}
    if t := token():
        h["Authorization"] = f"Bearer {t}"
    if a["kind"] == "openclaw":
        h["x-openclaw-session-key"] = a["session"]
    elif a["kind"] == "hermes":  # Hermes keeps the conversation itself when given a session id
        h["X-Hermes-Session-Id"] = a["session"] if a["session"] != "agent:main:main" else "for-real-jarvis"
    return h


STOPPED = threading.Event()  # you cut him off (fist): no retry, no "agent down"
CHAT_TAG = "[CHAT - typed, not spoken: markdown is fine] "  # so the agent tells typing from voice
_notes: list[str] = []  # what the orb did by itself since the agent's last message (he'd deny it otherwise)
_history: list[dict] = []  # what the panel's chat shows for non-OpenClaw agents (and the context for plain "openai" ones)


def note(text: str) -> None:
    _notes.append(f"{time.strftime('%H:%M')} {text}")


def _with_notes(text: str) -> str:
    if not _notes:
        return text
    pre = "[Meanwhile the orb did this by itself, without asking you: " + "; ".join(_notes) + ". It was real; own it if he asks.] "
    _notes.clear()
    return pre + text


def _messages(content) -> list[dict]:
    if _agent()["kind"] in ("openclaw", "hermes"):  # the server already has the conversation
        return [{"role": "user", "content": content}]
    return _history[-8:] + [{"role": "user", "content": content}]


def _remember(content, answer: str) -> None:
    if _agent()["kind"] != "openclaw" and answer:
        text = content if isinstance(content, str) else content[0]["text"]
        _history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": answer}])


def capture() -> Path:
    from PIL import ImageGrab
    image = ImageGrab.grab()
    image.thumbnail((1600, 1600))
    SCREENSHOT.parent.mkdir(exist_ok=True)
    image.convert("RGB").save(SCREENSHOT, quality=80)
    return SCREENSHOT


def with_screen(text: str) -> str | list:
    """If you ask JARVIS to look at your screen, attach a fresh screenshot."""
    if not _WANTS_SCREEN.search(text):
        return text
    try:
        import base64
        data = base64.b64encode(capture().read_bytes()).decode()
    except Exception as e:  # noqa: BLE001 — answer anyway
        print("couldn't capture the screen:", e)
        return text
    return [{"type": "text", "text": text + "\n(Attached: a screenshot of my screen taken just now.)"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + data}}]


LOGIN = {"en": "My login has expired, sir. Run claude auth login in a terminal, then ask me again.",
         "es": "Se me venció el inicio de sesión, señor. Corré claude auth login en una terminal y preguntame de nuevo."}


def _line(which: dict) -> str:
    s = settings.load()
    return which["en"] if s["speak_english"] else which.get(s["language"], which["en"])


class ClaudeCLI:
    """agent kind "claude-cli": ONE `claude` kept open (stream-json), so there's no gateway in between.
    ~300 MB, first word in ~1.3 s; it starts once (~10 s). Works in agent.workspace (your SOUL/USER/AGENTS, skills)."""

    def __init__(self) -> None:
        self.proc, self.lock, self.started = None, threading.Lock(), False
        self.handoff: str | None = None  # what you were just talking about in the other house (house.py)
        self.log: list[str] = []  # what was said here, handed back when he moves home

    def _start(self):
        import shutil
        a = _agent()
        cmd = [shutil.which("claude") or "claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json",
               "--verbose", "--include-partial-messages", "--model", a["model"] if str(a.get("model", "")).startswith("claude") else "claude-haiku-5-5",
               "--dangerously-skip-permissions"]
        if not a.get("full_claude"):  # only his workspace: your own MCP servers, plugins and hooks made every answer ~2.5 s slower
            cmd += ["--strict-mcp-config", "--setting-sources", "project,local", "--settings", '{"disableAllHooks": true}']
        # its OWN conversation, kept across restarts (--continue could pick up OpenClaw's, which runs claude in the same folder)
        import uuid
        sid_file = settings.DATA / "light-session.txt"
        if sid_file.exists():
            cmd += ["--resume", sid_file.read_text().strip()]
        else:
            sid = str(uuid.uuid4())
            sid_file.write_text(sid)
            cmd += ["--session-id", sid]
        self.started = True
        self.proc = subprocess.Popen(cmd, cwd=a.get("workspace") or None, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=open(settings.DATA / "claude-cli.log", "a", encoding="utf-8"), text=True,
                                     encoding="utf-8", bufsize=1,
                                     creationflags=subprocess.CREATE_NO_WINDOW)

    def stop(self) -> None:
        """Kills the current answer (and whatever tool it was running); the next question starts a fresh one."""
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None

    def stream(self, content):
        if isinstance(content, list):  # text + screenshot (OpenAI shape) -> Anthropic blocks
            content = [{"type": "text", "text": b["text"]} if b["type"] == "text" else
                       {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": b["image_url"]["url"].split(",", 1)[1]}} for b in content]
        said = content if isinstance(content, str) else content[0]["text"]
        if self.handoff:
            note, self.handoff = self.handoff, None
            content = note + "\n\n" + content if isinstance(content, str) else [{"type": "text", "text": note}] + content
        answer = []
        if not self.lock.acquire(timeout=20):  # an old answer never finished (abandoned): kill it and go on
            print(time.strftime("%H:%M:%S"), "light house: previous answer stuck, restarting claude")
            self.stop()
            self.lock.acquire(timeout=10)
        try:
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            msg = json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + "\n"
            try:
                self.proc.stdin.write(msg)
                self.proc.stdin.flush()
            except OSError:  # it was closed under us (a mode killed it?): a new one, same conversation
                self._start()
                self.proc.stdin.write(msg)
                self.proc.stdin.flush()
            proc = self.proc
            for line in proc.stdout:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("type") == "stream_event":
                    d = e["event"].get("delta") or {}
                    if d.get("type") == "text_delta" and d.get("text"):
                        answer.append(d["text"])
                        yield d["text"]
                elif e.get("type") == "result":
                    if e.get("is_error") and re.search(r"authenticat|log ?in|oauth|401", str(e.get("result")), re.I):
                        print(time.strftime("%H:%M:%S"), "light house:", str(e.get("result"))[:120])
                        self.stop()  # a logged-out claude stays logged out: the next question opens a new one
                        if not answer:
                            answer.append(_line(LOGIN))
                            yield answer[0]
                    break
            if not "".join(answer).strip().startswith("NO_REPLY"):  # overheard, not for him
                self.log.append(f"ST: {said}\nJARVIS: {''.join(answer).strip()}")
        finally:
            if self.lock.locked():
                self.lock.release()


_cli = ClaudeCLI()


def _warm_cli() -> None:
    """Open the light house's `claude` now (~10 s), so the first question is fast."""
    with _cli.lock:
        if _cli.proc is None or _cli.proc.poll() is not None:
            _cli._start()


def ask(content, timeout: int = 300, session: str | None = None) -> str:
    """session: another conversation of your agent (background tasks), so the main one stays free."""
    import httpx
    a = _agent()
    if a["kind"] == "claude-cli":
        if session:  # a side task: its own one-shot claude, the main one stays free
            text = content if isinstance(content, str) else content[0]["text"]
            import shutil
            r = subprocess.run([shutil.which("claude") or "claude", "-p", text, "--model", a["model"] if str(a.get("model", "")).startswith("claude") else "claude-haiku-5-5",
                                "--dangerously-skip-permissions"], cwd=a.get("workspace") or None, capture_output=True,
                               text=True, encoding="utf-8", timeout=timeout,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            return r.stdout.strip()
        return "".join(_cli.stream(content)).strip()
    r = httpx.post(a["url"].rstrip("/") + "/v1/chat/completions", timeout=timeout, headers=_headers(session),
                   json={"model": a["model"], "messages": _messages(content)})
    r.raise_for_status()
    answer = (r.json()["choices"][0]["message"]["content"] or "").strip()
    _remember(content, answer)
    return answer


def ask_stream(content, timeout: int = 300):
    """Text as your agent writes it (stream=true)."""
    import httpx
    a, parts = _agent(), []
    if a["kind"] == "claude-cli":
        yield from _cli.stream(content)
        return
    with httpx.stream("POST", a["url"].rstrip("/") + "/v1/chat/completions", timeout=timeout, headers=_headers(),
                      json={"model": a["model"], "stream": True, "messages": _messages(content)}) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"].get("content") or ""
            except (ValueError, KeyError, IndexError):
                continue
            if delta:
                parts.append(delta)
                yield delta
    _remember(content, "".join(parts))


def unless_no_reply(chunks, state: dict):
    """The agent's way to stay silent: an answer that starts with NO_REPLY yields nothing (state["quiet"] = True)."""
    buf = ""
    for c in chunks:
        if buf is None:
            yield c
            continue
        buf += c
        s = buf.lstrip()
        if not ("NO_REPLY".startswith(s) or s.startswith("NO_REPLY")):
            yield buf
            buf = None
    if buf is not None and buf.strip().startswith("NO_REPLY"):
        state["quiet"] = True
    elif buf:
        yield buf


def sentences(chunks):
    """Join streamed chunks and hand out whole sentences (plus whatever is left at the end)."""
    buffer, first = "", True
    for chunk in chunks:
        buffer += chunk
        if first and (cut := buffer.find(", ", 15)) != -1 and not _SENTENCE_END.search(buffer[:cut]):
            first = False  # a long first sentence: start speaking at its first comma (~2 s sooner)
            yield buffer[:cut + 1].strip()
            buffer = buffer[cut + 2:]
        parts = _SENTENCE_END.split(buffer)
        for done in parts[:-1]:
            if done.strip():
                first = False
                yield done.strip()
        buffer = parts[-1]
    if buffer.strip():
        yield buffer.strip()


def alive() -> bool:
    if _agent()["kind"] == "claude-cli":
        return True
    import socket
    from urllib.parse import urlparse
    u = urlparse(_agent()["url"])
    try:
        socket.create_connection((u.hostname, u.port or 80), timeout=2).close()
        return True
    except OSError:
        return False


_last_restart = 0.0


def restart() -> bool:
    """Runs your restart_command (if you set one), at most every 5 minutes."""
    global _last_restart
    command = _agent().get("restart_command") if _agent()["kind"] != "claude-cli" else None  # light house: never start OpenClaw
    if not command or time.time() - _last_restart < 300:
        return False
    _last_restart = time.time()
    print(time.strftime("%H:%M:%S"), "agent down: running restart_command")
    subprocess.Popen(command, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return True


WHO = ("[SETUP - reply with ONE line of JSON and nothing else] The voice orb on this PC is about to show your name. "
       'Reply {"name": "<the name you call yourself, as written in your persona, e.g. F.R.I.D.A.Y.>", '
       '"color": "<#rrggbb, ONLY if your persona names a color>"}. No name of your own: reply {}')


def adopt_identity(reply: str) -> dict:
    """The orb takes your agent's own name (Hermes, OpenClaw, any): writes data/identity.json once.
    Written even when the agent has no name ({}), so it isn't asked again; delete the file to ask again."""
    m = re.search(r"\{.*?\}", reply or "", re.S)
    try:
        got = json.loads(m.group(0)) if m else {}
    except ValueError:
        got = {}
    ident = {}
    name = str(got.get("name") or "").strip()
    if 0 < len(name) <= 24 and re.search(r"[A-Za-z0-9]", name):
        ident = {"name": name, "letter": re.sub(r"[^A-Za-z0-9]", "", name)[0].upper()}
        if re.fullmatch(r"#[0-9a-fA-F]{6}", str(got.get("color") or "")):
            ident["color"] = got["color"]
    settings.IDENTITY.write_text(json.dumps(ident, ensure_ascii=False), encoding="utf-8")
    return ident


class Brain:
    def __init__(self) -> None:
        import threading
        threading.Thread(target=self._watch, daemon=True).start()
        threading.Thread(target=self._warm_up, daemon=True).start()

    def _warm_up(self) -> None:
        """Right after Windows starts, the agent's first answer is slow (it's still loading). Wake it up now, in a
        side session, so your first question doesn't pay for it. One tiny message."""
        if _agent()["kind"] == "claude-cli":
            _warm_cli()
            return
        for _ in range(60):  # up to 10 minutes for the agent to come up
            if alive():
                try:
                    first = not settings.IDENTITY.exists()  # first start: the same message asks who the agent is
                    reply = ask(WHO if first else "[WARMUP - reply only: OK]", timeout=240,
                                session="agent:main:warmup" if _agent()["kind"] == "openclaw" else "for-real-jarvis-warmup")
                    if first:
                        print(time.strftime("%H:%M:%S"), "identity from your agent:", adopt_identity(reply))
                    print(time.strftime("%H:%M:%S"), "agent warmed up")
                except Exception as e:  # noqa: BLE001
                    print("warm-up failed:", type(e).__name__)
                return
            time.sleep(10)

    def _watch(self) -> None:
        while True:
            if not alive():
                restart()
            time.sleep(60)

    def _down(self) -> str:
        restart()
        return DOWN.get(settings.load()["language"], DOWN["en"])

    def answer(self, text: str, voice: bool = False) -> str:
        from .voice import voice_tag
        if alive():
            try:
                reply = ask(with_screen(_with_notes((voice_tag() if voice else CHAT_TAG) + text)))
                if reply:
                    return reply
            except Exception as e:  # noqa: BLE001
                print("agent didn't answer:", type(e).__name__, str(e)[:200])
                if getattr(getattr(e, "response", None), "status_code", 0) == 401:
                    return _line(LOGIN)  # it's up, it just isn't logged in: restarting it wouldn't help
        return self._down()

    def answer_by_sentence(self, text: str, voice: bool = False, open_mic: str = ""):
        """Like answer(), but sentence by sentence so the voice starts with the first one.
        open_mic: the note for something overheard without his name (addressed.py): no answer and no error is said then."""
        from .voice import voice_tag
        if not alive():
            if not open_mic:
                yield self._down()
            return
        STOPPED.clear()
        content, any_ = with_screen(_with_notes(open_mic + (voice_tag() if voice else CHAT_TAG) + text)), False
        state: dict = {}
        try:
            for sentence in sentences(unless_no_reply(ask_stream(content), state)):
                if STOPPED.is_set():
                    return
                any_ = True
                yield sentence
        except Exception as e:  # noqa: BLE001
            print("streaming failed:", type(e).__name__, str(e)[:200])
        if not any_ and not STOPPED.is_set() and not state.get("quiet") and not open_mic:
            yield self.answer(text, voice=voice)


if __name__ == "__main__":
    assert with_screen("what time is it?") == "what time is it?"
    assert list(sentences(["Hello, s", "ir. It is", " 8. All good"])) == ["Hello, sir.", "It is 8.", "All good"]
    assert list(sentences(["The Toyota Corolla, sir", ", with 50 million sold. Yes"])) == ["The Toyota Corolla,", "sir, with 50 million sold.", "Yes"]
    assert _WANTS_SCREEN.search("look at my screen") and _WANTS_SCREEN.search("mirá mi pantalla")
    print("brain ok; agent alive:", alive())
