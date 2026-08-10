import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INLINE_EXAMPLE_PATTERN = re.compile(r"\b(?:for example|such as|e\.g\.)\b[^\n]*`[^`]+`", re.IGNORECASE)


def test_examples_are_not_embedded_inline_in_prose() -> None:
    paths = [*PROJECT_ROOT.glob("*.md"), *PROJECT_ROOT.glob("docs/**/*.md"), *PROJECT_ROOT.glob("examples/**/*.md")]
    paths.extend(PROJECT_ROOT.glob("examples/**/*.py"))

    violations = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if INLINE_EXAMPLE_PATTERN.search(line):
                violations.append(f"{path.relative_to(PROJECT_ROOT)}:{line_number}: {line.strip()}")

    assert not violations, "Inline examples should be moved into a block or table:\n" + "\n".join(violations)
