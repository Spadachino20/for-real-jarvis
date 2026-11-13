<p align="center"><img src="jarvis/static/orb-192.png" width="120" alt="The JARVIS orb"></p>

<h1 align="center">For Real J.A.R.V.I.S.</h1>

<p align="center"><b>The real JARVIS on your Windows desktop: a voice, an orb and a control panel for <i>your own</i> AI agent.</b></p>

---

Most "JARVIS" projects are a chatbot with a nice skin. This one is a **door to a real agent** that already
lives on your PC: [OpenClaw](https://github.com/openclaw/openclaw) or [Hermes Agent](https://github.com/NousResearch/hermes-agent).
Your agent keeps its brain, memory, tools and channels (WhatsApp, Telegram, Discord...). This repo gives it:

- 🟦 **An orb** that floats over your screen and shows what JARVIS is doing (listening, thinking, speaking).
- 🎙️ **A voice**: say *"Hey Jarvis"* (or press **Ctrl+Shift+J**), talk, and cut him off with *"stop"*.
- 👀 **"Look at my screen"**: he sees what you see.
- 🖥️ **PC control**: open/close apps, music, volume, files, YouTube, clipboard, dictation, PC health.
- ⚡ **Modes** you build *with* JARVIS: one phrase sets up your PC ("work mode", "let's play").
- 🧠 **Personalization**: JARVIS interviews you and remembers what matters.
- 📊 **A panel** (installable as an app): chat, modes, token usage, automations, sessions, PC and logs.

It ships as a **skeleton**: no modes, no personality, nothing about anyone. JARVIS builds those with you.

## What you need

| | |
|---|---|
| Windows 10 or 11 | the orb, the voice and the PC control are Windows-only |
| An AI agent running on your PC | **OpenClaw** (recommended: the full panel works) or **Hermes Agent** |
| Python 3.10 - 3.12 | the installer offers to install it |
| A microphone | headphones work best (he won't hear himself) |

### Don't have an agent yet?

JARVIS needs a brain first. Create one here, then come back:

- **OpenClaw** → [github.com/openclaw/openclaw](https://github.com/openclaw/openclaw) (recommended)
- **Hermes Agent** → [github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)

### Already have one? Your agent can install this for you

Just send your agent this message:

> Install For Real J.A.R.V.I.S. for me: https://github.com/Spadachino20/for-real-jarvis — follow AGENT_SETUP.md.

It clones the repo, runs the installer and connects itself. **Your agent keeps its own personality, name,
memory and notes.** JARVIS only changes its personality if *you* ask for it (see [Personalize](#personalize-jarvis)).

## Install it yourself

```powershell
git clone https://github.com/Spadachino20/for-real-jarvis.git
cd for-real-jarvis
powershell -ExecutionPolicy Bypass -File install.ps1
```

The installer finds your agent, sets up Python and the voice, copies 4 skills into your agent
(`jarvis-pc`, `jarvis-modes`, `jarvis-personalize`, `jarvis-reminders`) and puts a **JARVIS** shortcut with the
orb on your desktop. It asks before changing anything in your agent's config, and you can run it again any time.

## First steps

1. Double-click **JARVIS** on your desktop. The orb appears at the top right (the first start takes ~20 s).
2. Say **"Hey Jarvis, what time is it?"**, or just "Jarvis", wait for the beep, and ask.
3. Right-click the orb → **Open panel** → **Personalize JARVIS**. He'll ask you a few questions.
4. In the panel → **Create a mode**. He'll build your first mode with you.

Tip: in Chrome or Edge, open the panel and choose **Install app**: it gets its own window and the orb icon,
and you can pin it to the taskbar.

## Personalize JARVIS

Press **Personalize JARVIS** in the panel (or say *"personalize JARVIS"*). Your agent will:

1. Ask whether to **keep its current personality** (the default) or take on JARVIS's (the calm, dry-witted
   butler from the movies).
2. Interview you, one question at a time: your name, language, what you do, your apps, how you like answers...
3. Show you what it learned and **only save it if you say yes**. It *adds* to what it already knows about you;
   it never wipes your notes.

Run it again whenever you want.

### Your agent's name and color on the orb

Is your agent called F.R.I.D.A.Y., EDITH or ULTRON? During the interview it can put **its own name, letter and
color** on the orb and the panel (and wake up to "Hey Friday"). It just writes one small file:

```json
// data/identity.json
{ "name": "F.R.I.D.A.Y.", "letter": "F", "color": "#ff8a3d" }
```

Change it any time (or ask your agent to). Delete it to go back to J.A.R.V.I.S.

## Modes

A mode is one phrase that sets up your PC: it opens apps, closes the ones in the way, plays a Spotify playlist
and can even change how JARVIS works (for example, "short technical answers" in a coding mode).

The repo ships **none**. Press **Create a mode** in the panel (or say *"create a work mode"*) and JARVIS asks you:
what's it for, what to open, what to close, which playlist, and if he should behave differently. He saves it in
`data/modes.json`, and it shows up as a button in the panel. Then say *"work mode"* or click it.

<details>
<summary>The format, if you want to edit it by hand</summary>

```json
{
  "modes": [
    {
      "id": "work",
      "title": "Work",
      "description": "Focus playlist, editor open, no distractions",
      "icon": "briefcase",
      "open": ["Code", "https://calendar.google.com"],
      "close": ["Discord", "steam"],
      "playlist": "spotify:playlist:XXXXXXXXXXXXXXXXXXXXXX",
      "playlist_name": "Focus",
      "tell_agent": "Work mode: short, technical answers.",
      "exit_message": "Left work mode: back to normal.",
      "confirm": "This closes Discord and Steam. Continue?"
    }
  ]
}
```

- `open`: Start-menu app names, `.lnk` / `.exe` paths, folders or URLs. `close`: process names without `.exe`.
- `tell_agent` / `exit_message`: what your agent should do while the mode is on, and when you leave it.
- `icon`: `briefcase`, `code`, `gamepad`, `car`, `shield`, `book`, `moon`, `music` or `bolt`.
</details>

## What you can say

| | |
|---|---|
| "Open Spotify" / "Close Discord" | apps, Store apps included |
| "Pause", "next song", "what's playing?", "turn it up" | music and volume |
| "Find my CV and open it" | Windows search |
| "Play lofi on YouTube" | first video, playing |
| "Look at my screen: where's the save button?" | screenshot + your agent's eyes |
| "How's my PC?" | CPU, RAM, disks, blue screens |
| "Translate what I copied and leave it copied" | clipboard |
| "Type: see you at five" | types where your cursor is |
| "Remind me in 10 minutes to drink water" | arrives on your chat channel |
| "Work mode", "let's play F1" | your modes |
| "Stop" / "Jarvis, …" while he talks | cuts him off |

## The panel

`http://127.0.0.1:18790` (right-click the orb → Open panel). Sections: **Home** (orb, summary, modes),
**Chat** (the same conversation as the orb), **Modes**, **Tokens** (30 days, per day, session and model),
**Automations** (run / pause), **Sessions**, **PC** and **Logs**.

Tokens, Automations, Sessions and Logs come from the OpenClaw gateway; with Hermes those sections say so.
The panel only answers on this PC, and its buttons need a key that changes on every start, so no website
you visit can press them.

## Settings

`data/settings.json` (created by the installer; every key is optional):

| Key | Default | |
|---|---|---|
| `agent.kind` | `openclaw` | `openclaw`, `hermes` or `openai` (any OpenAI-compatible agent) |
| `agent.url` / `agent.model` | OpenClaw's | Hermes: `http://127.0.0.1:8642` / `hermes-agent` |
| `agent.token` | read from OpenClaw | Hermes: your `API_SERVER_KEY` |
| `agent.restart_command` | — | a command to bring your agent back if it goes down |
| `language` | `en` | `en` or `es`: what you speak, and the panel's language |
| `speak_english` | `true` | spoken answers in English even if you speak Spanish |
| `voice` | `bm_lewis` | any Kokoro voice, or `elevenlabs:<voice>` with your key in `data/elevenlabs.key` |
| `microphone` / `output` | Windows default | part of the device name (`python -m jarvis --mics` picks the best mic) |
| `hotkey` | `ctrl+shift+j` | e.g. `ctrl+shift+f9`, `pause` |
| `interruptible` | `true` | set `false` if you use speakers instead of headphones |

Everything personal (settings, modes, keys, logs) lives in `data/`, which never leaves your PC.

## Troubleshooting

- **I don't see the orb** → double-click **JARVIS** on the desktop: it restarts it.
- **"Your agent isn't answering"** → start your agent (`openclaw gateway` / `hermes gateway`). For OpenClaw,
  check `gateway.http.endpoints.chatCompletions.enabled` is `true`.
- **He hears himself** → use headphones, or set `"interruptible": false`.
- **He doesn't hear me** → `.venv\Scripts\python.exe -m jarvis --mics`.
- **Everything else** → `.venv\Scripts\python.exe -m jarvis --selftest` and `data\jarvis.log`.

## How it's built

```
jarvis/
  __main__.py   starts the orb, the ears and the panel
  brain.py      talks to your agent (OpenAI-compatible API on localhost)
  voice.py      ears (RealtimeSTT: Silero VAD + faster-whisper) and voice (Kokoro / ElevenLabs)
  widget.py     the orb (tkinter)
  panel.py      the panel's server (Python's http.server) + panel.html
  gateway.py    OpenClaw gateway client (WebSocket RPC) for tokens, automations, sessions and logs
skills/         what your agent learns: PC control, modes, personalization, reminders
install.ps1     the one-step installer
```

## License

[PolyForm Noncommercial 1.0.0](LICENSE.md): free to use, change and share **for non-commercial purposes**.
Selling it, or using it to make money, needs the author's permission.

"J.A.R.V.I.S." is a nod to the films; this is an independent fan project, not affiliated with Marvel or Disney.
