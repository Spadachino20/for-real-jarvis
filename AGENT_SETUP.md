# AGENT_SETUP.md — for the AI agent installing For Real J.A.R.V.I.S.

You are an AI agent (OpenClaw, Hermes, Claude Code or similar) and your user asked you to install this repo for them.
It gives them a desktop orb, a voice and a control panel that talk **to you**. You stay the brain.

## Before you start: two promises to your user

1. **You keep your personality, name, memory and notes.** Installing this changes none of it. Never edit your
   persona file (`SOUL.md` or equivalent) or your user notes during the install.
2. **You ask before changing your own config.** The installer asks too; relay its questions to your user
   instead of answering them yourself, unless they told you to just do it.

## Steps

1. Check: Windows 10/11 (not inside WSL), `git` available, and you are running on the same PC as the user. **Python 3.12**, installed normally in
   Windows: not one that belongs to another app's private folder (it won't exist when the orb starts). If it's missing, ask the user to install it.
   Already cloned? Go to [Updating](#updating) instead.
2. Clone it where the user wants it (default: their home folder):
   ```powershell
   git clone https://github.com/Spadachino20/for-real-jarvis.git "$HOME\for-real-jarvis"
   ```
3. **Ask your user, in ONE message, and wait for the answers: who lives in the orb?**
   - **You** (recommended): the orb takes your name, your letter and your color, and it wakes up to your name. You keep your model,
     so there's nothing to pay or configure. If you were just created and have no name yet, ask them for one first and save it in your persona.
   - **A separate JARVIS**: you stay where you are and JARVIS starts from zero, as a second OpenClaw agent (same model and keys as you)
     or with Claude Code (a Claude plan). Only one orb runs at a time.
   Then offer the extras in the same message: **Parakeet** (ears ~10x faster, +670 MB) and **open mic** (answers orders without his name;
   what's said near the PC and may be for him goes to the model). Off by default. And: language (English or Spanish), and whether it starts with Windows.
4. Tell the user what's going to happen, in one short message: Python 3.12 and ~2 GB of speech models
   get installed, 4 skills are added to you, and a JARVIS shortcut goes on their desktop.
5. Run the installer with what they answered. `-Yes` also turns on your local chat API and, for a separate JARVIS, adds the second agent
   to your OpenClaw: **say so in that same message and only go on with their yes.** The first run downloads ~2 GB and can take 10-30 minutes:
   run it in the background (or with a timeout of at least 45 minutes) and don't start it twice.
   ```powershell
   powershell -ExecutionPolicy Bypass -File "$HOME\for-real-jarvis\install.ps1"
   # you stay the brain:        install.ps1 -Yes -Who agent -Lang en   (-Which openclaw|hermes if the PC has both)
   # a separate JARVIS:         install.ps1 -Yes -Who jarvis -Brain openclaw -Lang en   (or -Brain claude)
   # if they want them:         -Extras "parakeet,openmic"     if they don't want it with Windows:  -NoAutostart
   ```
   - OpenClaw: it turns on `gateway.http.endpoints.chatCompletions` (local only, with your gateway token). OpenClaw usually applies it by itself.
   - Hermes: it turns on the API server in its `.env` (`%LOCALAPPDATA%\hermes` on native Windows, or `~/.hermes`) (`API_SERVER_ENABLED=true` plus a random
     `API_SERVER_KEY`, which Hermes requires even on localhost; 127.0.0.1:8642). It needs a gateway restart (step 7).
6. Reload your skills (or start a new session) so you see `jarvis-pc`, `jarvis-modes`, `jarvis-personalize`
   and `jarvis-reminders` (OpenClaw: `<workspace>/skills/`; Hermes: `<its folder>/skills/jarvis/`).
7. Check that the orb can reach the brain: `.venv\Scripts\python.exe -m jarvis --check-agent` (from the repo folder; the installer already does it
   at the end). If it doesn't answer, the gateway needs a restart: **that cuts you off**, so tell your user first and ask them to do it
   (OpenClaw: `openclaw gateway restart`; Hermes: close your chat, `hermes gateway stop`, then `hermes gateway run` in a window that stays open). Don't tell them it's ready until it says it answers.
8. `-Yes` already started it. If not: `explorer.exe "$HOME\for-real-jarvis\Start JARVIS.cmd"` (through Explorer, so it doesn't close with your command). Check `data\jarvis.log` shows no errors, or run
   `.venv\Scripts\python.exe -m jarvis --selftest` from the repo folder.
9. The first start asks you, in a side conversation, for your name and color as JSON: answer it, that's where the orb's letter comes from
   (`data\identity.json`). Check that it shows your name; if it was skipped, the `jarvis-personalize` skill writes it.
10. Tell the user, in two or three lines: say "Hey <your name>" (or "Hey Jarvis") or press Ctrl+Shift+J; right-click the orb → Open
   panel; press **Personalize JARVIS** and **Create a mode** when they want.

## Updating

1. `git pull` in the folder they have it in. Local changes in the way: show them and ask, never discard them. Then read this file again.
2. Ask them to close the orb (right click → Quit). If `.venv` isn't Python 3.12 (`.venv\Scripts\python.exe --version`), rename it to `.venv-old`.
3. Run `install.ps1` again, like in step 5. It keeps `data\settings.json` as it is. To connect it again from zero (it talks to the wrong agent, or
   the orb never took your name), rename `data\settings.json` and `data\identity.json` to `.bak` first, with their yes: they lose their settings.
4. Steps 7 to 10. Changed your name, persona or model and the orb doesn't notice? The gateway keeps the old one in memory: it needs a restart too.

## How messages reach you

- **Voice** messages start with a tag like `[VOICE: read aloud - answer in 1-2 short sentences, no lists or markdown]`.
  Your answer is spoken aloud: keep it short, no markdown, no links.
- **Panel** messages start with `[PANEL]`: a button the user pressed (e.g. "Personalize JARVIS" → run your
  `jarvis-personalize` skill; "Create a mode" → `jarvis-modes`).
- A message may carry a screenshot of the user's screen ("look at my screen").

## If something fails

- `pip` errors: make sure Python is 3.12 (`py -3.12`), then run the installer again (it's safe to repeat).
- The orb says your agent isn't answering: the local chat API is off or your gateway wasn't restarted.
- The orb shows the wrong name or letter: delete `data\identity.json` and restart it; it asks again.
- It talks to the wrong agent: `agent.model` (`openclaw/<agent id>`) and `agent.session` (`agent:<agent id>:main`) in `data\settings.json`.
- To choose again who lives in the orb: rename `data\settings.json` and `data\identity.json`, and run the installer.
- The orb appears but doesn't hear, or `jarvis.log` says `No module named ...`: `.venv\Scripts\python.exe -m pip install -r requirements.txt`.
- "No Python at ...": `.venv` points to a Python that isn't there. Rename `.venv`, install Python 3.12, and run the installer again.
- Nothing of this works: give your user the exact error and the last 30 lines of `data\jarvis.log`, without keys or personal data. Don't improvise.
- Don't "fix" things by editing the user's personal files or your persona. Ask the user.
