"""The brain is YOUR agent (OpenClaw or Hermes). The orb is only a door: there is no second brain here.

Both speak the OpenAI chat-completions API on localhost. OpenClaw keeps the conversation in one session
(the same one its Control UI shows); for other agents the orb sends the last few turns itself.
"""
from __future__ import annotations

import json
import re
import subprocess
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


def _headers() -> dict:
    a, h = _agent(), {}
    if t := token():
        h["Authorization"] = f"Bearer {t}"
    if a["kind"] == "openclaw":
        h["x-openclaw-session-key"] = a["session"]
    return h


_history: list[dict] = []  # only for agents without server-side sessions


def _messages(content) -> list[dict]:
    if _agent()["kind"] == "openclaw":
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


def ask(content, timeout: int = 300) -> str:
    import httpx
    a = _agent()
    r = httpx.post(a["url"].rstrip("/") + "/v1/chat/completions", timeout=timeout, headers=_headers(),
                   json={"model": a["model"], "messages": _messages(content)})
    r.raise_for_status()
    answer = (r.json()["choices"][0]["message"]["content"] or "").strip()
    _remember(content, answer)
    return answer


def ask_stream(content, timeout: int = 300):
    """Text as your agent writes it (stream=true)."""
    import httpx
    a, parts = _agent(), []
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


def sentences(chunks):
    """Join streamed chunks and hand out whole sentences (plus whatever is left at the end)."""
    buffer = ""
    for chunk in chunks:
        buffer += chunk
        parts = _SENTENCE_END.split(buffer)
        for done in parts[:-1]:
            if done.strip():
                yield done.strip()
        buffer = parts[-1]
    if buffer.strip():
        yield buffer.strip()


def alive() -> bool:
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
    command = _agent().get("restart_command")
    if not command or time.time() - _last_restart < 300:
        return False
    _last_restart = time.time()
    print(time.strftime("%H:%M:%S"), "agent down: running restart_command")
    subprocess.Popen(command, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return True


class Brain:
    def __init__(self) -> None:
        import threading
        threading.Thread(target=self._watch, daemon=True).start()

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
                reply = ask(with_screen((voice_tag() if voice else "") + text))
                if reply:
                    return reply
            except Exception as e:  # noqa: BLE001
                print("agent didn't answer:", type(e).__name__, str(e)[:200])
        return self._down()

    def answer_by_sentence(self, text: str, voice: bool = False):
        """Like answer(), but sentence by sentence so the voice starts with the first one."""
        from .voice import voice_tag
        if not alive():
            yield self._down()
            return
        content, any_ = with_screen((voice_tag() if voice else "") + text), False
        try:
            for sentence in sentences(ask_stream(content)):
                any_ = True
                yield sentence
        except Exception as e:  # noqa: BLE001
            print("streaming failed:", type(e).__name__, str(e)[:200])
        if not any_:
            yield self.answer(text, voice=voice)


if __name__ == "__main__":
    assert with_screen("what time is it?") == "what time is it?"
    assert list(sentences(["Hello, s", "ir. It is", " 8. All good"])) == ["Hello, sir.", "It is 8.", "All good"]
    assert _WANTS_SCREEN.search("look at my screen") and _WANTS_SCREEN.search("mirá mi pantalla")
    print("brain ok; agent alive:", alive())
