#!/usr/bin/env python3
"""Minimal Python 3.13 smoke checks for Openroast."""

import importlib
from openroast import utils


MODULES = [
    "openroast",
    "openroast.controllers.recipe",
    "openroast.views.customqtwidgets",
    "openroast.views.mainwindow",
]


def main():
    for module_name in MODULES:
        importlib.import_module(module_name)

    style_path = utils.get_resource_filename("static/mainStyle.css")
    if not style_path:
        raise RuntimeError("Failed to resolve static/mainStyle.css")

    print("Smoke test passed: modules import and resources resolve")


if __name__ == "__main__":
    main()

