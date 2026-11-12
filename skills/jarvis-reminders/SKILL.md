---
name: jarvis-reminders
description: >
  Use when the user asks to be reminded of something or to schedule a recurring notice. Examples:
  "remind me in 10 minutes to drink water", "tell me tomorrow at 8 to call Ana", "every Monday at 9 remind me
  to check my email".
---

# Reminders (For Real J.A.R.V.I.S.)

A reminder must REACH the user. One that only fires inside your own session is never seen: don't do that.

## Where it arrives

The first time, ask where they want reminders (a chat channel you're connected to: WhatsApp, Telegram,
Discord...) and save the answer in your notes about the user, so you never ask again.

## OpenClaw

Create the automation with `automations` → `add`:

```json
{
  "name": "Reminder: <what>",
  "schedule": { "kind": "at", "at": "<ISO time WITH the user's offset, e.g. 2026-11-10T16:30:00-04:00>" },
  "sessionTarget": "isolated",
  "deleteAfterRun": true,
  "payload": { "kind": "agentTurn", "lightContext": true,
               "message": "Reminder for the user: <what>. Write only that notice, in one line." },
  "delivery": { "mode": "announce", "channel": "<their channel>", "to": "<their address on that channel>" }
}
```

- Write the time in the user's local time with its offset; never convert to `Z` by hand.
- Recurring ("every Monday at 9"): `"schedule": { "kind": "cron", "expr": "0 9 * * 1", "tz": "<their IANA zone>" }`
  and no `deleteAfterRun`.
- List / delete: `automations` → `list` / `remove`. The panel's Automations section also shows them.

## Hermes or other agents

Use your own scheduler or cron tool, delivering to the user's channel the same way.

Confirm in one line with the local time: "Done: I'll remind you on WhatsApp at 16:30."
