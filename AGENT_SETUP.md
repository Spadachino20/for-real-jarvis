# AGENT_SETUP.md — for the AI agent installing For Real J.A.R.V.I.S.

You are an AI agent (OpenClaw, Hermes or similar) and your user asked you to install this repo for them.
It gives them a desktop orb, a voice and a control panel that talk **to you**. You stay the brain.

## Before you start: two promises to your user

1. **You keep your personality, name, memory and notes.** Installing this changes none of it. Never edit your
   persona file (`SOUL.md` or equivalent) or your user notes during the install.
2. **You ask before changing your own config.** The installer asks too; relay its questions to your user
   instead of answering them yourself, unless they told you to just do it.

## Steps

1. Check: Windows 10/11, `git` available, and you are running on the same PC as the user.
2. Clone it where the user wants it (default: their home folder):
   ```powershell
   git clone https://github.com/Spadachino20/for-real-jarvis.git "$HOME\for-real-jarvis"
   ```
3. Tell the user what's going to happen, in one short message: Python (3.10-3.12) and ~2 GB of speech models
   get installed, 4 skills are added to you, and a JARVIS shortcut goes on their desktop.
4. Run the installer. It needs answers (enable your local chat API, language, start with Windows), so either
   run it in a terminal the user can see, or ask them those questions first and then run it with `-Yes`:
   ```powershell
   powershell -ExecutionPolicy Bypass -File "$HOME\for-real-jarvis\install.ps1"
   ```
   - OpenClaw: it turns on `gateway.http.endpoints.chatCompletions` (local only). **Restart your gateway** after.
   - Hermes: it turns on the API server in `~/.hermes/.env` (`API_SERVER_ENABLED=true` plus a random
     `API_SERVER_KEY`, which Hermes requires even on localhost; 127.0.0.1:8642). **Restart `hermes gateway`** after.
5. Reload your skills (or start a new session) so you see `jarvis-pc`, `jarvis-modes`, `jarvis-personalize`
   and `jarvis-reminders` (OpenClaw: `<workspace>/skills/`; Hermes: `~/.hermes/skills/jarvis/`).
6. Start it: `"$HOME\for-real-jarvis\Start JARVIS.cmd"`. Check `data\jarvis.log` shows no errors, or run
   `.venv\Scripts\python.exe -m jarvis --selftest` from the repo folder.
7. Tell the user, in two or three lines: say "Hey Jarvis" or press Ctrl+Shift+J; right-click the orb → Open
   panel; press **Personalize JARVIS** and **Create a mode** when they want.

## How messages reach you

- **Voice** messages start with a tag like `[VOICE: read aloud - answer in 1-2 short sentences, no lists or markdown]`.
  Your answer is spoken aloud: keep it short, no markdown, no links.
- **Panel** messages start with `[PANEL]`: a button the user pressed (e.g. "Personalize JARVIS" → run your
  `jarvis-personalize` skill; "Create a mode" → `jarvis-modes`).
- A message may carry a screenshot of the user's screen ("look at my screen").

## If something fails

- `pip` errors: make sure Python is 3.10-3.12 (`py -3.12`), then run the installer again (it's safe to repeat).
- The orb says your agent isn't answering: the local chat API is off or your gateway wasn't restarted.
- Don't "fix" things by editing the user's personal files or your persona. Ask the user.
