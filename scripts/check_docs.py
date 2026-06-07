"""Validate repository Markdown links and fenced code blocks."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_ROOTS = (ROOT / "README.md", ROOT / "docs", ROOT / "src")
LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
FENCE_PATTERN = re.compile(r"^```", re.MULTILINE)


def _markdown_files() -> list[Path]:
    """Return all project Markdown files covered by documentation checks."""
    files: list[Path] = []
    for root in MARKDOWN_ROOTS:
        if root.is_file():
            files.append(root)
        else:
            files.extend(root.rglob("*.md"))
    return sorted(files)


def _relative_link_target(raw_target: str) -> str | None:
    """Return the filesystem portion of a relative Markdown link."""
    target = raw_target.strip().split("#", maxsplit=1)[0]
    if not target or target.startswith(("http://", "https://", "mailto:")):
        return None
    return unquote(target)


def main() -> int:
    """Validate documentation files and return a process exit code."""
    errors: list[str] = []

    for path in _markdown_files():
        text = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(ROOT)

        fence_count = len(FENCE_PATTERN.findall(text))
        if fence_count % 2 != 0:
            errors.append(f"{relative_path}: unbalanced fenced code blocks")

        for match in LINK_PATTERN.finditer(text):
            target = _relative_link_target(match.group(1))
            if target is None:
                continue
            resolved = path.parent / target
            if not resolved.exists():
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{relative_path}:{line}: missing link target {target}")

    if errors:
        print("\n".join(errors))
        return 1

    print(f"Documentation checks passed ({len(_markdown_files())} Markdown files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
