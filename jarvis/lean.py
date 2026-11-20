"""Less RAM for the ears. install() before anything imports RealtimeSTT:

- torch (~270 MB across the orb and the mic reader): RealtimeSTT imports it only for torch.multiprocessing and
  torch.cuda.is_available(). With Parakeet (in-process) and the raw ONNX VAD nothing else needs it, so a tiny
  stand-in takes its place. Its Process wraps the target so the spawned mic reader installs it too before it
  imports RealtimeSTT. Not with Whisper on an NVIDIA card: there RealtimeSTT asks torch for CUDA.
- onnxruntime's memory arena: models keep reserving more with every phrase; off, they stay at their size
  (same speed, measured on Parakeet).
"""
from __future__ import annotations

import importlib
import multiprocessing
import sys
import types


def _run(module: str, name: str, args: tuple, kwargs: dict):
    install()
    return getattr(importlib.import_module(module), name)(*args, **kwargs)


class Process(multiprocessing.Process):
    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None, *, daemon=None):
        mod, qual = getattr(target, "__module__", None), getattr(target, "__qualname__", "")
        if mod == "__main__":  # run with -m: the child knows it by its real name
            mod = getattr(getattr(sys.modules["__main__"], "__spec__", None), "name", None)
        if mod and qual and "." not in qual and "<" not in qual:  # module-level function: importable in the child
            target, args, kwargs = _run, (mod, qual, tuple(args), dict(kwargs or {})), {}
        super().__init__(group, target, name, args, kwargs or {}, daemon=daemon)


def _no_torch() -> None:
    if "torch" in sys.modules:  # the real one is already loaded: nothing to save, don't fight it
        return
    mp = types.ModuleType("torch.multiprocessing")
    mp.__dict__.update({k: getattr(multiprocessing, k) for k in dir(multiprocessing) if not k.startswith("__")})
    mp.Process = Process
    torch = types.ModuleType("torch")
    torch.__path__ = []
    torch.jarvis_stand_in = True
    torch.multiprocessing = mp
    torch.cuda = types.SimpleNamespace(is_available=lambda: False, device_count=lambda: 0)
    torch.Tensor = type("Tensor", (), {})  # scipy/numpy array checks look it up when "torch" is loaded; nothing is one
    sys.modules["torch"], sys.modules["torch.multiprocessing"] = torch, mp


def _no_arena() -> None:
    import onnxruntime as ort
    if getattr(ort.SessionOptions, "jarvis_lean", False):
        return

    class Lean(ort.SessionOptions):
        jarvis_lean = True

        def __init__(self) -> None:
            super().__init__()
            self.enable_cpu_mem_arena = False
            self.enable_mem_pattern = False

    ort.SessionOptions = Lean


def _probe(q) -> None:  # self-test: runs in a spawned child
    import RealtimeSTT.core.runtime  # noqa: F401 — what the mic reader imports
    q.put(getattr(sys.modules.get("torch"), "jarvis_stand_in", False))


def install() -> None:
    from . import settings
    _no_arena()
    if settings.load().get("stt") == "parakeet":
        _no_torch()


if __name__ == "__main__":
    import onnxruntime as ort
    from . import settings
    assert "torch" not in sys.modules
    install()
    assert ort.SessionOptions().enable_cpu_mem_arena is False
    if settings.load().get("stt") == "parakeet":
        import torch.multiprocessing as tmp
        assert sys.modules["torch"].jarvis_stand_in and not sys.modules["torch"].cuda.is_available() and tmp.Event
        import RealtimeSTT  # noqa: F401 — imports with the stand-in
        q = tmp.Queue()
        p = tmp.Process(target=_probe, args=(q,))
        p.start(); p.join(60)
        assert q.get(timeout=5) is True, "the spawned child loaded the real torch"
    print("lean ok")
