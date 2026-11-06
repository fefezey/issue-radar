"""Notifications: on a Mac with Issue Radar's own name and radar icon, on Linux through notify-send.

macOS shows a notification with the icon of the app that sent it. A plain
`osascript` notification comes from "Script Editor", so on first use we
build a tiny "Issue Radar.app" (an AppleScript applet with our icon) and
send notifications through it. If that can't be built, we fall back to the
plain way, so you still get notified.
"""

import plistlib
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from issue_radar import db
from issue_radar.i18n import translate
from issue_radar.languages import language_name

ICON = Path(__file__).parent / "icon.icns"
BUNDLE_ID = "io.github.fefezey.issue-radar.notifier"
NOTIFIER_VERSION = 1  # bump to rebuild the app after changing it

_APPLET = """\
on notify(theTitle, theSubtitle, theMessage)
	display notification theMessage with title theTitle subtitle theSubtitle
	quit
end notify
"""

_LSREGISTER = (
    "/System/Library/Frameworks/CoreServices.framework/Frameworks/"
    "LaunchServices.framework/Support/lsregister"
)


def _quote(text: str) -> str:
    """Make text safe to put inside an AppleScript string."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _notifier_app() -> Path | None:
    """~/.issue-radar/Issue Radar.app, built the first time it's needed."""
    app = db.DB_PATH.parent / "Issue Radar.app"
    info = app / "Contents" / "Info.plist"
    try:
        if info.exists() and plistlib.loads(info.read_bytes()).get("IssueRadarNotifier") == NOTIFIER_VERSION:
            return app
        shutil.rmtree(app, ignore_errors=True)
        app.parent.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".applescript", delete=False) as script:
            script.write(_APPLET)
        # -s: stay open long enough to receive the "notify" message.
        subprocess.run(["osacompile", "-s", "-o", str(app), script.name], check=True, capture_output=True)
        Path(script.name).unlink()

        resources = app / "Contents" / "Resources"
        shutil.copy(ICON, resources / "applet.icns")
        (resources / "Assets.car").unlink(missing_ok=True)  # would win over our icon

        plist = plistlib.loads(info.read_bytes())
        plist.pop("CFBundleIconName", None)
        plist.update(
            CFBundleIdentifier=BUNDLE_ID,
            CFBundleName="Issue Radar",
            CFBundleIconFile="applet",
            LSUIElement=True,  # no Dock icon
            IssueRadarNotifier=NOTIFIER_VERSION,
        )
        info.write_bytes(plistlib.dumps(plist))

        # Changing the app breaks its signature; sign it again, for this Mac only.
        subprocess.run(["codesign", "--force", "--deep", "-s", "-", str(app)], check=True, capture_output=True)
        subprocess.run([_LSREGISTER, "-f", str(app)], capture_output=True)
        return app
    except (OSError, subprocess.CalledProcessError, plistlib.InvalidFileException) as error:
        print(f"Couldn't build the notifier app, using plain notifications: {error}", flush=True)
        shutil.rmtree(app, ignore_errors=True)
        return None


def notify(title: str, subtitle: str, message: str) -> None:
    """Show a notification on macOS, or on Linux with notify-send.
    Does nothing on other systems."""
    if sys.platform.startswith("linux"):
        if shutil.which("notify-send"):
            subprocess.run(["notify-send", "--app-name=Issue Radar", title, f"{subtitle}\n{message}"], timeout=30)
        return
    if sys.platform != "darwin":
        return
    app = _notifier_app()
    if app:
        script = f"tell application {_quote(str(app))} to notify({_quote(title)}, {_quote(subtitle)}, {_quote(message)})"
        if subprocess.run(["osascript", "-e", script], capture_output=True, timeout=30).returncode == 0:
            return
    script = f"display notification {_quote(message)} with title {_quote(title)} subtitle {_quote(subtitle)}"
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=30)


def notify_new_issues(issues: list[dict], lang: str) -> None:
    if len(issues) == 1:
        issue = issues[0]
        notify("Issue Radar", issue["repo"], issue["title"])
        return

    by_language = Counter(language_name(issue["language"]) for issue in issues)
    summary = ", ".join(f"{count} {name}" for name, count in by_language.most_common())
    notify("Issue Radar", translate(lang, "notify.many", len(issues)), summary)
