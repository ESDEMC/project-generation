import warnings
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as metadata_version
from pathlib import Path
import subprocess
import sys


PACKAGE_NAME = "project-generation"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _get_live_scm_version() -> str:
    print(Path.cwd())

    result = subprocess.run(
        [sys.executable, "-m", "setuptools_scm"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def get_package_version() -> str:
    if (PROJECT_ROOT / ".git").exists():
        try:
            return _get_live_scm_version()
        except Exception as e:
            warnings.warn(f"Failed to get live SCM version: {e}")

    try:
        return metadata_version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "0+unknown"