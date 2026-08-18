import json
import re
from pathlib import Path


JSON_BLOCK_PATTERN = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_documentation_json_snippets_are_valid_json() -> None:
    markdown_files = [PROJECT_ROOT / "README.md", *sorted((PROJECT_ROOT / "docs").rglob("*.md"))]
    markdown_files.extend(sorted((PROJECT_ROOT / "examples").rglob("README.md")))

    failures: list[str] = []
    for markdown_file in markdown_files:
        text = markdown_file.read_text(encoding="utf-8")
        for index, match in enumerate(JSON_BLOCK_PATTERN.finditer(text), start=1):
            try:
                json.loads(match.group(1))
            except json.JSONDecodeError as error:
                failures.append(f"{markdown_file.relative_to(PROJECT_ROOT)} JSON block {index}: {error}")

    assert not failures, "\n".join(failures)
