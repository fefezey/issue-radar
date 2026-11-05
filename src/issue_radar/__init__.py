import threading


def main() -> None:
    from issue_radar.scanner import scan_forever
    from issue_radar.web import app

    # Scan in the background so the page opens right away.
    threading.Thread(target=scan_forever, daemon=True).start()

    print("Sayfa: http://localhost:8000")
    app.run(port=8000)
