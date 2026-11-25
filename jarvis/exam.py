"""The exam: every self-check at once, plus your own phrases (data/exam.json). No tokens.  python -m jarvis.exam

data/exam.json: [{"heard": "Abre Al Spotify", "talking": false, "verdict": "yes"},   who he thinks you're talking to (addressed.py)
                 {"command": "shutdown /s", "needs": "power"}]                        what the brake must stop ("" = nothing)
"""
import json
import subprocess
import sys

from . import addressed, guard, settings

failed = []
for m, flag in (("guard", "--check"), ("reminders", "--check"), ("addressed", ""), ("stt", ""), ("house", ""), ("settings", ""), ("study", "")):
    if not (settings.DATA.parent / "jarvis" / f"{m}.py").exists():
        continue  # study.py is optional
    r = subprocess.run([sys.executable, "-m", f"jarvis.{m}", *([flag] if flag else [])], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    print(("ok   " if not r.returncode else "FAIL ") + m)
    if r.returncode:
        failed.append(m)
        print("     " + (r.stderr.strip().splitlines() or ["?"])[-1])
mine = settings.DATA / "exam.json"
cases = json.loads(mine.read_text(encoding="utf-8")) if mine.exists() else []
for c in cases:
    if "heard" in c:
        got, want = addressed.decide(c["heard"], c.get("talking", False)), c["verdict"]
    else:
        got, want = guard.kinds("PowerShell", c), c["needs"]
        got = want if want in got else " ".join(got)
    if got != want:
        failed.append(str(c))
        print(f"FAIL {c.get('heard') or c.get('command')}: {got!r}, expected {want!r}")
print(f"{len(cases)} of your phrases. " + (f"{len(failed)} FAILED" if failed else "All good."))
sys.exit(bool(failed))
