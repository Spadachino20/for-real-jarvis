---
name: jarvis-modes
description: >
  Use when the user wants to create, change, list or delete a "mode": one phrase that sets up the PC for
  something (work, gaming, studying, sleeping...). Examples: "create a work mode", "make a gaming mode for
  Forza", "add Discord to my work mode", "delete the study mode", "what modes do I have?". Also when the
  panel says the user pressed "Create a mode".
---

# Build modes with the user (For Real J.A.R.V.I.S.)

A mode is one entry in `{{JARVIS_HOME}}\data\modes.json`. The panel shows every mode as a button, and the
jarvis-pc skill runs it (`mode <id>`). The repo ships **no** modes: you build them **with** the user.

## The interview (one question at a time, short, wait for each answer)

1. **What is it for?** ("working", "playing F1"...) → that gives the `title`, the `id` and the `description`.
2. **What should open?** Apps, games, folders, websites. For each one find the real target:
   - Start menu apps: just the name (`Claude`, `Spotify`) - check it with `Get-StartApps | ? Name -like '*name*'`.
   - Games and tools: look for the shortcut first (`$HOME\Desktop`, `C:\Users\Public\Desktop`, Start menu) and
     use the `.lnk` path; for an `.exe` use its full path (the mode skips it if it's already running).
   - Websites: the URL.
3. **What should close?** Background apps that get in the way (Discord, Steam, launchers...). Use process
   names without `.exe` (check them with `Get-Process`). Never put the browser, the orb (`pythonw`), your own
   agent, antivirus or Windows processes here, and never close things the user didn't name.
4. **Music?** A Spotify playlist: ask them to share its link ("Share → Copy link to playlist") and store it as
   `spotify:playlist:<id>`. Optional `playlist_name` (exact name) helps press its play button.
5. **Should you, the agent, change how you work in this mode?** (e.g. "short technical answers, read my
   project notes first"). If yes, write it in `tell_agent`, and write in `exit_message` what you should do
   when they leave the mode (this makes the panel show an "Exit" button).
6. **Ask before closing apps?** If the mode closes anything, add a short `confirm` question for the panel.

Then show the entry, ask "Save it?", and only with a yes add it to the file (create it if missing, keep the
other modes untouched, valid JSON, UTF-8). Offer to test it right away.

## Format

```json
{
  "modes": [
    {
      "id": "work",
      "title": "Work",
      "description": "Focus playlist, opens the editor, closes games and chat",
      "icon": "briefcase",
      "open": ["Code", "https://calendar.google.com"],
      "close": ["Discord", "steam"],
      "playlist": "spotify:playlist:XXXXXXXXXXXXXXXXXXXXXX",
      "playlist_name": "Focus",
      "tell_agent": "Work mode: short, technical answers.",
      "exit_message": "The user left work mode: go back to normal.",
      "confirm": "This closes Discord and Steam. Continue?"
    }
  ]
}
```

- `id`: short, lowercase, no spaces (`work`, `f1`, `study`). Only `id` and `title` are required.
- `icon` (panel button): one of `briefcase`, `code`, `gamepad`, `car`, `shield`, `book`, `moon`, `music`, `bolt`.
- To change a mode, edit only that entry; to delete one, ask for confirmation first.
- After saving, run `pc.ps1 modes` to check the file reads fine. The panel picks the change up by itself.
