"""Start Issue Radar by itself when you log in to your Mac, and keep it running.

Uses a LaunchAgent, macOS's own way to run a program in the background for
one user. `issue-radar install` turns it on, `issue-radar uninstall` off.
"""

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from issue_radar import db

LABEL = "io.github.fefezey.issue-radar"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG = db.DB_PATH.parent / "issue-radar.log"


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def install() -> int:
    if sys.platform != "darwin":
        print("Starting at login is only supported on macOS for now.")
        return 1
    LOG.parent.mkdir(exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    agent = {
        "Label": LABEL,
        # This project's own Python, so its packages are there.
        "ProgramArguments": [sys.executable, "-m", "issue_radar"],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},  # start again if it crashes
        "WorkingDirectory": str(Path.home()),
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
        # Programs started by macOS get a bare PATH; keep yours so `gh` (your
        # GitHub login) and `ollama` are found.
        "EnvironmentVariables": {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONUNBUFFERED": "1"},
    }
    PLIST.write_bytes(plistlib.dumps(agent))

    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", f"{domain}/{LABEL}")  # if an older one is loaded
    result = _launchctl("bootstrap", domain, str(PLIST))
    if result.returncode != 0:
        print(f"Couldn't start it: {result.stderr.strip()}")
        return 1
    print("Issue Radar now starts by itself when you log in, and is running.")
    print("Page: http://localhost:8000")
    print(f"Log:  {LOG}")
    print("To turn this off: uv run issue-radar uninstall")
    return 0


def uninstall() -> int:
    _launchctl("bootout", f"gui/{os.getuid()}/{LABEL}")
    if PLIST.exists():
        PLIST.unlink()
        print("Issue Radar no longer starts by itself, and has been stopped.")
    else:
        print("Issue Radar wasn't set to start by itself.")
    return 0
