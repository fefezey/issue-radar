<p align="center">
  <img src="assets/logo.svg" width="96" height="96" alt="Issue Radar logo">
</p>

<h1 align="center">Issue Radar</h1>

<p align="center"><strong>Find your next open-source contribution before someone else does.</strong></p>

<p align="center">
  <a href="https://github.com/fefezey/issue-radar/actions/workflows/tests.yml"><img src="https://github.com/fefezey/issue-radar/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  · <a href="README.tr.md">Türkçe</a>
</p>

Issue Radar helps developers find beginner-friendly issues on GitHub.

It scans GitHub for new issues, filters out tasks that are already claimed, and notifies you when it finds something worth looking at. You can choose which programming languages to follow, explore issues by project, and keep track of your contributions. It also offers optional AI summaries through Ollama, so you can understand an issue before getting started.

Everything runs locally on your Mac. Your data and preferences stay on your computer.

## Features

- **Finds new beginner issues** in the languages you choose, newest first — labeled `good first issue`, `good-first-issue`, `first-timers-only`, `beginner` or `beginner-friendly`.
-  **Is this project friendly to newcomers?** — each project shows what it is in one line, and how many pull requests from outside its team it merged in the last three months. A project that merges none is marked.
-  **Grouped by project** — one busy project can't fill the whole list; its other issues fold under "N more issues from this project".
-  **Skips tiny projects** — only repositories with at least 100 stars (you can change this).
-  **New projects first** — issues from projects you haven't sent a pull request to yet are listed first. Projects you already know are marked.
-  **Filters out claimed issues** — assigned ones, ones with a linked pull request, and ones where someone commented "I'd like to work on this". Saved issues are checked again on every scan, so ones that were closed or taken later drop out too.
-  **AI summaries, free and private** — a small model on your own computer (via [Ollama](https://ollama.com)) explains each issue in two sentences in your language. Optional; without it you just don't see summaries.
-  **Docs, tests and translations marked** — the gentlest first contributions, found from the issue's title and GitHub labels, with a filter to see only those.
-  **Mac notifications** — scans every 10 minutes and notifies you at most once an hour.
-  **A simple web page** to go through issues: *Interested*, *Skip* or *Hide project*, with undo, without losing your place.
-  **Claim it** — *Interested* opens a ready-to-post comment ("I'd like to work on this… could you assign it to me?") with a line for your own plan, and a button that copies it and opens the issue. If the project's contributing guide says not to ask first, you're told so.
-  **Follow your progress** — for issues you're interested in, Issue Radar reads GitHub on every scan and shows where you are: *Commented → Assigned → PR opened → Merged*, with the next step (including the `Fixes #123` line that links your pull request).
-  **Where to start** — a guide for each issue you're interested in: the files named in the issue that really exist in the project (with links), the project's setup and test commands from its contributing guide and README, and a plain explanation written by the local AI. A Mac notification tells you when you're assigned, when your pull request is merged, or when someone else takes an issue you wanted.
-  **Settings page** — pick the languages to search and the minimum stars.
-  **English and Turkish interface** — picks your browser's language, switch any time. Notifications follow the same language.
-  Light and dark theme, following your system.

### Planned

- [ ] How quickly maintainers answer newcomers
- [ ] More interface languages — [add yours](#add-a-language)
- [ ] Notifications on Linux and Windows
- [ ] Telegram and Discord notifications

## How it works

1. **Scan** — every 10 minutes, search GitHub for new open issues with a beginner label.
2. **Filter** — drop issues that are assigned, have a linked PR, were claimed in the comments, or come from repositories with too few stars. Star counts are remembered for a day, so GitHub isn't asked again on every scan.
3. **Re-check** — look again at up to 20 saved issues in a single request, and drop the ones that have been closed or taken since.
4. **Learn about projects** — for a few projects per scan, at most once a day each: what the project is, and how many outsiders' pull requests it merged lately (bots don't count).
5. **Summarize** — if Ollama is running, write a short summary for each new issue, one at a time in the background. Issues with a very short description get none: the title already says it.
6. **Notify** — save new issues locally and show a Mac notification.
7. **Decide** — open the web page and pick what you want to work on.

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

Open **http://localhost:8000**. The first scan can take about a minute; the page refreshes by itself.

### AI summaries (optional)

Summaries are made by [Ollama](https://ollama.com) with the `gemma3:4b` model (about 3 GB). It's free, and the issue text never leaves your computer:

```bash
brew install ollama
brew services start ollama
ollama pull gemma3:4b
```

Issue Radar picks it up on its own; **Settings** shows whether summaries are on. The model runs fine on a Mac with 8 GB of memory, but close heavy apps (like the iOS Simulator) if summaries are slow. To use another model, set `OLLAMA_MODEL`, for example `OLLAMA_MODEL=qwen2.5:3b uv run issue-radar`.

Summaries are written by a small model and can be wrong — the original issue is always one click away.

### GitHub access

Without signing in, GitHub allows only 60 requests an hour, which is not enough. Issue Radar uses, in this order:

1. the `GITHUB_TOKEN` environment variable, if set, or
2. your [GitHub CLI](https://cli.github.com/) login (`gh auth login`).

The token only needs to read public data.

### Notifications

On macOS, notifications are shown through AppleScript, so they appear as coming from **Script Editor**. If you don't see them, allow notifications for Script Editor in **System Settings → Notifications**.

## Configuration

Open **Settings** on the page to choose:

- **Languages to search** — Python, JavaScript, TypeScript, Go, Rust, Java, C#, C++, Ruby, PHP, Kotlin, Swift. Default: Python and JavaScript.
- **Minimum stars** — any, 50, 100, 500 or 1000. Default: 100.

Changes apply right away, and a new scan starts immediately.

These are still set in the code, in `src/issue_radar/scanner.py`:

| What | Name | Default |
| --- | --- | --- |
| Scan interval | `SCAN_INTERVAL` | 10 minutes |
| Retry after a failed scan | `RETRY_INTERVAL` | 5 minutes |
| Notification interval | `NOTIFY_INTERVAL` | 1 hour |

Your issues and choices are stored in `~/.issue-radar/issues.db`. Delete this file to start over.

## Project structure

```
src/issue_radar/
├── __init__.py      starts the scanner and the web page
├── github.py        talks to GitHub: search, star counts, claimed issues, your pull requests
├── scanner.py       scans on a schedule and decides when to notify
├── ai.py            AI summaries through Ollama
├── kinds.py         spots docs, test and translation issues
├── claiming.py      the comment draft, and reading contributing guides
├── guide.py         the issue guide: setup and test commands, files to look at
├── notify.py        Mac notifications
├── db.py            the local SQLite database
├── web.py           the web page's routes
├── languages.py     languages you can search, and their display names
├── settings.py      settings from the settings page
├── i18n.py          translations
├── locales/         one JSON file per interface language
└── templates/
    └── index.html   the web page
```

## Contributing

Contributions are welcome — this is a tool for first-time contributors, after all. Good places to start:

- **Add a language** — see below. No coding needed.
- **Improve claim detection.** `CLAIM_PHRASES` in `github.py` lists the phrases people use to claim an issue. Add the ones you see in the wild.
- **Spot more kinds of easy work.** `kinds.py` finds docs, test and translation issues from titles and labels. Missed one, or found a wrong match? Adjust the rules.
- **Linux or Windows notifications.** `notify.py` only supports macOS.
- **Anything from the [Planned](#planned) list.**

Open an issue first if you plan a bigger change.

### Run the tests

```bash
uv run pytest
```

The tests need no network, no GitHub token and no Ollama: GitHub's and the model's answers are made up in the tests, and every test gets its own empty database. They run on every push and pull request.

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
