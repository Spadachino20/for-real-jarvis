"""Keeps JARVIS alive: opens him again if he crashes (not if you close him). Three crashes in ten minutes: it gives up."""
import subprocess
import sys
import time
from pathlib import Path

crashes: list[float] = []
while True:
    if subprocess.call([sys.executable, "-m", "jarvis", *sys.argv[1:]]) == 0:
        break
    crashes = [t for t in crashes if time.time() - t < 600] + [time.time()]
    with open(Path(__file__).resolve().parents[1] / "data" / "jarvis.log", "a", encoding="utf-8") as log:
        log.write(time.strftime("%H:%M:%S") + " keep: JARVIS crashed" + (", opening him again\n" if len(crashes) < 3 else " 3 times: giving up\n"))
    if len(crashes) >= 3:
        break
    time.sleep(3)
