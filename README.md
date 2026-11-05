<p align="center">
  <img src="assets/logo.svg" width="96" height="96" alt="Issue Radar logo">
</p>

<h1 align="center">Issue Radar</h1>

<p align="center"><strong>Find your next open-source contribution before someone else does.</strong></p>

Beginner-friendly GitHub issues get picked up fast — often within hours. Issue Radar watches GitHub for you, finds new `good first issue`s that nobody has claimed yet, and lets you know right away.

It runs on your own computer: no account, no server, your choices stay on your disk.

## Features

- 🔍 **Finds new `good first issue`s** in the languages you choose, newest first.
- ⭐ **Skips tiny projects** — only repositories with at least 100 stars.
- ⚡ **Filters out claimed issues** — assigned ones, ones with a linked pull request, and ones where someone commented "I'd like to work on this".
- 🔔 **Mac notifications** — scans every 10 minutes and notifies you at most once an hour.
- 🖥️ **A simple web page** to go through issues: *Interested*, *Skip* or *Hide project*, with undo.
- 🌍 **English and Turkish interface** — picks your browser's language, switch any time. Notifications follow the same language.
- 🌗 Light and dark theme, following your system.

### Planned

- [ ] AI summaries in your language, with difficulty and time estimates
- [ ] A ready-to-post "I'd like to work on this" comment draft
- [ ] More interface languages — [add yours](#add-a-language)
- [ ] Settings page (languages, minimum stars, scan interval)
- [ ] Notifications on Linux and Windows
- [ ] Telegram and Discord notifications

## How it works

1. **Scan** — every 10 minutes, search GitHub for new open issues labeled `good first issue`.
2. **Filter** — drop issues that are assigned, have a linked PR, were claimed in the comments, or come from repositories with fewer than 100 stars.
3. **Notify** — save new issues locally and show a Mac notification.
4. **Decide** — open the web page and pick what you want to work on.

## Getting started

You need [uv](https://docs.astral.sh/uv/) (it installs the right Python for you):

```bash
brew install uv
```

Then:

```bash
git clone https://github.com/fefezey/issue-radar.git
cd issue-radar
uv run issue-radar
```

Open **http://localhost:8000**. The first scan takes 30–40 seconds; the page refreshes by itself.

### GitHub access

Without signing in, GitHub allows only 60 requests an hour, which is not enough. Issue Radar uses, in this order:

1. the `GITHUB_TOKEN` environment variable, if set, or
2. your [GitHub CLI](https://cli.github.com/) login (`gh auth login`).

The token only needs to read public data.

### Notifications

On macOS, notifications are shown through AppleScript, so they appear as coming from **Script Editor**. If you don't see them, allow notifications for Script Editor in **System Settings → Notifications**.

## Configuration

There is no settings page yet. For now, change these values in the code:

| What | Where | Default |
| --- | --- | --- |
| Languages to search | `LANGUAGES` in `src/issue_radar/languages.py` | `python`, `javascript` |
| Minimum stars | `min_stars` in `src/issue_radar/github.py` | `100` |
| Scan interval | `SCAN_INTERVAL` in `src/issue_radar/scanner.py` | 10 minutes |
| Notification interval | `NOTIFY_INTERVAL` in `src/issue_radar/scanner.py` | 1 hour |

Your issues and choices are stored in `~/.issue-radar/issues.db`. Delete this file to start over.

## Project structure

```
src/issue_radar/
├── __init__.py      starts the scanner and the web page
├── github.py        talks to GitHub: search, star counts, claimed issues
├── scanner.py       scans on a schedule and decides when to notify
├── notify.py        Mac notifications
├── db.py            the local SQLite database
├── web.py           the web page's routes
├── languages.py     which languages to search
├── i18n.py          translations
├── locales/         one JSON file per interface language
└── templates/
    └── index.html   the web page
```

## Contributing

Contributions are welcome — this is a tool for first-time contributors, after all. Good places to start:

- **Add a language** — see below. No coding needed.
- **Improve claim detection.** `CLAIM_PHRASES` in `github.py` lists the phrases people use to claim an issue. Add the ones you see in the wild.
- **Linux or Windows notifications.** `notify.py` only supports macOS.
- **Anything from the [Planned](#planned) list.**

Open an issue first if you plan a bigger change.

### Add a language

1. Copy `src/issue_radar/locales/en.json` to a file named after your language code, for example `de.json`.
2. Translate the values on the right. Keep the keys on the left and anything in `{curly braces}` as they are.
3. For words that change with a number, use `.one` and `.other` keys, like `"issue.stars.one": "{stars} star"` and `"issue.stars.other": "{stars} stars"`. If your language doesn't change, `.other` alone is enough.
4. Run `uv run issue-radar` and pick your language in the top-right corner.

Any key you leave out falls back to English.

## License

[MIT](LICENSE)

---

<p align="center"><em>Contribute more. Search less.</em></p>
