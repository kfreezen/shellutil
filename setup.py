import os

from setuptools import setup, find_namespace_packages


with open(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "README.md")
) as file:
    long_description = file.read()

setup(
    name="shellutil",
    url="https://github.com/kfreezen/shellutil",
    long_description=long_description,
    long_description_content_type="text/markdown",
    description="Utilities to handle shell access to both local and remote shells.",
    packages=find_namespace_packages(include=["shellutil"]),
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    install_requires=["paramiko", "ptyprocess"],
    test_suite="tests",
)
