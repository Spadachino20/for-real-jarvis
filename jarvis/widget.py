"""The orb: a small always-on-top widget that shows what JARVIS is doing.

Click: open/close the chat. Drag: move it. Right click: menu (mute, voice, panel, quit).
tkinter ships with Python: zero dependencies.
"""
from __future__ import annotations

import math
import queue
import tkinter as tk
from typing import Callable

BG, TRANSPARENT = "#0b1220", "#010203"
COLORS = {"idle": "#2b6f8a", "listening": "#38e1ff", "thinking": "#ffb347",
          "speaking": "#4f9dff", "loading": "#6b7280", "mic off": "#7f1d1d"}
SIZE = 128  # canvas; with the voice the rings open up to ~63 px of radius
TEXT = {
    "en": {"mute": "Mute microphone", "unmute": "Unmute microphone", "voice": "Voice", "english": "Speak answers in English",
           "panel": "Open panel", "quit": "Quit", "no_panel": "The panel didn't start: port 18790 is busy (see data/jarvis.log)."},
    "es": {"mute": "Silenciar micrófono", "unmute": "Activar micrófono", "voice": "Voz", "english": "Contestar hablando en inglés",
           "panel": "Abrir panel", "quit": "Salir", "no_panel": "El panel no arrancó: el puerto 18790 está ocupado (ver data/jarvis.log)."},
}


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
        self.canvas.grid(row=0, column=0, sticky="n")
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
            self.english = tk.BooleanVar(value=english)
            self.menu.add_checkbutton(label=self.t["english"], variable=self.english,
                                      command=lambda: on_english(self.english.get()))
        self.menu.add_command(label=self.t["panel"], command=self._open_panel)
        self.menu.add_command(label=self.t["quit"], command=self.on_quit)

        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
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
        self.chat.insert("end", f"{who}: ", "jarvis" if who == "JARVIS" else "you")
        self.chat.insert("end", text + "\n\n")
        self.chat.config(state="disabled")
        self.chat.see("end")

    def _animate(self) -> None:
        c, m = self.canvas, SIZE / 2
        c.delete("all")
        color = COLORS.get(self.state, COLORS["idle"])
        self.phase += 0.12
        alive = self.state in ("listening", "speaking", "thinking")
        source = {"listening": "mic", "speaking": "voice"}.get(self.state)
        now = self.level(source) if self.level and source else 0.0
        self.smooth = max(now, self.smooth * 0.75)  # jumps up, eases down
        for i in range(3):  # rings breathe and open with the volume (outer ones more)
            radius = 30 + i * 8 + math.sin(self.phase * (2 if alive else 0.6) + i) * (4 if alive else 1.5) \
                + self.smooth * (5 + i * 4)
            c.create_oval(m - radius, m - radius, m + radius, m + radius, outline=color, width=2 if i == 0 else 1)
        if self.state == "thinking":  # spinning arc
            c.create_arc(m - 44, m - 44, m + 44, m + 44, start=(self.phase * 90) % 360, extent=70,
                         outline="#ffd08a", style="arc", width=3)
        c.create_oval(m - 22, m - 22, m + 22, m + 22, fill=BG, outline=color, width=2)
        c.create_text(m, m, text="J", fill=color, font=("Segoe UI Semibold", 18))
        self.root.after(40, self._animate)

    def _press(self, e) -> None:
        self._origin, self._moved = (e.x_root, e.y_root, self.root.winfo_x(), self.root.winfo_y()), False

    def _drag(self, e) -> None:
        x0, y0, wx, wy = self._origin
        if abs(e.x_root - x0) + abs(e.y_root - y0) > 4:
            self._moved = True
            self.root.geometry(f"+{wx + e.x_root - x0}+{wy + e.y_root - y0}")

    def _release(self, e) -> None:
        if self._moved:
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

    def _open_panel(self) -> None:
        import webbrowser
        if self.panel_url:
            webbrowser.open(self.panel_url)
        else:
            self.show("JARVIS", self.t["no_panel"])

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        self.root.after(0, self.root.destroy)
