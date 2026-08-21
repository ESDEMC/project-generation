import warnings
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as metadata_version
from pathlib import Path


PACKAGE_NAME = "project-generation"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_package_version() -> str:
    if (PROJECT_ROOT / ".git").exists():
        try:
            from setuptools_scm import get_version

            return get_version(root=PROJECT_ROOT)
        except Exception:
            warnings.warn("Failed to get version from setuptools_scm")

    try:
        return metadata_version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "0+unknown"
