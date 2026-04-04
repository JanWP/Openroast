from pathlib import Path
import os

from setuptools import find_packages, setup

version = {}
with open("./openroast/version.py", encoding="utf-8") as fp:
    exec(fp.read(), version)

here = Path(__file__).resolve().parent


def package_files(directory):
    paths = []
    for (base, _directories, filenames) in os.walk(directory):
        for filename in filenames:
            paths.append(os.path.join("..", base, filename))
    return paths


setup(
    name="openroast",
    version=version["__version__"],
    description="An open source, cross-platform application for home coffee roasting",
    long_description=(here / "README.rst").read_text(encoding="utf-8"),
    long_description_content_type="text/x-rst",
    url="https://github.com/Roastero/Openroast",
    author="Roastero",
    author_email="admin@roastero.com",
    license="GPLv3",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "Topic :: System :: Hardware :: Hardware Drivers",
        "Topic :: Scientific/Engineering",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.13",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Operating System :: Microsoft :: Windows",
    ],
    python_requires=">=3.13",
    keywords="sr700 coffee roasting",
    packages=find_packages(exclude=["contrib", "docs", "tests"]),
    # Keep hard requirements minimal; on Raspberry Pi use distro GUI packages.
    install_requires=[
        "freshroastsr700>=0.2.3",
    ],
    extras_require={
        "gui": [
            "PyQt5>=5.15",
            "matplotlib>=3.8",
        ],
    },
    package_data={
        "": package_files("openroast/static"),
    },
    entry_points={
        "console_scripts": [
            "openroast=openroast.openroastapp:main",
        ],
    },
)
