from importlib.metadata import PackageNotFoundError, version

from setuptools_scm import get_version


PACKAGE_NAME = "project-generation"


def get_package_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return get_version(root="../..", relative_to=__file__)