# Languages you can pick on the settings page, as GitHub's search understands them.
SUPPORTED_LANGUAGES = [
    "python",
    "javascript",
    "typescript",
    "go",
    "rust",
    "java",
    "c",
    "csharp",
    "cpp",
    "ruby",
    "php",
    "kotlin",
    "swift",
]

_DISPLAY_NAMES = {
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "csharp": "C#",
    "cpp": "C++",
    "php": "PHP",
}

# GitHub's names for the languages above ("C#", "C++") -> our codes.
_FROM_GITHUB = {name.lower(): code for code, name in _DISPLAY_NAMES.items()}


def language_name(name: str) -> str:
    """'javascript' -> 'JavaScript', 'python' -> 'Python'"""
    return _DISPLAY_NAMES.get(name, name.capitalize())


def from_github(name: str | None) -> str | None:
    """'C++' -> 'cpp', 'Python' -> 'python'; None for languages we don't search (HTML, Shell...)."""
    if not name:
        return None
    code = _FROM_GITHUB.get(name.lower(), name.lower())
    return code if code in SUPPORTED_LANGUAGES else None
