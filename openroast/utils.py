import os
import sys
from importlib import resources
from pathlib import Path


def get_resource_filename(resname):
    """Get the absolute path to a packaged resource."""
    # Source installs and editable installs typically resolve here.
    package_root = resources.files("openroast")
    candidate = package_root.joinpath(*resname.split("/"))
    if candidate.exists():
        return os.fspath(candidate)

    # Frozen app fallback.
    module_dir_candidate = Path(__file__).resolve().parent / resname
    if module_dir_candidate.exists():
        return str(module_dir_candidate)

    if hasattr(sys, "frozen"):
        exe_dir_candidate = Path(sys.executable).resolve().parent / resname
        if exe_dir_candidate.exists():
            return str(exe_dir_candidate)

    raise FileNotFoundError(
        "get_resource_filename - Could not locate resource '%s'" % (resname,)
    )


def get_resource_string(resname):
    """Load the resource as bytes."""
    with open(get_resource_filename(resname), "rb") as fd:
        return fd.read()

