import socket
import sys
import threading
import webbrowser

PORT = 8000
PAGE = f"http://localhost:{PORT}"

USAGE = """\
usage: issue-radar [install | uninstall]

  (nothing)   start Issue Radar and its page at http://localhost:8000
  install     start it by itself whenever you log in to your Mac
  uninstall   stop doing that
"""


def _already_running() -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", PORT)) == 0


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else None
    if command in ("install", "uninstall"):
        from issue_radar import service

        sys.exit(service.install() if command == "install" else service.uninstall())
    if command is not None:
        print(USAGE)
        sys.exit(0 if command in ("-h", "--help", "help") else 2)

    if _already_running():
        # Started at login already: just show the page instead of a second copy.
        print(f"Issue Radar is already running: {PAGE}")
        webbrowser.open(PAGE)
        return

    from issue_radar.ai import summarize_forever
    from issue_radar.scanner import scan_forever
    from issue_radar.web import app

    # Scan and summarize in the background so the page opens right away.
    threading.Thread(target=scan_forever, daemon=True).start()
    threading.Thread(target=summarize_forever, daemon=True).start()

    print(f"Page: {PAGE}")
    app.run(port=PORT)
