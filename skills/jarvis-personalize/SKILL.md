---
name: jarvis-personalize
description: >
  Use when the user wants JARVIS to get to know them or to change JARVIS's personality: "personalize JARVIS",
  "get to know me", "ask me questions about me", "change your personality", "talk to me like the movie
  JARVIS", "put your name on the orb", "make the orb orange", "go back to JARVIS". Also when the panel says the user pressed "Personalize JARVIS".
---

# Get to know the user (For Real J.A.R.V.I.S.)

## The golden rule: your personality stays yours

You may already have a personality, a name, memories and notes about the user. **Keep all of it.**
This interview only ADDS what you learn about the user. You change your personality **only** if the user
explicitly asks for it in step 1, and you show the change before saving it.

## Step 1 - ask first, then wait

"Before we start: do you want me to keep my current personality, or should I take on JARVIS's personality
(the butler from the movies: calm, dry British wit, calls you 'sir')? Keeping mine is the default."

- Keep (or no clear answer) → you will NOT touch your persona file. Go to step 1b.
- JARVIS / a new style → note it; you'll write it at the end (step 4).

## Step 1b - how the orb and the panel look (your identity)

The orb shows a letter and a color, and the panel shows a name. By default they say J.A.R.V.I.S. in cyan.
If you keep your own personality and you have your own name (F.R.I.D.A.Y., EDITH, ULTRON...), offer to
show **your** name instead: "Want the orb to say <your name>, with an '<letter>' and my color?"

With a yes, write `{{JARVIS_HOME}}\data\identity.json` (only this file, UTF-8):

```json
{ "name": "F.R.I.D.A.Y.", "letter": "F", "color": "#ff8a3d" }
```

- `name`: how you write your name. `letter`: the one in the orb (default: the first letter).
- `color`: a `#rrggbb` that fits you; suggest one and let the user pick. Ideas: JARVIS cyan `#38e1ff`,
  FRIDAY orange `#ff8a3d`, ULTRON red `#ff3b3b`, EDITH violet `#a78bfa`, KAREN green `#3ddc97`, gold `#ffc857`.
- Optional `"wake": ["fri"]`: extra words that call you. Your name and "Jarvis" always work ("Hey Friday").
- The orb changes within 3 seconds; the panel on its next reload (F5). Nothing to restart.
- Desktop icon too (optional): run `{{JARVIS_HOME}}\.venv\Scripts\python.exe -m jarvis.icon` (writes
  `data\orb.ico`) and set it as the icon of the desktop shortcut that points to `Restart JARVIS.cmd`.
- To change it later, edit the file. **To go back to J.A.R.V.I.S., delete `data\identity.json`.**

## Step 2 - the interview (one question at a time, short, wait for each answer)

Skip anything you already know (check your memory and notes first). Let them skip any question.

1. What should I call you? (name, nickname, "sir"...)
2. Where are you, and what language(s) do you speak? (time zone, how to talk to you)
3. What do you do? (work, study, projects)
4. Which apps and tools do you use every day?
5. What should I help you with most? (work, gaming, reminders, music, PC...)
6. How do you like answers: short or detailed? Serious or with humor?
7. Anything I should never do, or always do?
8. Anything else you want me to remember?

## Step 3 - save what you learned (add, never replace)

- OpenClaw: add a section to `USER.md` in your workspace. Hermes or others: your user profile / memory.
- Title it `## From the For Real J.A.R.V.I.S. interview (<date>)`, short bullets, in the user's language.
- If something contradicts an older note, ask which one is right.
- Show what you'll add, ask "Save it?", and only save with a yes.

## Step 4 - only if they asked for a new personality in step 1

- Show the exact text you'd add or change in your persona file (OpenClaw: `SOUL.md`; Hermes: `SOUL.md`
  in its home; others: your system prompt or persona notes) and ask for a yes before saving.
- Prefer adding a "Voice and style" section over rewriting the file. Never delete their old notes without asking.

## A better voice

If the user asks for a better or more natural voice (or dislikes the default one), explain the free ElevenLabs
option in 3 short steps: free account at elevenlabs.io → Developers → API Keys → Create (Text to Speech +
Voices read) → right-click the orb → "ElevenLabs voice…" → paste. Never ask them to paste the key to you in the
chat: the orb's dialog keeps it on their PC.

## Finish

One line: what you'll remember, and that they can run this again any time ("personalize JARVIS").
