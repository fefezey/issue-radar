"""The issue guide: how to set up and test a project, and which files to
look at first. Plain rules over the project's own files, no AI: these are
facts you can check, and a small model would guess file names.
"""

import re

# Commands worth showing, by the program they start with.
_COMMANDS = {
    "git", "pip", "pip3", "python", "python3", "uv", "poetry", "pipenv", "pdm", "hatch",
    "pytest", "tox", "nox", "conda", "mamba", "make", "npm", "npx", "yarn", "pnpm", "bun",
    "deno", "cargo", "go", "mvn", "gradle", "./gradlew", "bundle", "rake", "gem", "composer",
    "dotnet", "cmake", "meson", "ninja", "just", "docker", "pre-commit",
}
_TEST_WORDS = re.compile(r"\b(?:test|tests|pytest|tox|nox|check|lint|vitest|jest|spec)\b", re.IGNORECASE)
_SETUP_WORDS = re.compile(
    r"\b(?:install|clone|setup|sync|venv|virtualenv|init|bootstrap|develop|build|create|env)\b", re.IGNORECASE
)
_CODE_BLOCK = re.compile(r"```[ \t]*([\w+-]*)[^\n]*\n(.*?)```", re.DOTALL)
_SHELL_BLOCKS = {"", "bash", "sh", "shell", "console", "zsh", "shell-session", "shellsession", "terminal", "cmd"}
MAX_COMMANDS = 6


# Signs that a setup command is for working on the project, not just using it.
_DEVELOPER_SETUP = re.compile(r"git clone|\s-e\s|--editable|\[dev|requirements|\bsync\b|venv|\bdevelop\b|npm ci|install$")


def find_commands(*texts: str) -> dict[str, list[str]]:
    """Setup and test commands from shell code blocks in Markdown texts.

    Pass the contributing guide before the README: its commands come first.
    Only setup steps for working on the project are kept ("git clone",
    "pip install -e .", "npm install"); a README's usage examples ("conda
    install anaconda-client") would send a newcomer the wrong way.
    """
    found: dict[str, list[str]] = {"setup": [], "test": []}
    for text in texts:
        for language, block in _CODE_BLOCK.findall(text):
            if language.lower() not in _SHELL_BLOCKS:
                continue
            for line in block.splitlines():
                line = re.sub(r"^\s*(?:[$%>]|PS>)\s+", "", line).strip()
                if not line or line.startswith("#") or len(line) > 120 or re.search(r"<[^>]+>", line):
                    continue
                if line.split()[0] not in _COMMANDS:
                    continue
                if _TEST_WORDS.search(line):
                    kind = "test"
                elif _SETUP_WORDS.search(line) and _DEVELOPER_SETUP.search(line):
                    kind = "setup"
                else:
                    continue
                if line not in found[kind]:
                    found[kind].append(line)
    return {kind: lines[:MAX_COMMANDS] for kind, lines in found.items()}


# --- Files to look at -------------------------------------------------------

_FILE_LIKE = re.compile(
    r"[\w./-]+\.(?:py|pyi|js|mjs|cjs|ts|tsx|jsx|vue|svelte|go|rs|java|kt|rb|php|swift|cs|cpp|cc|c|h|hpp|"
    r"md|rst|yml|yaml|toml|json|css|scss|html|sh)\b"
)
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_SKIP_PATHS = re.compile(r"(?:^|/)(?:node_modules|dist|build|vendor|third_party|\.git)/|\.min\.(?:js|css)$")
# Words that look like identifiers but say nothing about where the code is.
_COMMON = {
    "true", "false", "none", "null", "self", "this", "that", "with", "from", "import", "return",
    "class", "function", "def", "const", "async", "await", "error", "issue", "test", "tests",
    "file", "files", "data", "value", "string", "number", "list", "dict", "type", "object",
    "index", "main", "init", "config", "readme", "github", "https", "http", "should", "would",
}
MAX_FILES = 6
# Code names point to code; docs only count when the issue names the file itself.
_DOC_EXTENSIONS = (".md", ".rst", ".txt", ".adoc")


def _normalize(name: str) -> str:
    """'ReferenceWindowModel', 'reference_window_model', 'reference-window-model' -> 'referencewindowmodel'"""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def name_candidates(*texts: str) -> tuple[set[str], set[str]]:
    """File paths and code names mentioned in the issue: (paths, identifiers).
    Code is usually written in `backticks`; file names are also found in plain text."""
    paths: set[str] = set()
    identifiers: set[str] = set()
    for text in texts:
        paths.update(match.lstrip("./") for match in _FILE_LIKE.findall(text))
        for span in re.findall(r"`([^`\n]+)`", text) + re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+\b", text):
            if "/" in span or _FILE_LIKE.fullmatch(span.strip()):
                continue  # a path, already taken above; its folder names aren't code names
            for part in re.split(r"[.:()\s,]+", span):
                if _IDENTIFIER.fullmatch(part) and part.lower() not in _COMMON:
                    identifiers.add(part)
    return paths, identifiers


def find_files(paths_in_repo: list[str], mentioned_paths: set[str], identifiers: set[str]) -> list[str]:
    """Files in the project that match names from the issue, best matches first."""
    wanted_ids = {_normalize(name) for name in identifiers if len(_normalize(name)) >= 4}
    scored = []
    for path in paths_in_repo:
        if _SKIP_PATHS.search(path):
            continue
        basename = path.rsplit("/", 1)[-1]
        stem = basename.split(".", 1)[0]
        # A path with folders ("tests/models/test_x.py") must match exactly;
        # a bare file name ("GameCard.vue") may be in any folder.
        if any(path.endswith(m) if "/" in m else basename == m for m in mentioned_paths):
            score = 3  # the issue names this file
        elif _normalize(stem) in wanted_ids and not basename.endswith(_DOC_EXTENSIONS):
            score = 2  # a class or module named in the issue has its own file
        else:
            continue
        scored.append((-score, len(path), path))
    return [path for _, _, path in sorted(scored)[:MAX_FILES]]
