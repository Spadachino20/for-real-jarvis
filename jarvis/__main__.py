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


def app(with_voice: bool) -> None:
    if already_running():
        print("JARVIS is already running.")
        return
    import time
    from .brain import Brain
    from .voice import SAMPLE, VOICES, level, say
    from .widget import Orb
    s = settings.load()
    lang = s["language"] if s["language"] in GREETING else "en"
    parts = {"brain": None, "ears": None}
    turn = threading.Lock()  # one answer at a time

    def think(text: str, voice: bool) -> None:
        with turn:
            orb.set_state("thinking")
            while parts["brain"] is None:
                time.sleep(0.3)
            t0 = time.time()
            from .panel import mode_for, run_mode
            if mode := mode_for(text):  # modes run here, not through the agent: instant and reliable
                reply = (run_mode(mode["id"]) or ("Modo " if lang == "es" else "") + (mode.get("title") or mode["id"]) + (", señor." if lang == "es" else " mode, sir."))
                orb.show("JARVIS", reply)
                if voice and parts["ears"]:
                    parts["ears"].speak(reply)
                else:
                    orb.set_state("idle")
                return
            if voice and parts["ears"]:
                # the voice starts with the first sentence; the rest keeps arriving in parallel
                pieces = parts["brain"].answer_by_sentence(text, voice=True)
                first = next(pieces, "")
                t1, rest = time.time(), []
                worker = threading.Thread(target=lambda: rest.extend(pieces), daemon=True)
                worker.start()

                def the_rest() -> str:
                    worker.join()
                    return " ".join(rest)

                parts["ears"].speak(first, then=the_rest)
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
        english = settings.load()["speak_english"] or lang == "en"
        threading.Thread(target=say, args=(SAMPLE["en" if english else lang],), daemon=True).start()

    def pick_english(on: bool) -> None:
        settings.save("speak_english", on)
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
            text, spoken = GREETING[lang]
            orb.show("JARVIS", text.format(key=s["hotkey"].title()))
            say(spoken if not s["speak_english"] else GREETING["en"][1])
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
