import ast
import pathlib


from tests.support.paths import ROOT

PACKAGE_ROOT = ROOT / "src" / "project_generation"


def imported_project_generation_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("project_generation"):
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names if alias.name.startswith("project_generation"))
    return modules


def test_neutral_generation_does_not_depend_on_application_or_infrastructure() -> None:
    forbidden_prefixes = (
        "project_generation.application",
        "project_generation.infrastructure",
    )

    violations: list[str] = []
    for path in (PACKAGE_ROOT / "generation").glob("*.py"):
        for module in imported_project_generation_modules(path):
            if module.startswith(forbidden_prefixes):
                violations.append(f"{path.name}: {module}")

    assert not violations, "Neutral generation must not depend on application or infrastructure code: " + ", ".join(violations)
