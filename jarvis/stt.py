"""Parakeet TDT 0.6B v3 (onnx-asr, CPU) as a RealtimeSTT engine: ~10x faster than Whisper small, same accuracy
on ST's voice. Settings "stt": "parakeet" turns it on (pip install "onnx-asr[cpu,hub]").

It's handed to RealtimeSTT as transcription_executor, so it runs in JARVIS's own process (no spawned worker).
"""
from __future__ import annotations

import re
from functools import cache

from RealtimeSTT.transcription_engines.base import (BaseTranscriptionEngine, TranscriptionEngineConfig,
                                                    TranscriptionInfo, TranscriptionResult)

from . import settings


def fix(text: str, fixes: dict[str, str]) -> str:
    """Settings "stt_fixes" {regex: replacement}: what Parakeet keeps mishearing (it has no prompt to bias it)."""
    for pattern, repl in fixes.items():
        text = re.sub(pattern, repl, text, flags=re.I)
    return text


class OnnxParakeet(BaseTranscriptionEngine):

    def __init__(self, config) -> None:
        super().__init__(config)
        import onnx_asr
        self.model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", quantization="int8")

    def transcribe(self, audio, language=None, use_prompt=True, **kwargs) -> TranscriptionResult:
        text = self.model.recognize(self._normalize_audio(audio), sample_rate=16000).strip() if len(audio) else ""
        text = fix(text, settings.load().get("stt_fixes") or {})
        return TranscriptionResult(text=text, info=TranscriptionInfo(language=language, language_probability=1.0 if text else 0.0))


@cache  # loaded once: the watchdog rebuilds the recorder, not the model
def engine() -> OnnxParakeet:
    return OnnxParakeet(TranscriptionEngineConfig(model="parakeet"))


@cache
def _whisper():
    from faster_whisper import WhisperModel
    return WhisperModel("base", device="cpu", compute_type="int8")


def says_name(audio) -> bool:
    """Parakeet can't be told the name: "Jarvis" alone comes out "Java's". When it found no name, a small
    Whisper hinted with the name listens to the first 2.5 s only (~0.3 s on CPU)."""
    import numpy as np
    from .voice import split_wake
    if audio is None or not len(audio):
        return False
    head = np.asarray(audio, np.float32)[:40000]
    if np.sqrt((head ** 2).mean()) < settings.load().get("name_check_min_rms", 0.006):
        return False  # noise or silence: a hinted Whisper would "hear" the name in it (your voice: ~0.013-0.02)
    segs, _ = _whisper().transcribe(head, beam_size=5, initial_prompt=f"{settings.identity()['short'].title()}.",
                                    language=settings.load()["language"] if settings.load()["language"] in ("es", "en") else None)
    return split_wake(" ".join(s.text for s in segs))[0]


if __name__ == "__main__":
    import numpy as np
    f = {r"^hello\W*$": "Hacelo.", r"\brama\b": "RAM"}
    assert fix("Hello.", f) == "Hacelo." and fix("Hello Jarvis", f) == "Hello Jarvis"
    assert fix("Cuánta memoria Rama tengo", f) == "Cuánta memoria RAM tengo" and fix("Ramallo", f) == "Ramallo"
    e = engine()
    assert engine() is e
    assert e.transcribe(np.zeros(0, np.float32)).text == ""
    assert e.transcribe(np.zeros(16000, np.float32)).text == ""
    print("ok")
