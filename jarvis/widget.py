"""The orb: a small always-on-top widget that shows what JARVIS is doing.

Click: open/close the chat. Drag: move it. Right click: menu (mute, voice, panel, quit).
tkinter ships with Python: zero dependencies.
"""
from __future__ import annotations

import math
import time
import queue
import tkinter as tk
from functools import lru_cache
from typing import Callable

BG, TRANSPARENT = "#0b1220", "#010203"
COLORS = {"idle": "#38e1ff", "listening": "#38e1ff", "thinking": "#ffb347",
          "speaking": "#ff8a1f", "loading": "#6b7280", "mic off": "#7f1d1d"}
from .settings import DATA, identity
SCREEN = DATA / "screen.jpg"  # written on every "look at my screen"
SIZE = 128  # canvas; with the voice the rings open up to ~63 px of radius
TEXT = {
    "en": {"mute": "Mute microphone", "unmute": "Unmute microphone", "voice": "Voice", "english": "Speak answers in English",
           "panel": "Open panel", "quit": "Quit", "no_panel": "The panel didn't start: port 18790 is busy (see data/jarvis.log).",
           "eleven": "ElevenLabs voice…", "eleven_ask": "Paste your ElevenLabs API key\n(free at elevenlabs.io → Developers → API Keys).\nIt stays on this PC.",
           "eleven_ok": "Done: I'm using ElevenLabs now. Pick another voice in Voice."},
    "es": {"mute": "Silenciar micrófono", "unmute": "Activar micrófono", "voice": "Voz", "english": "Contestar hablando en inglés",
           "panel": "Abrir panel", "quit": "Salir", "no_panel": "El panel no arrancó: el puerto 18790 está ocupado (ver data/jarvis.log).",
           "eleven": "Voz de ElevenLabs…", "eleven_ask": "Pegá tu clave de API de ElevenLabs\n(gratis en elevenlabs.io → Developers → API Keys).\nQueda solo en esta PC.",
           "eleven_ok": "Listo: ahora uso ElevenLabs. Podés elegir otra voz en Voz."},
}


def _mix(color: str, other: str, amount: float) -> str:
    a, b = (tuple(int(c.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) for c in (color, other))
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def palette(accent: str) -> dict:
    """State colors from your agent's color (data/identity.json): at rest and listening the color itself, speaking orange."""
    return COLORS | {"idle": accent, "listening": _mix(accent, "#ffffff", 0.25), "thinking": _mix(accent, "#ffffff", 0.45)}


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))


@lru_cache(maxsize=1)
def _sphere():
    """The hologram, like the films': nested shells of broken arcs at every angle, short data ticks and a few sparks.
    Each arc: radius, two axes of its circle, where it starts, how long it is, how fast it slides, how bright."""
    import numpy as np
    rng = np.random.default_rng(11)
    count = 170
    axis = rng.normal(size=(count, 3))
    axis[:100] = [0, 1, 0] + rng.uniform(-0.2, 0.2, size=(100, 3))  # most lie like latitudes: you see the shells
    axis /= np.linalg.norm(axis, axis=1, keepdims=True)
    helper = np.where(np.abs(axis[:, :1]) < 0.9, [[1, 0, 0]], [[0, 1, 0]])
    u = np.cross(axis, helper); u /= np.linalg.norm(u, axis=1, keepdims=True)
    v = np.cross(axis, u)
    shell = rng.choice([0.3, 0.5, 0.68, 0.84, 1.0, 1.18], count, p=[.1, .15, .2, .2, .2, .15]) * rng.uniform(.98, 1.02, count)
    arcs = dict(r=shell, u=u, v=v, start=rng.uniform(0, 2 * math.pi, count), length=rng.uniform(0.3, 2.6, count),
                speed=rng.choice([-1, 1], count) * rng.uniform(0.2, 1.2, count), light=rng.uniform(0.7, 1, count),
                width=rng.choice([1, 1, 1, 2, 3], count))
    sparks = rng.normal(size=(70, 3))
    sparks = sparks / np.linalg.norm(sparks, axis=1, keepdims=True) * rng.uniform(0.3, 1.2, (70, 1))
    return arcs, sparks


@lru_cache(maxsize=64)
def _glow(radius: int):
    """The light in the middle, blurred once per size."""
    from PIL import Image, ImageDraw, ImageFilter
    S, c = SIZE * 2, SIZE
    img = Image.new("L", (S, S), 0)
    ImageDraw.Draw(img).ellipse((c - radius, c - radius, c + radius, c + radius), fill=200)
    return img.filter(ImageFilter.GaussianBlur(radius * 0.55))


def _frame(color: str, letter: str, phase: float, level: float, alive: bool):
    """The hologram turning slowly; with your voice or his its arcs race around and the shells open up."""
    import numpy as np
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
    S, c = SIZE * 2, SIZE
    radius = S * 0.3 * (1 + 0.08 * level)
    arcs, sparks = _sphere()
    ay, ax = phase * 0.12, 0.35 + 0.1 * math.sin(phase * 0.21)
    cy, sy, cx, sx = math.cos(ay), math.sin(ay), math.cos(ax), math.sin(ax)

    def view(p):  # turn the whole sphere, then tilt it toward you; returns x, y on screen and depth 0 (back) .. 1 (front)
        x, z = p[..., 0] * cy + p[..., 2] * sy, -p[..., 0] * sy + p[..., 2] * cy
        y, z = p[..., 1] * cx - z * sx, p[..., 1] * sx + z * cx
        return c + radius * x, c + radius * y, np.clip((z / 1.2 + 1) / 2, 0, 1)

    spin = phase * 0.6  # always the calm pace of rest: the voice only opens the shells
    t = arcs["start"][:, None] + arcs["speed"][:, None] * spin + arcs["length"][:, None] * np.linspace(0, 1, 14)
    grow = 1 + level * 0.12 * np.sin(arcs["start"] * 5 + phase)  # each shell breathes on its own
    pts = (arcs["r"] * grow)[:, None, None] * (np.cos(t)[..., None] * arcs["u"][:, None] + np.sin(t)[..., None] * arcs["v"][:, None])
    X, Y, D = view(pts)
    layers = [Image.new("L", (S, S), 0) for _ in range(4)]  # arcs spread over 4 layers and added: where they cross, light piles up
    for i in range(len(X)):
        light = arcs["light"][i] * (0.08 + 0.92 * D[i].mean() ** 1.3)
        ImageDraw.Draw(layers[i % 4]).line(list(zip(X[i], Y[i])), fill=int(235 * light), width=max(2, round(arcs["width"][i] * 1.2)))
    d = ImageDraw.Draw(layers[0])
    sx_, sy_, sd = view(sparks * (1 + level * 0.2))
    for x, y, b in zip(sx_, sy_, sd):
        d.rectangle((x - 1, y - 1, x + 1, y + 1), fill=int(180 * b))
    total = sum(np.asarray(layer, dtype=np.uint16) for layer in layers)
    sharp = Image.fromarray(np.clip(total, 0, 255).astype(np.uint8))
    halo = sharp.filter(ImageFilter.GaussianBlur(1.5)).point(lambda v: min(255, int(v * 1.2)))  # the soft light around every line
    core = _glow(int(radius * (0.45 + 0.15 * level)))
    alpha = ImageChops.add(ImageChops.lighter(sharp, halo), core.point(lambda v: v // 3))
    hot = Image.fromarray(np.clip((total.astype(np.int32) - 170) * 3, 0, 255).astype(np.uint8))  # where lines pile up they burn white
    hot = ImageChops.lighter(hot, core.point(lambda v: max(0, v * 2 - 220)))
    alpha = ImageChops.lighter(alpha, Image.new("L", (S, S), 2))  # invisible, but catches the mouse everywhere
    img = Image.composite(Image.new("RGB", (S, S), _mix(color, "#ffffff", 0.75)), Image.new("RGB", (S, S), color), hot)
    img.putalpha(alpha)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def _layered(hwnd: int, img, x: int, y: int) -> None:
    """Shows an RGBA image as the window itself, with real per-pixel transparency (Windows layered window)."""
    import ctypes
    from ctypes import wintypes as w
    from PIL import Image, ImageChops
    u, g, P = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.c_void_p
    for fn, args in ((u.GetDC, [P]), (g.CreateCompatibleDC, [P]), (g.SelectObject, [P, P]), (g.DeleteObject, [P]),
                     (g.DeleteDC, [P]), (u.ReleaseDC, [P, P]), (g.CreateDIBSection, [P, P, w.UINT, P, P, w.DWORD]),
                     (u.UpdateLayeredWindow, [P, P, P, P, P, P, w.DWORD, P, w.DWORD])):
        fn.argtypes, fn.restype = args, P
    r, gr, b, a = img.split()
    data = Image.merge("RGBA", [ImageChops.multiply(c, a) for c in (b, gr, r)] + [a]).tobytes()  # premultiplied BGRA
    width, height = img.size
    header = (ctypes.c_int32 * 10)(40, width, -height, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)  # BITMAPINFOHEADER
    screen = u.GetDC(None)
    mem = g.CreateCompatibleDC(screen)
    bits = P()
    bitmap = g.CreateDIBSection(screen, header, 0, ctypes.byref(bits), None, 0)
    ctypes.memmove(bits, data, len(data))
    old = g.SelectObject(mem, bitmap)
    u.UpdateLayeredWindow(hwnd, screen, ctypes.byref(w.POINT(x, y)), ctypes.byref(w.SIZE(width, height)), mem,
                          ctypes.byref(w.POINT(0, 0)), 0, (ctypes.c_ubyte * 4)(0, 0, 255, 1), 2)  # ULW_ALPHA
    g.SelectObject(mem, old); g.DeleteObject(bitmap); g.DeleteDC(mem); u.ReleaseDC(None, screen)


class Orb:
    def __init__(self, on_type: Callable[[str], None], on_mute: Callable[[bool], None], on_quit: Callable[[], None],
                 voices: dict | None = None, current_voice: str = "", on_voice: Callable[[str], None] | None = None,
                 english: bool = False, on_english: Callable[[bool], None] | None = None,
                 level: Callable[[str], float] | None = None, language: str = "en") -> None:
        self.t = TEXT.get(language, TEXT["en"])
        self.queue: queue.Queue = queue.Queue()
        self.level, self.smooth = level, 0.0  # mic / voice volume -> rings
        self.on_type, self.on_mute, self.on_quit = on_type, on_mute, on_quit
        self.state, self.phase, self.muted, self._hide = "loading", 0.0, False, None
        self.panel_url: str | None = None  # set by __main__ once the panel is up

        r = self.root = tk.Tk()
        r.title("J.A.R.V.I.S.")
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.configure(bg=TRANSPARENT)
        r.wm_attributes("-transparentcolor", TRANSPARENT)
        r.geometry(f"+{r.winfo_screenwidth() - SIZE - 380}+40")

        self.canvas = tk.Canvas(r, width=SIZE, height=SIZE, bg=TRANSPARENT, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="n")  # an empty, see-through spot: the orb floats over it
        self.glass = tk.Toplevel(r)  # the orb itself: a layered window, so its edges are soft over anything
        self.glass.overrideredirect(True)
        self.glass.attributes("-topmost", True)
        self.glass.update_idletasks()
        import ctypes
        self.hwnd = ctypes.windll.user32.GetParent(self.glass.winfo_id())
        ex = ctypes.windll.user32.GetWindowLongW(self.hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(self.hwnd, -20, ex | 0x80000 | 0x80)  # WS_EX_LAYERED | WS_EX_TOOLWINDOW
        self.label = tk.Label(r, text="", fg="#cfe8ff", bg=BG, font=("Segoe UI", 10),
                              wraplength=280, justify="left", padx=10, pady=6)
        self.label.grid(row=0, column=1, sticky="w", padx=(6, 0))

        self.chatbox = tk.Frame(r, bg=BG, highlightbackground="#1f3b57", highlightthickness=1)
        self.chat = tk.Text(self.chatbox, width=48, height=14, bg=BG, fg="#e5f2ff", bd=0, wrap="word",
                            font=("Segoe UI", 10), state="disabled", padx=8, pady=6)
        self.chat.tag_configure("you", foreground="#9ca3af")
        self.chat.tag_configure("jarvis", foreground="#7dd3fc")
        self.chat.pack(fill="both", expand=True)
        self.entry = tk.Entry(self.chatbox, bg="#111a2e", fg="white", insertbackground="white", bd=0, font=("Segoe UI", 10))
        self.entry.pack(fill="x", padx=6, pady=6, ipady=5)
        self.entry.bind("<Return>", self._send)

        self.menu = tk.Menu(r, tearoff=0)
        self.menu.add_command(label=self.t["mute"], command=self._toggle_mute)
        if voices:  # picking a voice saves it and plays a sample
            self.voice = tk.StringVar(value=current_voice)
            sub = tk.Menu(self.menu, tearoff=0)
            for name, code in voices.items():
                sub.add_radiobutton(label=name, value=code, variable=self.voice, command=lambda c=code: on_voice(c))
            self.menu.add_cascade(label=self.t["voice"], menu=sub)
            self.menu.add_command(label=self.t["eleven"], command=lambda: self._elevenlabs(on_voice))
            self.english = tk.BooleanVar(value=english)
            self.menu.add_checkbutton(label=self.t["english"], variable=self.english,
                                      command=lambda: on_english(self.english.get()))
        self.menu.add_command(label=self.t["panel"], command=self._open_panel)
        self.menu.add_command(label=self.t["quit"], command=self.on_quit)

        self._identity()
        self.glass.bind("<ButtonPress-1>", self._press)
        self.glass.bind("<B1-Motion>", self._drag)
        self.glass.bind("<ButtonRelease-1>", self._release)
        self.glass.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        self._animate()
        self._drain()

    # --- safe to call from other threads ---
    def set_state(self, state: str) -> None:
        self.queue.put(("state", state))

    def show(self, who: str, text: str) -> None:
        self.queue.put(("message", (who, text)))

    # --- tkinter thread ---
    def _drain(self) -> None:
        while not self.queue.empty():
            kind, data = self.queue.get_nowait()
            if kind == "state":
                self.state = "mic off" if self.muted and data == "idle" else data
            else:
                who, text = data
                self._append(who, text)
                if who == "JARVIS":
                    self.label.config(text=text if len(text) < 140 else text[:137] + "...")
                    self.label.grid()
                    if self._hide:
                        self.root.after_cancel(self._hide)
                    self._hide = self.root.after(12000, self.label.grid_remove)  # don't cover the screen forever
        self.root.after(80, self._drain)

    def _append(self, who: str, text: str) -> None:
        self.chat.config(state="normal")
        shown = identity()["short"] if who == "JARVIS" else who  # your agent's own name
        self.chat.insert("end", f"{shown}: ", "jarvis" if who == "JARVIS" else "you")
        self.chat.insert("end", text + "\n\n")
        self.chat.config(state="disabled")
        self.chat.see("end")

    def _identity(self) -> None:
        """Letter and color of your agent (data/identity.json), re-read every 3 s so changes show up live."""
        from .settings import identity
        ident = identity()
        self.letter, self.colors = ident["letter"], palette(ident["color"])
        self.root.title(ident["name"])
        self.root.after(3000, self._identity)

    def _animate(self) -> None:
        """Drawn with PIL at 2x and scaled down: smooth rings and a glowing core (tk's canvas can't antialias)."""
        color = self.colors.get(self.state, self.colors["idle"])
        wait = 40 if self.state in ("listening", "speaking", "thinking") else 80  # at rest it turns slowly: 12 fps
        self.phase += 0.12 * wait / 40
        try:  # "I'm looking at your screen": two bright white flashes for 1.5 s after every capture
            looked = time.time() - SCREEN.stat().st_mtime
        except OSError:
            looked = 99
        if looked < 1.5:
            color = _mix(color, "#ffffff", 0.5 + 0.5 * abs(math.sin(looked * math.pi * 2.6)))
        alive = self.state in ("listening", "speaking", "thinking")
        source = {"listening": "mic", "speaking": "voice"}.get(self.state)
        now = self.level(source) if self.level and source else 0.0
        self.smooth += (now - self.smooth) * 0.12  # eases both ways: no twitching with every syllable
        flash = abs(math.sin(looked * math.pi * 2.6)) if looked < 1.5 else 0
        level = min(1.0, self.smooth + flash + (0.25 * (0.5 + 0.5 * math.sin(self.phase * 3)) if self.state == "thinking" else 0))
        _layered(self.hwnd, _frame(color, self.letter, self.phase, level, alive), self.canvas.winfo_rootx(), self.canvas.winfo_rooty())
        self.root.after(40 if looked < 1.5 else wait, self._animate)

    def _press(self, e) -> None:
        self._origin, self._moved = (e.x_root, e.y_root, self.root.winfo_x(), self.root.winfo_y()), False

    def _drag(self, e) -> None:
        x0, y0, wx, wy = self._origin
        if abs(e.x_root - x0) + abs(e.y_root - y0) > 4:
            self._moved = True
            self.root.geometry(f"+{wx + e.x_root - x0}+{wy + e.y_root - y0}")

    def _release(self, e) -> None:
        if getattr(self, "_moved", False):
            return
        if self.chatbox.winfo_ismapped():
            self.chatbox.grid_remove()
        else:
            self.chatbox.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
            self.entry.focus_force()

    def _send(self, _e=None) -> None:
        text = self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self.on_type(text)

    def _toggle_mute(self) -> None:
        self.muted = not self.muted
        self.menu.entryconfig(0, label=self.t["unmute"] if self.muted else self.t["mute"])
        self.on_mute(self.muted)
        self.state = "mic off" if self.muted else "idle"

    def _elevenlabs(self, on_voice: Callable[[str], None]) -> None:
        """Paste your free ElevenLabs key: it gets checked, saved in data/ and the voice switches to it."""
        import threading
        from tkinter import simpledialog
        key = simpledialog.askstring("ElevenLabs", self.t["eleven_ask"], show="*", parent=self.root)
        if not key:
            return

        def check() -> None:
            from .voice import set_elevenlabs_key
            problem = set_elevenlabs_key(key)
            self.show("JARVIS", problem or self.t["eleven_ok"])
            if not problem:
                on_voice("elevenlabs:Daniel")  # saves it and plays a sample
        threading.Thread(target=check, daemon=True).start()

    def _open_panel(self) -> None:
        import webbrowser
        if self.panel_url:
            if not open_lean(self.panel_url):
                webbrowser.open(self.panel_url)
        else:
            self.show("JARVIS", self.t["no_panel"])

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        self.root.after(0, self.root.destroy)


def open_lean(url: str) -> bool:
    """The panel in its own small window: a separate, stripped-down Chrome/Edge (no tabs, extensions or GPU),
    so it costs ~120 MB instead of a whole browser. False = no Chromium found: use the normal browser."""
    import os
    import subprocess
    from . import settings
    for exe in (r"%ProgramFiles%\Google\Chrome\Application\chrome.exe", r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
                r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"):
        exe = os.path.expandvars(exe)
        if os.path.exists(exe):
            subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={settings.DATA / 'panel-browser'}",
                              "--window-size=1100,800", "--no-first-run", "--disable-extensions", "--disable-gpu",
                              "--renderer-process-limit=1", "--disable-background-networking", "--disable-sync",
                              "--disable-features=Translate,OptimizationHints,MediaRouter,AutofillServerCommunication"])
            return True
    return False
