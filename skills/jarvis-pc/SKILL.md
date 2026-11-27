---
name: jarvis-pc
description: >
  Use for anything on the user's Windows PC: open or close programs (Microsoft Store apps too), control music
  (play, pause, next, what's playing) and volume, find and open files, play a YouTube video, open websites,
  check how the PC is doing, read/copy the clipboard, type text where the cursor is, take a screenshot, and run
  the user's modes ("work mode", "let's play X"). Examples: "open Spotify", "pause", "next song", "what's
  playing?", "turn it up", "find my CV and open it", "play lofi on YouTube", "how's my PC?", "translate what I
  copied", "type: see you at 5", "work mode".
---

# Operate the PC (For Real J.A.R.V.I.S.)

Don't write PowerShell by hand for these: use the shortcut, already tested, which answers in one line with the
real result. Run it with your shell/exec tool:

```
powershell -NoProfile -ExecutionPolicy Bypass -File "{{JARVIS_HOME}}\skills\jarvis-pc\pc.ps1" <action> <argument>
```

| Request | Action |
|---|---|
| "open Spotify / Chrome / WhatsApp" | `open spotify` (Start menu name, Store apps included) |
| "open downloads / documents / desktop", a path or a URL | `open downloads` |
| "close Spotify" | `close spotify` |
| "play music", "resume" / "pause" | `music play` / `music pause` (not a toggle: pause stays paused) |
| "next" / "previous" / "what's playing?" | `music next` / `music previous` / `music status` |
| "turn it up / down", "mute" | `volume up` / `volume down` (5 steps = 10 %; add a number for more), `volume mute` |
| "find the file X" | `find X` → paths (Windows index, ~1 s); then `open <path>` |
| "send me … on WhatsApp", "WhatsApp me a summary" | `whatsapp-me '<text>'` → to his own chat (needs OpenClaw on); `\n` for each new line, all the details he asked for |
| "play X on YouTube Music", "put on a Christmas playlist in YouTube Music" | `ytmusic X` → finds a playlist and plays it in his installed YouTube Music app (never plain YouTube); a link works too |
| "open my X" and `open` didn't find it | `apps X` → the apps and shortcuts that match; then `open` the exact name or path |
| press a button/tab/link in an app ("dale play", "next tab") | `click 'Play' [window]`; keys: `keys '{ENTER}'`, `keys '^l'` |
| "play X on YouTube" / "give me the link to X" | `youtube X` (opens the first video) / `youtube-link X` (title and link only) |
| "open YouTube / Instagram / TikTok / X / Gmail / the panel" | `open youtube` (or that name) |
| "how's my PC?", "why is it slow?" | `pc-status` → CPU, RAM, disks, top memory users, blue screens and hard shutdowns |
| "summarize / translate / fix what I copied" | `clipboard` → do what was asked with that text |
| "…and leave it copied" | `copy '<text>'` |
| "type: …", "dictate: …" | `type '<text>'` → pasted where the cursor is; the clipboard is restored |
| check something on screen | `screenshot` → then look at the image file it returns |
| "work mode", "let's play X", any of the user's modes | `modes` to list them, `mode <id>` to run one |

## Figure it out (never "I can't" after one try)

Small PC things (open an app, play something, press a button) are yours to solve. When the first way fails or the
output isn't what he asked for, try the next rung yourself, without asking him:

1. The shortcut for it (`open X`, `ytmusic X`, `music play`...).
2. `apps <word>` → every app and shortcut with that word (web apps installed from Chrome/Edge too): `open` the exact one.
3. A link in his browser, or the app's own address (music.youtube.com, web.whatsapp.com...).
4. Look and act: `screenshot` to see the screen, then `click '<text on it>' [window]` (buttons, tabs, links, "Play"),
   `keys` (`^l`, `{ENTER}`, `{TAB}`) and `type` for search boxes; screenshot again to check.

Only after rung 4, tell him in one line what you tried and what's blocking. When he corrects how he wants something
done ("YouTube Music means my app"), save it to memory so the next time the first try is the right one.

## Rules

- The shortcut's output IS the verification: no screenshot needed to confirm music or volume.
- Say only what the output confirms. `open` answers "opened (running: ...)" only when the app really is running;
  "did NOT open" or "NOT closed" means it failed: tell him so, never "it's open". "sent to Windows" (a URL or
  folder) means you sent it, not that you saw it.
- "Play music" with Spotify closed: `open spotify`, wait 5 s, `music play`, `music status`.
- `type` writes exactly what the user said (only punctuation and capitals) unless they ask you to rewrite it.
  In PowerShell the text goes in single quotes: double any `'` inside it.
- Modes: run `mode <id>` and report its line in one sentence. If the output contains
  `INSTRUCTION FOR THE AGENT: …`, follow that instruction from now on (until the user leaves the mode).
  The name comes from speech recognition and may be misheard ("força" = forza, "f uno" = f1): pick the
  closest mode id from `modes` and run it. Only if none is close, offer to create it with the jarvis-modes skill. Never invent a mode.
- On social networks only open and look: never post, comment, like or send messages without the user's
  explicit permission for that specific message.
- Closing a program with unsaved work (Word, editors): ask first.
- `pc-status`: summarize it in two spoken sentences, worst thing first. Don't make up temperatures: Windows
  doesn't give them without admin rights.
