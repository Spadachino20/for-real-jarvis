"""For Real J.A.R.V.I.S. — a desktop orb, a voice and a panel for YOUR agent.

  python -m jarvis              orb + voice ("Hey Jarvis") + panel
  python -m jarvis --no-voice   orb + panel only, type to him
  python -m jarvis --text ".."  one question from the console (answer spoken aloud)
  python -m jarvis --mics       pick the microphone that hears you best
  python -m jarvis --selftest   self-tests of every piece
"""
from __future__ import annotations

import subprocess
import sys
import re
import threading

from . import settings

if sys.stdout is None:  # pythonw (no console): everything goes to the log
    settings.DATA.mkdir(exist_ok=True)
    _log = open(settings.DATA / "jarvis.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _log
else:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GREETING = {"en": ('Online, sir. Say "Hey Jarvis" or press {key}.', "Online, sir."),
            "es": ('En línea, señor. Diga "oye Jarvis" o apriete {key}.', "En línea, señor.")}


def quick_reply(text: str, lang: str) -> str | None:
    """Questions JARVIS answers himself, instantly, without asking the agent."""
    import datetime
    t, now, es = text.lower(), datetime.datetime.now(), lang == "es"
    days = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    if re.search(r"\b(qu[eé] hora( es)?|what time( is it)?|the time)\b", t):
        return f"Son las {now:%H:%M}, señor." if es else f"It's {now:%H:%M}, sir."
    if re.search(r"\b(qu[eé] (d[ií]a|fecha) es( hoy)?|what('?s| is) (the date|today)|what day is it)\b", t):
        return (f"Hoy es {days[now.weekday()]} {now.day} de {months[now.month - 1]}, señor." if es
                else f"Today is {now:%A, %B} {now.day}, sir.")
    if re.search(r"c[aá]mara|camera", t) and re.search(
            r"\b(apag|desactiv|quit|cerr|cierr|prend|encend|activ|turn|switch|disable|enable|stop|start)|\b(on|off)\b", t):
        off = re.search(r"\b(apag|desactiv|quit|cerr|cierr|disable|stop)|\boff\b", t)
        from .hands import CAMERA_OFF
        from .brain import note
        note(f"turned the gesture camera {'off' if off else 'on'} (he asked by voice)")
        if off:
            CAMERA_OFF.touch()
            return "Cámara apagada, señor." if es else "Camera off, sir."
        CAMERA_OFF.unlink(missing_ok=True)
        return "Cámara encendida, señor." if es else "Camera on, sir."
    return None


def selftest() -> None:
    for module in ("settings", "brain", "voice", "panel"):
        r = subprocess.run([sys.executable, "-m", f"jarvis.{module}"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        print(f"{module:9}", "OK  " if r.returncode == 0 else "FAIL", (r.stdout or r.stderr).strip().splitlines()[-1:])


def already_running() -> bool:
    """One orb per Windows session: if autostart and a double click collide, the second one leaves."""
    import ctypes
    global _mutex  # held while the process lives
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\ForRealJarvis_orb")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def kill_orphans() -> None:
    """A JARVIS that was killed leaves its Whisper workers behind (~500 MB): close those whose parent is gone."""
    import os
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "$all = (Get-Process).Id; Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                        "? { $_.CommandLine -like '*spawn_main*' -and $all -notcontains $_.ParentProcessId } | % ProcessId"],
                       capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    for pid in r.stdout.split():
        os.kill(int(pid), 9)
        print("closed an orphan worker:", pid)


def app(with_voice: bool) -> None:
    if already_running():
        print("JARVIS is already running.")
        return
    import time
    threading.Thread(target=kill_orphans, daemon=True).start()
    from .brain import Brain
    from .voice import SAMPLE, VOICES, level, say
    from .widget import Orb
    s = settings.load()
    lang = s["language"] if s["language"] in GREETING else "en"
    parts = {"brain": None, "ears": None}
    turn = threading.Lock()  # one answer at a time

    def finished(summary: str, full: str) -> None:
        """A background task is done: say the summary when JARVIS is free; the whole answer goes to the orb's chat."""
        with turn:
            orb.show("JARVIS", full)
            if parts["ears"]:
                parts["ears"].speak(summary)

    def said(text: str) -> None:
        """Speak one line when JARVIS is free (the rest is on screen)."""
        with turn:
            orb.show("JARVIS", text)
            if parts["ears"]:
                parts["ears"].speak(text)

    def think(text: str, voice: bool) -> None:
        with turn:
            orb.set_state("thinking")
            while parts["brain"] is None:
                time.sleep(0.3)
            t0 = time.time()
            from .panel import show_reply, background_reply, message_reply, metrics_reply, mode_reply, remember, where_reply
            spoken = "en" if voice and settings.load()["speak_english"] else lang  # local replies in the language he speaks
            if not (reply := where_reply(text, spoken)):
                remember(text)
            if reply or (reply := quick_reply(text, spoken) or mode_reply(text, spoken) or metrics_reply(text, spoken) or message_reply(text, spoken) or show_reply(text, spoken, said) or background_reply(text, spoken, finished)):  # modes run here, not through the agent: instant and reliable
                orb.show("JARVIS", reply)
                if voice and parts["ears"]:
                    parts["ears"].speak(reply)
                else:
                    orb.set_state("idle")
                return
            if voice and parts["ears"]:
                # the voice starts with the first sentence; the rest keeps arriving in parallel
                pieces = parts["brain"].answer_by_sentence(text, voice=True)
                got_first = threading.Event()

                def maybe_filler() -> None:  # only if the agent is slow: a quick answer needs no "one moment"
                    if not got_first.wait(0.6):
                        parts["ears"].filler()
                    if not got_first.wait(7):  # using tools: say so instead of 30 s of silence; the answer still comes spoken
                        parts["ears"].filler("En eso estoy, señor. Le aviso cuando termine." if spoken == "es"
                                             else "Working on it, sir. I'll let you know when it's done.")
                        orb.set_state("thinking")
                threading.Thread(target=maybe_filler, daemon=True).start()
                first = next(pieces, "")
                got_first.set()
                t1, rest = time.time(), []

                def the_rest():  # each sentence is spoken as soon as it arrives
                    for sentence in pieces:
                        rest.append(sentence)
                        yield sentence

                parts["ears"].speak(first, then=the_rest())
                orb.show("JARVIS", " ".join([first, *rest]).strip())
            else:
                reply = parts["brain"].answer(text, voice=voice)
                t1 = time.time()
                orb.show("JARVIS", reply)
                if voice and parts["ears"]:
                    parts["ears"].speak(reply)
                else:
                    orb.set_state("idle")
            heard = getattr(parts["ears"], "last_transcription", 0.0) if voice else 0.0
            print(time.strftime("%H:%M:%S"), f"timings {'voice' if voice else 'chat'}: "
                  f"understand {heard:.1f}s | agent {t1 - t0:.1f}s | speak {time.time() - t1:.1f}s")

    def clapped() -> None:
        """Clap-clap (or snap-snap): straight into work mode, no agent in between."""
        want = settings.load().get("clap_mode", "auto")
        modes = settings.modes()
        if want == "auto":
            mode = next((m for m in modes if re.search(r"work|trabaj", f"{m.get('id', '')} {m.get('title', '')}", re.I)), None)
        else:
            mode = next((m for m in modes if m.get("id") == want), None)
        es = lang == "es" and not settings.load()["speak_english"]  # same language as his voice
        if not turn.acquire(blocking=False):  # busy answering: ignore the claps
            return
        try:
            print(time.strftime("%H:%M:%S"), "clap-clap:", mode and mode.get("id"))
            if mode is None:
                reply = ("No tengo un modo trabajo todavía, señor. Pídame que lo creemos." if es
                         else "I don't have a work mode yet, sir. Ask me to set one up.")
            else:
                from .panel import run_mode
                title = mode.get("title") or mode["id"]
                reply = run_mode(mode["id"], by="a double clap") or (f"Modo {title} activado, señor." if es else f"Activating {mode.get('title_en', 'work' if want == 'auto' else title)} mode, sir.")  # claps are deliberate: no "shall I?"
            orb.show("JARVIS", reply)
            parts["ears"].speak(reply)
        finally:
            turn.release()

    def stop_all() -> None:
        """Fist: silence now, stop the agent's run (thinking, tools, writing), and leave it a note with what you heard."""
        from .voice import cut
        from . import brain
        cut()
        if not turn.locked():
            return
        brain.STOPPED.set()
        orb.set_state("idle")
        said = " ".join(getattr(parts["ears"], "said", []) if parts["ears"] and parts["ears"].speaking else [])
        if settings.load()["agent"]["kind"] == "claude-cli":
            brain._cli.stop()  # kills its thinking and tools; the next question opens a fresh one
            print(time.strftime("%H:%M:%S"), "stopped by fist (claude-cli)")
            return
        if settings.load()["agent"]["kind"] != "openclaw":
            return
        from .panel import gateway
        key = settings.load()["agent"]["session"]
        try:
            gateway().call("chat.abort", {"sessionKey": key})
            gateway().call("chat.inject", {"sessionKey": key, "label": "cut off", "message":
                "[He cut me off with a gesture. He only heard: «" + (said[-600:] or "nothing") +
                "». Anything after that he did NOT hear and was NOT done; don't assume it.]"})
            print(time.strftime("%H:%M:%S"), "stopped by fist after:", len(said.split()), "words")
        except Exception as e:  # noqa: BLE001
            print("couldn't stop the agent:", e)

    def gesture(name: str) -> None:
        import ctypes
        if name == "puño":  # busy: stop him; idle: minimize the window in front
            if turn.locked() or (parts["ears"] and parts["ears"].speaking):
                stop_all()
            else:
                ctypes.windll.user32.ShowWindow(ctypes.windll.user32.GetForegroundWindow(), 6)  # SW_MINIMIZE
        elif name == "palma":  # music play/pause (any player)
            ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0xB3, 0, 2, 0)
        elif name.startswith("barrer"):  # next / previous song
            key = 0xB0 if name == "barrer derecha" else 0xB1
            ctypes.windll.user32.keybd_event(key, 0, 0, 0)
            ctypes.windll.user32.keybd_event(key, 0, 2, 0)
        elif name == "cuernos":  # settings "horns_mode" (default: juego)
            from .panel import run_mode
            if mode := next((m for m in settings.modes() if m.get("id") == settings.load().get("horns_mode", "juego")), None):
                said(run_mode(mode["id"], by="the horns gesture") or f"Activating {mode.get('title_en', mode.get('title') or mode['id'])} mode, sir.")
        elif name == "pulgar arriba":  # "yes" to his question
            from .panel import _pending
            if _pending:
                threading.Thread(target=think, args=("sí", True), daemon=True).start()

    def heard(text: str) -> None:
        orb.show(you, text)
        think(text, voice=True)

    def typed(text: str) -> None:
        orb.show(you, text)
        threading.Thread(target=think, args=(text, False), daemon=True).start()

    def mute(off: bool) -> None:
        if parts["ears"]:
            parts["ears"].mute(off)

    def quit_() -> None:
        if parts["ears"]:
            parts["ears"].close()
        orb.close()

    def pick_voice(code: str) -> None:
        settings.save("voice", code)
        from .voice import warm_fillers
        threading.Thread(target=warm_fillers, daemon=True).start()
        english = settings.load()["speak_english"] or lang == "en"
        threading.Thread(target=say, args=(SAMPLE["en" if english else lang],), daemon=True).start()

    def pick_english(on: bool) -> None:
        settings.save("speak_english", on)
        from .voice import warm_fillers
        threading.Thread(target=warm_fillers, daemon=True).start()
        threading.Thread(target=say, args=(SAMPLE["en" if on else lang],), daemon=True).start()

    you = "You" if lang == "en" else "Vos"
    orb = Orb(typed, mute, quit_, VOICES, s["voice"], pick_voice, s["speak_english"], pick_english, level, lang)

    def orb_info() -> dict:
        """What the panel shows about the orb (read from the panel's thread)."""
        now = settings.load()
        return {"state": orb.state, "mic": not orb.muted, "voice": now["voice"].replace("elevenlabs:", ""),
                "speaks": "English" if now["speak_english"] else now["language"],
                "hotkey": now["hotkey"].title() if with_voice else "—", "language": now["language"]}

    from .panel import start as start_panel
    orb.panel_url = start_panel(orb_info)

    def boot() -> None:
        parts["brain"] = Brain()
        if with_voice:
            from .voice import Ears, hotkey_listener
            parts["ears"] = Ears(heard, orb.set_state)
            threading.Thread(target=hotkey_listener, args=(parts["ears"].by_hotkey,), daemon=True).start()
            from .voice import ClapDetector
            parts["ears"].claps = ClapDetector(clapped)
            text, spoken = GREETING[lang]
            orb.show("JARVIS", text.format(key=s["hotkey"].title()))
            say(spoken if not s["speak_english"] else GREETING["en"][1])
            from .voice import warm_fillers
            threading.Thread(target=warm_fillers, daemon=True).start()  # "Right away, sir" ready in memory

            def speak_first(text: str) -> None:  # JARVIS talks without being asked: only when he's free
                if not turn.acquire(timeout=20):  # busy answering: wait a bit, then drop it
                    print(time.strftime("%H:%M:%S"), "proactive: skipped (busy):", text[:60])
                else:
                    try:
                        orb.show("JARVIS", text)
                        parts["ears"].speak(text)
                    finally:
                        turn.release()
            if settings.load().get("gestures"):  # webcam hands: python -m jarvis.hands trains them
                from .hands import watch as watch_hands
                threading.Thread(target=watch_hands, args=(gesture,), daemon=True).start()
            from .proactive import watch
            threading.Thread(target=watch, args=(speak_first,), daemon=True).start()
            parts["ears"].loop()
        else:
            orb.set_state("idle")
            orb.show("JARVIS", GREETING[lang][1])

    threading.Thread(target=boot, daemon=True).start()
    orb.run()


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["--selftest"]:
        selftest()
    elif args[:1] == ["--mics"]:
        from .voice import pick_microphone
        pick_microphone()
    elif args[:1] == ["--text"]:
        from .brain import Brain
        from .voice import say
        reply = Brain().answer(" ".join(args[1:]), voice=True)
        print("JARVIS:", reply)
        say(reply)
    else:
        app(with_voice="--no-voice" not in args)


if __name__ == "__main__":
    main()
