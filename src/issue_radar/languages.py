# Languages you can pick on the settings page, as GitHub's search understands them.
SUPPORTED_LANGUAGES = [
    "python",
    "javascript",
    "typescript",
    "go",
    "rust",
    "java",
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


def language_name(name: str) -> str:
    """'javascript' -> 'JavaScript', 'python' -> 'Python'"""
    return _DISPLAY_NAMES.get(name, name.capitalize())
