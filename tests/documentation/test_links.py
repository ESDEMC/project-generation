import re
from pathlib import Path
from urllib.parse import unquote

from tests.support.paths import ROOT

PROJECT_ROOT = ROOT

MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def test_relative_markdown_links_resolve() -> None:
    broken_links: list[str] = []

    for markdown_path in sorted(PROJECT_ROOT.rglob("*.md")):
        text = markdown_path.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK_PATTERN.findall(text):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue

            relative_path = unquote(target.split("#", 1)[0])
            if not relative_path:
                continue

            resolved = (markdown_path.parent / relative_path).resolve()
            if not resolved.exists():
                broken_links.append(f"{markdown_path.relative_to(PROJECT_ROOT)} -> {target}")

    assert not broken_links, "Broken Markdown links:\n" + "\n".join(broken_links)
