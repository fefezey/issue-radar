import threading


def main() -> None:
    from issue_radar.ai import summarize_forever
    from issue_radar.scanner import scan_forever
    from issue_radar.web import app

    # Scan and summarize in the background so the page opens right away.
    threading.Thread(target=scan_forever, daemon=True).start()
    threading.Thread(target=summarize_forever, daemon=True).start()

    print("Sayfa: http://localhost:8000")
    app.run(port=8000)
