"""Ears and voice.

Ears: RealtimeSTT (Silero VAD + faster-whisper). "Jarvis" is found in what was transcribed.
Voice: Kokoro (local) or ElevenLabs (cloud, data/elevenlabs.key). Everything that plays goes through one lock.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Callable

import numpy as np
import sounddevice as sd

from . import settings

# Orb menu voices. "a:0.6+b:0.4" mixes two Kokoro voices.
VOICES = {
    "Lewis (British)": "bm_lewis",
    "George (British)": "bm_george",
    "Daniel (British)": "bm_daniel",
    "Onyx (deep)": "am_onyx",
    "Alex (Spanish)": "em_alex",
    "Santa (Spanish, deep)": "em_santa",
    "Dora (Spanish, female)": "ef_dora",
    "George + Lewis": "bm_george:0.5+bm_lewis:0.5",
    "Daniel (ElevenLabs)": "elevenlabs:Daniel",   # cloud; needs data/elevenlabs.key
}
SAMPLE = {"en": "Good afternoon, sir. All systems are online.", "es": "Buenas tardes, señor. Todos los sistemas en línea."}
SPEED = 1.1
FOLLOW_UP_SEC = 8   # after "Jarvis" alone or after an answer, keep listening without the name

# Per language: what Whisper hears, how you call him, and the short phrases that cut him off.
# Stop phrases must be the WHOLE utterance, so "stop the music" is still a normal request.
WORDS = {
    "en": {"wake": r"(?:hey|ok|okay|yo)", "stop": r"(?:stop|enough|quiet|shut up|silence|that'?s enough)",
           "filler": r"(?:jarvis|please|now|stop)", "junk": r"^(thanks? for watching.*|subtitles.*|\W*|m+|uh+|um+)\.?$"},
    "es": {"wake": r"(?:oye|oie|hey|ey|ei|hola|che)", "stop": r"(?:par[aá]|basta|silencio|c[aá]llate|ya est[aá]|suficiente|detente)",
           "filler": r"(?:par[aá]|basta|jarvis|ya|por favor)", "junk": r"^(gracias( por ver( el video)?)?|subt[ií]tulos.*|\W*|m+|eh+|ah+)\.?$"},
}
_NAME = r"(?:jarvis|yarvis|jarbis|harvis|jarviz|yarbis|charvis|arvis)"  # how Whisper mishears "Jarvis"


def _lang() -> str:
    lang = settings.load()["language"]
    return lang if lang in WORDS else "en"


def _wake_re(lang: str):
    # "Jarvis" always works; your agent's name too (data/identity.json: "Hey Friday")
    names = "|".join([_NAME[3:-1]] + [re.escape(w) for w in settings.identity()["wake"] if w != "jarvis"])
    return re.compile(rf"^\W*(?:{WORDS[lang]['wake']}\W+)?(?:{names})\b[\s,.!:;-]*(.*)$", re.I | re.S)


def _stop_re(lang: str):
    w = WORDS[lang]
    return re.compile(rf"^\W*{w['stop']}(?:\W+{w['filler']}){{0,2}}\W*$", re.I)


def split_wake(text: str, lang: str | None = None) -> tuple[bool, str]:
    """("Hey Jarvis, what time is it?") -> (True, "what time is it?")."""
    m = _wake_re(lang or _lang()).match(text.strip())
    return (True, m.group(1).strip()) if m else (False, text.strip())


def is_stop(text: str, lang: str | None = None) -> bool:
    return bool(_stop_re(lang or _lang()).match(text))


def is_junk(text: str, lang: str | None = None) -> bool:
    return bool(re.match(WORDS[lang or _lang()]["junk"], text, re.I))


def voice_tag() -> str:
    """Tells your agent the message came from the mic and the answer will be read aloud."""
    s = settings.load()
    return s["voice_tags"]["spoken_english" if s["speak_english"] else "spoken"]


# ---------- orb level (rings follow the volume) ----------
_levels = {"mic": (0.0, 0.0), "voice": (0.0, 0.0)}


def _mark(source: str, samples) -> None:
    if len(samples):
        rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float32))))
        _levels[source] = (min(1.0, rms * float(settings.load()["orb_gain"])), time.time())


def level(source: str) -> float:
    """Last volume of `source` ("mic" or "voice"), fading to 0 in 0.3 s without new audio."""
    value, when = _levels[source]
    return value * max(0.0, 1 - (time.time() - when) / 0.3)


# ---------- speaking ----------
_cut = threading.Event()
_tts = None
_tts_lock = threading.Lock()
# Everything that plays goes through here one at a time: two sd.play() at once crashed the process.
_audio_lock = threading.Lock()


def cut() -> None:
    """Silences JARVIS right now (Kokoro and ElevenLabs)."""
    _cut.set()
    sd.stop()


def clean(text: str) -> str:
    text = re.sub(r"```.*?```", " (I left the code in the chat) ", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#`>|~]", "", text)
    text = re.sub(r"[\U0001F000-\U0001FFFF☀-➿️]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _device_name(d: dict) -> str:
    for cp in ("cp1252", "latin-1"):  # MME hands back UTF-8 read as cp1252
        try:
            return d["name"].encode(cp).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return d["name"]


def _find_output(name: str) -> int | None:
    mme = next(i for i, h in enumerate(sd.query_hostapis()) if h["name"] == "MME")
    return next((i for i, d in enumerate(sd.query_devices())
                 if d["hostapi"] == mme and d["max_output_channels"] > 0 and name in d["name"].lower()), None)


def output() -> int | None:
    """Chosen output device (even if Windows has another default). Call with _audio_lock held."""
    name = settings.load()["output"].lower()
    if not name:
        return None
    index = _find_output(name)
    if index is None:  # something was (un)plugged: re-list (safe, nothing is playing)
        sd._terminate()
        sd._initialize()
        index = _find_output(name)
    return index


def _play(audio, sr: int) -> None:
    with _audio_lock:
        sd.play(audio, sr, device=output())
        t0, window = time.time(), sr // 20
        while sd.get_stream().active:  # instead of sd.wait(): feed the orb while it plays
            i = int((time.time() - t0) * sr)
            _mark("voice", audio[i:i + window])
            time.sleep(0.04)


def _style(voice: str):
    """"bm_lewis" or a mix "bm_george:0.5+bm_lewis:0.5" (averaged style vector)."""
    if "+" not in voice and ":" not in voice:
        return voice
    return sum(_tts.get_voice_style(n) * float(w) for n, w in (p.split(":") for p in voice.split("+")))


ELEVENLABS_KEY = settings.DATA / "elevenlabs.key"   # paste your key there; never committed
_voice_id: dict[str, str] = {}


def _elevenlabs_headers(name: str) -> dict | None:
    try:
        key = ELEVENLABS_KEY.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not key:
        return None
    headers = {"xi-api-key": key}
    if name not in _voice_id:  # find the voice by name in your account
        import httpx
        voices = httpx.get("https://api.elevenlabs.io/v2/voices", params={"search": name},
                           headers=headers, timeout=15).raise_for_status().json()["voices"]
        _voice_id[name] = next(v["voice_id"] for v in voices if v["name"].split(" ")[0] == name)
    return headers


def set_elevenlabs_key(key: str, voice_name: str = "Daniel") -> str | None:
    """Checks the key against ElevenLabs, saves it in data/elevenlabs.key (git-ignored) and switches the voice.
    Returns None if it worked, or what went wrong. The key is never printed or logged."""
    import httpx
    key = key.strip()
    if len(key) < 20:
        return "That doesn't look like an ElevenLabs key."
    try:
        r = httpx.get("https://api.elevenlabs.io/v2/voices", params={"search": voice_name},
                      headers={"xi-api-key": key}, timeout=15)
    except httpx.HTTPError:
        return "Couldn't reach ElevenLabs. Check your internet connection."
    if r.status_code in (401, 403):
        return "ElevenLabs rejected that key (or it lacks the 'Voices' read permission)."
    if r.status_code != 200:
        return f"ElevenLabs answered {r.status_code}. Try again in a minute."
    settings.DATA.mkdir(exist_ok=True)
    ELEVENLABS_KEY.write_text(key, encoding="utf-8")
    _voice_id.clear()
    settings.save("voice", f"elevenlabs:{voice_name}")
    return None


def _speak_elevenlabs(text: str, name: str) -> bool:
    """Streams the voice as it arrives (starts in ~0.5 s). False = couldn't: Kokoro speaks instead."""
    import httpx
    try:
        headers = _elevenlabs_headers(name)
        if headers is None:
            return False
        with httpx.stream("POST", f"https://api.elevenlabs.io/v1/text-to-speech/{_voice_id[name]}/stream",
                          params={"output_format": "pcm_24000"}, headers=headers, timeout=30,
                          json={"text": text, "model_id": "eleven_flash_v2_5"}) as r:
            r.raise_for_status()
            with _audio_lock, sd.RawOutputStream(samplerate=24000, channels=1, dtype="int16", device=output()) as out:
                rest = b""
                for chunk in r.iter_bytes():
                    if _cut.is_set():
                        out.abort()  # drop what was buffered
                        break
                    chunk = rest + chunk
                    even = len(chunk) - len(chunk) % 2  # whole 16-bit samples
                    out.write(chunk[:even])
                    _mark("voice", np.frombuffer(chunk[:even], np.int16) / 32768)
                    rest = chunk[even:]
        return True
    except Exception as e:  # noqa: BLE001 — fall back to the local voice
        print("ElevenLabs unavailable, using Kokoro:", type(e).__name__, str(e)[:200])
        return False


def say(text: str) -> None:
    global _tts
    text = clean(text)
    if not text:
        return
    s = settings.load()
    voice = s["voice"]
    english = s["speak_english"] or s["language"] == "en"
    if voice.startswith("elevenlabs:"):
        if _speak_elevenlabs(text, voice.split(":", 1)[1]):
            return
        voice = "bm_lewis" if english else "em_alex"
    with _tts_lock:
        if _tts is None:
            from kokoro_onnx import Kokoro
            _tts = Kokoro(str(settings.ROOT / "models/kokoro-v1.0.int8.onnx"), str(settings.ROOT / "models/voices-v1.0.bin"))
        audio, sr = _tts.create(text, voice=_style(voice), speed=SPEED, lang="en-gb" if english else "es")
    if not _cut.is_set():
        _play(audio, sr)


def beep(freq: int = 880, sec: float = 0.1) -> None:
    t = np.linspace(0, sec, int(16000 * sec), False)
    _play((0.15 * np.sin(2 * np.pi * freq * t) * np.hanning(t.size)).astype(np.float32), 16000)


# ---------- listening ----------

def microphones() -> list[tuple[int, str]]:
    import pyaudio
    p = pyaudio.PyAudio()
    try:
        mme = next(i for i in range(p.get_host_api_count()) if p.get_host_api_info_by_index(i)["name"] == "MME")
        return [(i, _device_name(d)) for i in range(p.get_device_count())
                if (d := p.get_device_info_by_index(i))["maxInputChannels"] > 0 and d["hostApi"] == mme
                and "Mapper" not in d["name"] and "Asignador" not in d["name"]]
    finally:
        p.terminate()


def mic_index(name: str) -> int | None:
    if not name:
        return None
    return next((i for i, n in microphones() if name.lower() in n.lower()), None)


def pick_microphone(sec: float = 4.0) -> str | None:
    """Records from each microphone while you talk and keeps the one that hears you best."""
    import pyaudio
    p = pyaudio.PyAudio()
    print(f"Talk non-stop for ~{sec:.0f} s on each microphone (count out loud).")
    results = []
    for i, name in microphones():
        input(f"\n[{name}]  Press Enter and talk...")
        try:
            s = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, input_device_index=i,
                       frames_per_buffer=1600)
            x = np.frombuffer(b"".join(s.read(1600, exception_on_overflow=False) for _ in range(int(sec * 10))),
                              np.int16).astype(np.float32)
            s.close()
            loud = float(np.percentile(np.abs(x), 95))
        except OSError as e:
            print("  won't open:", e)
            continue
        print(f"  level {loud:7.0f}  " + "#" * min(60, int(loud / 200)))
        results.append((loud, name))
    p.terminate()
    if not results:
        return None
    best = max(results)[1]
    settings.save("microphone", best)
    print(f"\nPicked: {best}  (saved in {settings.FILE})")
    return best


class Ears:
    """Listens in a thread and calls `on_heard(text)`; `state(name)` tells the orb.
    Watchdog: if the mic stops sending audio (some USB speakers freeze PyAudio), the ears rebuild themselves."""
    NO_AUDIO_SEC = 6

    def __init__(self, on_heard: Callable[[str], None], state: Callable[[str], None]) -> None:
        self.state, self.on_heard = state, on_heard
        self.running, self.mic_on, self.speaking = True, True, False
        self._awake_until = 0.0
        self._last_audio = time.time()
        self.rec = self._create()
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _create(self):
        from RealtimeSTT import AudioToTextRecorder
        s = settings.load()
        index = mic_index(s["microphone"])
        if s["microphone"] and index is None:
            print(f"Warning: microphone '{s['microphone']}' not found, using the Windows default.")
        self._last_audio = time.time()
        return AudioToTextRecorder(
            model=s["whisper_model"], language=_lang(), device="cpu", compute_type="int8", beam_size=1,
            initial_prompt=f"{settings.identity()['short'].title()}, {s['vocabulary']} {', '.join(m.get('title', '') for m in settings.modes())}", input_device_index=index, spinner=False,
            silero_sensitivity=0.4, silero_backend="official_onnx", silero_deactivity_detection=True,
            webrtc_sensitivity=3, post_speech_silence_duration=0.55, min_length_of_recording=0.4,
            on_recording_start=self._starts, on_recording_stop=self._stops, on_recorded_chunk=self._audio,
            no_log_file=True)

    def _audio(self, chunk) -> None:
        self._last_audio = time.time()
        _mark("mic", np.frombuffer(chunk, np.int16) / 32768)

    def _watchdog(self) -> None:
        while self.running:
            time.sleep(2)
            if self.mic_on and time.time() - self._last_audio > self.NO_AUDIO_SEC:
                print(time.strftime("%H:%M:%S"), "the mic stopped sending audio: rebuilding the ears")
                old = self.rec
                try:
                    self.rec = self._create()
                except Exception as e:  # noqa: BLE001 — retries next round
                    print("couldn't rebuild the ears:", e)
                    self._last_audio = time.time()
                    continue
                threading.Thread(target=old.shutdown, daemon=True).start()  # frees the stuck text()

    def awake(self) -> bool:
        return time.time() < self._awake_until

    def _starts(self) -> None:
        self._rec_start = time.time()

    def _stops(self) -> None:
        self._rec_end = time.time()
        if self.awake():
            self.state("thinking")

    def _wake(self) -> None:
        self._awake_until = time.time() + FOLLOW_UP_SEC
        self.state("listening")
        beep()

    def _sleep(self) -> None:
        self._awake_until = 0.0
        self.state("idle")

    def during_his_voice(self) -> bool:
        """Did this recording start while JARVIS was talking? Then it may be his own echo, even if the
        transcription arrives after he stopped: it can only cut him off, never become a new request."""
        if self.speaking:
            return True
        start = getattr(self, "_rec_start", 0.0)
        return getattr(self, "_spoke_from", 1e18) <= start <= getattr(self, "_spoke_until", 0.0) + 0.3

    def by_hotkey(self) -> None:
        """Hotkey = saying "Jarvis": if he's talking he stops, and he listens for your request."""
        if self.speaking:
            cut()
        if self.mic_on:
            self._wake()

    def mute(self, off: bool) -> None:
        self.mic_on = not off
        self._last_audio = time.time()
        self.rec.set_microphone(not off)

    def speak(self, text: str, then=None) -> None:
        """Says `text`; `then` (a function returning the rest of the answer, still arriving) follows it."""
        interruptible = settings.load()["interruptible"]
        self.state("speaking")
        _cut.clear()
        self.speaking, self._spoke_from = True, time.time()
        if not interruptible:
            self.mute(True)  # so he doesn't hear himself through the speakers
        last = text
        try:
            say(text)
            if then:
                rest = then()
                last = rest or text
                if not _cut.is_set():
                    say(rest)
        finally:
            self.speaking, self._spoke_until = False, time.time()
            if not interruptible:
                self.mute(False)
            # he asked something ("¿Sigo?"): answer without the name. Otherwise back to waiting for "Jarvis"
            asked = last.strip().rstrip(" .!").endswith("?") or settings.load().get("follow_up", False)
            self._awake_until = time.time() + FOLLOW_UP_SEC if asked else 0.0
            self.state("listening" if asked else "idle")

    def loop(self) -> None:
        self.state("idle")
        while self.running:
            try:
                text = (self.rec.text() or "").strip()
                self.last_transcription = time.time() - getattr(self, "_rec_end", time.time())
            except Exception:  # noqa: BLE001 — the watchdog closed the old recorder
                continue
            if len(text) < 2 or is_junk(text):
                continue
            called, request = split_wake(text)
            if self.during_his_voice():  # only "Jarvis…" or a stop phrase cut him off; the rest is his echo
                if not (called or is_stop(text)):
                    continue
                print(time.strftime("%H:%M:%S"), "cut off by you:", text)
                cut()
                if not called or len(request) < 2 or is_stop(request):
                    continue  # you only wanted him quiet; he keeps listening 8 s without the name
            elif is_stop(text) and self.awake():
                continue  # "stop" when he's already quiet: nothing to do
            if not (called or self.awake()):
                if self._awake_until:
                    self._sleep()
                continue  # background talk: not for JARVIS
            if called and len(request) < 2:  # just "Jarvis": wait for the request
                self._wake()
                continue
            self._awake_until = time.time() + 60  # stays awake while he thinks and talks
            # in another thread: the ears keep listening while he thinks and talks (so you can cut him off)
            threading.Thread(target=self.on_heard, args=(request,), daemon=True).start()

    def close(self) -> None:
        self.running = False
        self.rec.shutdown()


def hotkey_listener(on_press: Callable[[], None], hotkey: str | None = None) -> None:
    """Global hotkey (Windows RegisterHotKey, no dependencies). Blocks: run it in a thread."""
    import ctypes
    from ctypes import wintypes
    hotkey = (hotkey or settings.load()["hotkey"]).lower()
    *mods, key = hotkey.split("+")
    flags = sum({"alt": 1, "ctrl": 2, "shift": 4, "win": 8}[m] for m in mods) | 0x4000  # MOD_NOREPEAT
    special = {"pause": 0x13, "pausa": 0x13, **{f"f{n}": 0x6F + n for n in range(1, 13)}}
    vk = special.get(key) or ord(key.upper())
    u = ctypes.windll.user32
    if not u.RegisterHotKey(None, 1, flags, vk):
        print(f"Couldn't register the hotkey {hotkey}: another program uses it.")
        return
    msg = wintypes.MSG()
    while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if msg.message == 0x0312:  # WM_HOTKEY
            on_press()


if __name__ == "__main__":  # self-test (no audio needed)
    assert clean("**Done**, sir 🦾") == "Done, sir"
    for lang, ok, no in (("en", ("Stop.", "Enough, Jarvis", "shut up", "stop stop"), ("stop the music", "I'll stop the music, sir.", "Stopwatch")),
                         ("es", ("Pará.", "Basta, Jarvis", "callate", "Ya está"), ("para mañana", "Pará la música", "Paramount"))):
        for p in ok:
            assert is_stop(p, lang), (lang, p)
        for p in no:
            assert not is_stop(p, lang), (lang, p)
    assert split_wake("Hey Jarvis, what time is it?", "en") == (True, "what time is it?")
    assert split_wake("Oye Yarvis, pausá la música", "es") == (True, "pausá la música")
    assert split_wake("I talked to Jarvis yesterday", "en")[0] is False
    assert split_wake("Jarvisito", "es")[0] is False
    assert is_junk("Thanks for watching!", "en") and not is_junk("Open Spotify", "en")
    print("voice ok; microphones:", [n for _, n in microphones()])
