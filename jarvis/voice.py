"""Ears and voice.

Ears: RealtimeSTT (Silero VAD + faster-whisper). "Jarvis" is found in what was transcribed.
Voice: Kokoro (local) or ElevenLabs (cloud, data/elevenlabs.key). Everything that plays goes through one lock.
"""
from __future__ import annotations

import collections
import re
import sys
import threading
import time
from typing import Callable

import numpy as np
import sounddevice as sd

from . import addressed, settings

# Orb menu voices. "a:0.6+b:0.4" mixes two Kokoro voices.
VOICES = {
    "Lewis (British)": "bm_lewis",
    "George (British)": "bm_george",
    "Daniel (British)": "bm_daniel",
    "Onyx (deep)": "am_onyx",
    "Emma (British, female)": "bf_emma",
    "Heart (American, female)": "af_heart",
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


def _words(text: str) -> list[str]:
    import unicodedata
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9']+", plain)


def echo_of(heard: str, said: list[str]) -> bool:
    """Is what the mic heard just his own voice coming back (headset leaking, speakers)? Most of its words are in
    what he said these last seconds. Your "para, Jarvis" or "abrí Chrome" over him has words he didn't say."""
    words = [w for w in _words(heard) if w not in ("jarvis", "sir", "senor")]
    if not words:
        return bool(_words(heard))  # only "sir" / "señor": his
    his = set(_words(" ".join(said)))
    return sum(w in his for w in words) >= max(1, round(0.6 * len(words)))


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
        sd.play(audio, sr, device=output(), latency="low" if len(audio) < sr // 4 else None)  # a beep: ~0.1 s sooner
        t0, window = time.time(), sr // 20
        while sd.get_stream().active:  # instead of sd.wait(): feed the orb while it plays
            i = int((time.time() - t0) * sr)
            _mark("voice", audio[i:i + window])
            time.sleep(0.04)


class ClapDetector:
    """Two claps (or finger snaps) in a row -> on_double(). Fed with the mic chunks the ears already read.
    A clap is a short, loud peak far above the room's background noise; voice and music are steadier and fail that."""

    def __init__(self, on_double: Callable[[], None]) -> None:
        self.on_double = on_double
        self.background = 0.01        # slow average of the room's loudness (RMS)
        self.last_clap = 0.0          # when the previous clap was
        self.blocked_until = 0.0      # quiet time after a double clap (or a clap that was too loud for too long)

    def feed(self, audio: np.ndarray, now: float | None = None) -> bool:
        s = settings.load()
        if not s.get("clap_mode", "auto"):
            return False
        now = time.time() if now is None else now
        peak = float(np.abs(audio).max()) if audio.size else 0.0
        rms = float(np.sqrt(np.mean(audio ** 2))) if audio.size else 0.0
        loud = peak > s.get("clap_threshold", 0.35) and peak > 8 * self.background and rms < 0.6 * peak
        self.background = 0.97 * self.background + 0.03 * min(rms, 0.2)  # slow: one clap barely moves it
        if not loud or now < self.blocked_until:
            return False
        gap = now - self.last_clap
        if gap < 0.12:                 # the same clap still ringing
            return False
        self.last_clap = now
        if 0.15 <= gap <= 0.8:         # second clap: clap-clap
            self.last_clap, self.blocked_until = 0.0, now + 3
            threading.Thread(target=self.on_double, daemon=True).start()
            return True
        return False


def _paused(audio: np.ndarray, sec: float = 0.16) -> bool:
    """You said something and went quiet just now (the last 0.16 s far below the loudest 0.1 s)."""
    h = 1600
    if audio.size < 3 * h:
        return False
    loud = max(float(np.sqrt(np.mean(audio[i:i + h] ** 2))) for i in range(0, audio.size - h + 1, h))
    return loud > 0.006 and float(np.sqrt(np.mean(audio[-int(16000 * sec):] ** 2))) < 0.15 * loud


def _device() -> str:
    """"cuda" with an NVIDIA card (e.g. RTX 5060) and CUDA installed, else "cpu". settings "stt_device" forces it."""
    want = settings.load().get("stt_device", "auto")
    if want != "auto":
        return want
    try:
        import ctranslate2
        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:  # noqa: BLE001
        return "cpu"


def _style(voice: str):
    """"bm_lewis" or a mix "bm_george:0.5+bm_lewis:0.5" (averaged style vector)."""
    if "+" not in voice and ":" not in voice:
        return voice
    return sum(_tts.get_voice_style(n) * float(w) for n, w in (p.split(":") for p in voice.split("+")))


ELEVENLABS_KEY = settings.DATA / "elevenlabs.key"   # paste your key there; never committed
_voice_id: dict[str, str] = {}
_http = None  # one connection kept open: saves the TLS handshake (~0.1-0.3 s) on every sentence


def _client():
    global _http
    if _http is None:
        import httpx
        _http = httpx.Client(base_url="https://api.elevenlabs.io", timeout=30, http2=False,
                             limits=httpx.Limits(keepalive_expiry=300))
    return _http


def _elevenlabs_headers(name: str) -> dict | None:
    try:
        key = ELEVENLABS_KEY.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not key:
        return None
    headers = {"xi-api-key": key}
    if name not in _voice_id:  # find the voice by name in your account
        voices = _client().get("/v2/voices", params={"search": name},
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
    try:
        headers = _elevenlabs_headers(name)
        if headers is None:
            return False
        with _client().stream("POST", f"/v1/text-to-speech/{_voice_id[name]}/stream",
                              params={"output_format": "pcm_24000", "optimize_streaming_latency": 3},
                              headers=headers, json={"text": text, "model_id": "eleven_flash_v2_5"}) as r:
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


FILLERS = {
    "en": ["Right away, sir.", "One moment, sir.", "On it, sir.", "Certainly, sir.", "Just a second, sir."],
    "es": ["Enseguida, señor.", "Un momento, señor.", "En ello, señor.", "Ahora mismo, señor.", "Déjeme ver, señor."],
}
_filler_audio: dict[tuple[str, str], tuple] = {}  # (voice, text) -> (audio, sample rate), made once


def _synth(text: str, voice: str, english: bool):
    """Audio without playing it (for the cached fillers)."""
    global _tts
    if voice.startswith("elevenlabs:"):
        name = voice.split(":", 1)[1]
        headers = _elevenlabs_headers(name)
        if headers:
            r = _client().post(f"/v1/text-to-speech/{_voice_id[name]}", params={"output_format": "pcm_24000"},
                               headers=headers, json={"text": text, "model_id": "eleven_flash_v2_5"})
            r.raise_for_status()
            return np.frombuffer(r.content[:len(r.content) // 2 * 2], np.int16).astype(np.float32) / 32768, 24000
        voice = "bm_lewis" if english else "em_alex"
    with _tts_lock:
        if _tts is None:
            from kokoro_onnx import Kokoro
            _tts = Kokoro(str(settings.ROOT / "models/kokoro-v1.0.int8.onnx"), str(settings.ROOT / "models/voices-v1.0.bin"))
        return _tts.create(text, voice=_style(voice), speed=SPEED, lang="en-gb" if english else "es")


def _filler_setup():
    s = settings.load()
    english = s["speak_english"] or s["language"] == "en"
    return s["voice"], english, FILLERS["en" if english else "es"]


def warm_fillers() -> None:
    """Prepare the fillers in the background (at start and after changing voice)."""
    if not settings.load().get("fillers", True):
        return
    voice, english, texts = _filler_setup()
    for text in texts:
        if (voice, text) not in _filler_audio:
            try:
                _filler_audio[(voice, text)] = _synth(text, voice, english)
            except Exception as e:  # noqa: BLE001 — no filler is fine
                print("couldn't prepare filler:", type(e).__name__, str(e)[:120])
                return


def filler() -> None:
    """Says a short "Right away, sir" while the agent thinks. Only from the cache: never waits on the network."""
    import random
    if not settings.load().get("fillers", True):
        return
    voice, _, texts = _filler_setup()
    ready = [_filler_audio[(voice, t)] for t in texts if (voice, t) in _filler_audio]
    if ready and not _cut.is_set():
        _play(*random.choice(ready))


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
        self.on_barge = cut  # __main__ swaps it for one that also stops the rest of the answer
        self._awake_until = 0.0
        self._last_audio = time.time()
        self.claps: ClapDetector | None = None   # set by the app: clap-clap -> work mode
        self._load_spotter()
        self._ring: collections.deque = collections.deque(maxlen=110)  # ~3.5 s of mic, for _hear_name
        self._woke_rec = self._ended_rec = -1.0
        self._talk_until, self._asked = 0.0, False  # open mic (addressed.py): he just spoke / he asked something
        self.rec = self._create()
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _load_spotter(self) -> None:
        """Before the mic opens: loading it in the mic callback (cold boot: >6 s) stalled the audio, the watchdog
        rebuilt the ears and the second import met a half-loaded openwakeword."""
        self._oww, self._oww_buf = None, np.zeros(0, np.int16)
        s = settings.load()
        if s.get("stt") == "parakeet":  # loaded now: the first "Jarvis" used to wait ~2 s for Whisper
            from . import stt
            threading.Thread(target=lambda: stt.says_name(np.random.default_rng(0).normal(0, .02, 16000).astype(np.float32)), daemon=True).start()
        if not s.get("fast_wake", True) or s.get("stt") == "parakeet" or s.get("open_mic") == "all":  # _hear_name does it; with the mic open to everything he hears it all anyway: ~120 MB less
            return
        try:
            from openwakeword.model import Model
            self._oww = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        except Exception as e:  # noqa: BLE001 — no model: the transcription still wakes him, just later
            print("fast wake off:", type(e).__name__, str(e)[:120])

    def _create(self):
        from RealtimeSTT import AudioToTextRecorder
        s = settings.load()
        index = mic_index(s["microphone"])
        if s["microphone"] and index is None:
            print(f"Warning: microphone '{s['microphone']}' not found, using the Windows default.")
        self._last_audio = time.time()
        extra = {}
        if s.get("stt") == "parakeet":
            from . import stt
            extra = {"transcription_executor": stt.engine()}  # runs in this process: no Whisper worker at all
        return AudioToTextRecorder(**extra,
            model=s["whisper_model"], language=_lang(), device=_device(), compute_type="float16" if _device() == "cuda" else "int8", beam_size=5,  # 1 garbles short words ("sí" -> "C")
            initial_prompt=("Oye Jarvis, sí, dale, procedé, poné el modo trabajo, por favor. " if _lang() == "es" else "") +  # a Spanish prompt keeps Whisper in Spanish
            f"{settings.identity()['short'].title()}, {s['vocabulary']} {', '.join(m.get('title', '') for m in settings.modes())}", input_device_index=index, spinner=False,
            silero_sensitivity=0.4, silero_backend="raw_onnx" if getattr(sys.modules.get("torch"), "jarvis_stand_in", False) else "official_onnx",  # raw: no torch (jarvis/lean.py) silero_deactivity_detection=True,
            webrtc_sensitivity=3, post_speech_silence_duration=s.get("silence_sec", 0.45), min_length_of_recording=0.4, pre_recording_buffer_duration=0.6,  # 0.2 clipped the first syllable
            on_recording_start=self._starts, on_recording_stop=self._stops, on_recorded_chunk=self._audio,
            no_log_file=True)

    def _audio(self, chunk) -> None:
        self._last_audio = time.time()
        audio = np.frombuffer(chunk, np.int16) / 32768
        _mark("mic", audio)
        self._ring.append((self._last_audio, audio.astype(np.float32)))
        talking = getattr(self, "_rec_start", 0) > getattr(self, "_rec_end", 0) or time.time() - getattr(self, "_rec_end", 0) < 1
        if self.claps and talking:  # "p", "t", "k" in your voice peak like claps: none while you speak
            self.claps.last_clap = 0.0
            if np.abs(audio).max() > 0.35 and time.time() - getattr(self, "_clap_note", 0) > 5:
                self._clap_note = time.time()
                print(time.strftime("%H:%M:%S"), "clap ignored: the mic thinks someone is talking (music? voice?)")
        elif self.claps and not self.speaking and self.mic_on:  # never on his own voice
            self.claps.feed(audio)
        if self.mic_on and not self.speaking and not self.awake():
            self._spot(np.frombuffer(chunk, np.int16))

    def _spot(self, pcm: np.ndarray) -> None:
        """openWakeWord hears "(hey) Jarvis" while you're still talking: beep in ~0.2 s instead of after Whisper."""
        if self._oww is None or not settings.load().get("fast_wake", True):
            return
        self._oww_buf = np.concatenate([self._oww_buf, pcm])
        while self._oww_buf.size >= 1280:  # the model eats 80 ms frames
            frame, self._oww_buf = self._oww_buf[:1280], self._oww_buf[1280:]
            score = max(self._oww.predict(frame).values())
            if score > settings.load().get("wake_threshold", 0.5) and time.time() - getattr(self, "_fast_woke", 0) > 3:
                self._fast_woke, self._woke_rec, self._woke_guess = time.time(), getattr(self, "_rec_start", 0.0), False
                self._oww.reset()
                threading.Thread(target=self._wake, args=(True,), daemon=True).start()

    def _watchdog(self) -> None:
        while self.running:
            time.sleep(2)
            if 0 < self._awake_until < time.time() and not self.speaking:
                self._sleep()  # you said nothing more: back to rest (the orb used to stay lit)
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
        if self.speaking and settings.load().get("barge_in"):
            threading.Thread(target=self._barge, args=(self._rec_start,), daemon=True).start()
        if (self.mic_on and not self.speaking and not self.awake() and settings.load().get("fast_wake", True)
                and settings.load().get("stt") == "parakeet"):
            threading.Thread(target=self._hear_name, args=(self._rec_start,), daemon=True).start()

    def _barge(self, start: float) -> None:
        """barge_in (headphones: he can't hear himself): you start talking over him and he goes quiet at once,
        then takes what you said as a new request. 0.6 s of voice first, so a cough doesn't cut him."""
        time.sleep(0.6)
        if not (self.speaking and self._rec_start == start and getattr(self, "_rec_end", 0) < start):
            return
        if settings.load().get("stt") != "parakeet":
            return  # no fast reader to tell you from his echo: the finished phrase decides (echo_of)
        from . import stt
        heard = [a for at, a in list(self._ring) if at > start - 0.3]
        text = stt.engine().transcribe(np.concatenate(heard), retry=False).text if heard else ""
        if not text.strip() or echo_of(text, [s for _, s in getattr(self, "recent", [])]):
            return  # his own voice leaking into the mic: he keeps talking
        print(time.strftime("%H:%M:%S"), "cut off by your voice:", text[:60])
        self.on_barge()

    def _hear_name(self, start: float) -> None:
        """"Jarvis" on its own (openWakeWord only knows "hey Jarvis"): Parakeet reads along while you're still talking
        (~0.13 s a look, first 1.8 s of each phrase, only asleep) and he beeps the moment the name is in it.
        A short phrase it can't make out gets the hinted Whisper (stt.says_name) at the first pause, once."""
        from . import stt
        checked = False
        while time.time() < start + 1.8 and self._rec_start == start and getattr(self, "_rec_end", 0) < start:
            if self.awake() or self.speaking:
                return
            heard = [a for at, a in list(self._ring) if at > start - 0.5]  # the VAD opens a bit after you start
            if heard and sum(map(len, heard)) > 6400:
                audio = np.concatenate(heard)
                text = stt.engine().transcribe(np.concatenate([audio, np.zeros(3200, np.float32)]), retry=False).text
                found = split_wake(text)[0]
                guess = False
                if not found and not checked and len(text.split()) <= 2 and _paused(audio):
                    checked = True
                    found = guess = stt.says_name(audio)
                if found and not self.awake() and not self.speaking:
                    self._fast_woke, self._woke_rec, self._woke_guess = time.time(), start, guess
                    print(time.strftime("%H:%M:%S"), f"name heard {time.time() - start:.2f}s into your phrase")
                    self._wake(True)
                    return
            time.sleep(0.04)

    def _stops(self) -> None:
        self._rec_end, self._ended_rec = time.time(), getattr(self, "_rec_start", 0.0)
        if self.awake():
            self.state("thinking")

    def _wake(self, fast: bool = False) -> None:
        self._awake_until, self._asked = time.time() + FOLLOW_UP_SEC, False
        self.state("listening")
        if fast or time.time() - getattr(self, "_fast_woke", 0) > 4:  # the fast spotter already beeped
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
        """Says `text`; `then` (the rest of the answer: sentences still arriving, or a function returning it) follows it."""
        interruptible = settings.load()["interruptible"]
        self.state("speaking")
        _cut.clear()
        self.speaking, self._spoke_from = True, time.time()
        if not interruptible:
            self.mute(True)  # so he doesn't hear himself through the speakers
        last, self.said = text, [text]  # what he actually got to say (the fist cuts here)
        self.recent = [(at, s) for at, s in getattr(self, "recent", []) if time.time() - at < 20] + [(time.time(), text)]  # echo check
        try:
            say(text)
            if callable(then):
                then = [then()]
            for more in then or []:  # sentence by sentence, as the agent writes them
                if _cut.is_set():
                    break
                if more:
                    self.said.append(more)
                    self.recent.append((time.time(), more))
                    last = more  # the last thing said decides if he waits for an answer ("¿Sigo?")
                say(more)
        finally:
            self.speaking, self._spoke_until = False, time.time()
            if not interruptible:
                self.mute(False)
            # he asked something ("¿Sigo?"): answer without the name. Otherwise back to waiting for "Jarvis"
            asked = last.strip().rstrip(" .!").endswith("?") or settings.load().get("follow_up", False)
            self._awake_until, self._asked = time.time() + FOLLOW_UP_SEC if asked else 0.0, asked
            self._talk_until = time.time() + addressed.TALK_SEC
            self.state("listening" if asked else "idle")

    def filler(self, text: str | None = None) -> None:
        """Short "Right away, sir" while the agent thinks (or the line given), without hearing himself."""
        interruptible = settings.load()["interruptible"]
        _cut.clear()
        self.speaking, self._spoke_from, self.said = True, time.time(), []  # a filler isn't part of the answer
        if not interruptible:
            self.mute(True)
        try:
            say(text) if text else filler()
        finally:
            self.speaking, self._spoke_until = False, time.time()
            if not interruptible:
                self.mute(False)

    def loop(self) -> None:
        self.state("idle")
        while self.running:
            try:
                text = (self.rec.text() or "").strip()
                self.last_transcription = time.time() - getattr(self, "_rec_end", time.time())
            except Exception:  # noqa: BLE001 — the watchdog closed the old recorder
                continue
            if len(text) < 2 and self.awake() and not self.during_his_voice() and settings.load().get("stt") == "parakeet":
                from . import stt  # you're talking to him and nothing came out: don't lose it
                text = stt.second_try(getattr(self.rec, "last_transcription_bytes", None))
                print(time.strftime("%H:%M:%S"), "empty transcription, second try:", repr(text[:80]))
            called, request = split_wake(text)
            if not called and (rest := addressed.name_at_end(text)):  # "¿qué hora es, Jarvis?"
                called, request = True, rest
            if not called and self._woke_rec == self._ended_rec:  # he woke inside this very phrase, the full text lost the name
                if len(text.split()) <= 2:  # a lone "Jarvis" misheard ("Dervis"): not a request
                    called, request = True, ""
                elif settings.load().get("stt") == "parakeet":
                    from . import stt
                    # a guess (hinted Whisper) is only good for a lone "Jarvis": with more words after it, it was something else
                    if self._woke_guess or not stt.says_name(getattr(self.rec, "last_transcription_bytes", None)):
                        print(time.strftime("%H:%M:%S"), "woke by mistake, back to sleep:", text[:60])
                        self._sleep()
                        continue
            if (not called and len(text.split()) <= 2 and not self.awake() and not self.during_his_voice()
                    and settings.load().get("stt") == "parakeet"):
                from . import stt  # Parakeet can drop the name entirely (""), so this runs before the junk check
                if stt.says_name(getattr(self.rec, "last_transcription_bytes", None)):
                    print(time.strftime("%H:%M:%S"), "name found by the second check:", repr(text))
                    called, request = True, ""
            if not called and (len(text) < 2 or is_junk(text)):
                if not self.speaking:  # _stops showed "thinking": there's nothing to think about
                    self.state("listening" if self.awake() else "idle")
                continue
            open_mic = settings.load().get("open_mic") and not called and not self.during_his_voice()
            if open_mic and not (self.awake() and not self._asked):  # (awake after a bare "Jarvis": it's for him)
                from .panel import _pending
                if not (_pending and addressed.decide(text, True) == "maybe" and len(text.split()) <= 3):  # the yes/no he's waiting for
                    verdict = addressed.decide(text, time.time() < max(self._talk_until, self._awake_until))
                    every = settings.load().get("open_mic") == "all"
                    if every and verdict == "no" and (len(text.split()) >= 2 or addressed._REPLY.match(text)):
                        verdict = "all"  # your agent decides, with the whole conversation in mind
                    if verdict == "no":  # someone else's: silence, and not even the words in the log
                        print(time.strftime("%H:%M:%S"), f"overheard, not for him ({len(text.split())} words)")
                        if self._awake_until:
                            self._sleep()
                        continue
                    print(time.strftime("%H:%M:%S"), f"open mic, {'order' if verdict == 'yes' else 'maybe for him'}:", text[:80])
                    note = addressed.ORDER if verdict == "yes" else addressed.OPEN_ALL if every else addressed.OPEN_MIC
                    threading.Thread(target=self.on_heard, args=(request, note), daemon=True).start()
                    continue
            print(time.strftime("%H:%M:%S"), "heard:", text[:80])
            if self.during_his_voice():  # only "Jarvis…" or a stop phrase cut him off; the rest is his echo
                if echo_of(text, [s for _, s in getattr(self, "recent", [])]) and not is_stop(text):
                    print(time.strftime("%H:%M:%S"), "his own voice came back through the mic, ignored")
                    continue
                if settings.load().get("barge_in"):  # headphones: it's you, not his echo
                    self.on_barge()
                    if is_stop(text):
                        continue
                    called = True  # what you said over him is for him
                elif not (called or is_stop(text)):
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
            # stays awake while he thinks and talks (open mic: no need, what's for him gets through anyway)
            self._awake_until = 0.0 if settings.load().get("open_mic") else time.time() + 60
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
    said = ["Just a second, sir.", "I can't confirm it's on screen."]  # his own voice back through the mic vs. you over him
    assert echo_of("Just a second, sir.", said) and echo_of("I can't convert it's on screen.", said) and echo_of("sir", said)
    assert not echo_of("Jarvis, abrí Chrome", said) and not echo_of("Perdón que te corte, abrí Chrome", said)
    tone = 0.1 * np.sin(np.arange(8000) / 5).astype(np.float32)
    assert _paused(np.concatenate([tone, np.zeros(3200, np.float32)])) and not _paused(tone) and not _paused(np.zeros(9000, np.float32))
    print("voice ok; microphones:", ascii([n for _, n in microphones()]))
