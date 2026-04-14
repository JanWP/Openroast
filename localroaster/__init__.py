"""Reusable backend/controller package for local coffee roaster hardware.

This package is intentionally frontend-agnostic. Openroast consumes it through
an adapter, but the same controller can back a CLI, web UI, or other frontend.

AI co-authorship disclosure for this fork is documented in NOTICE_AI.rst at
repository root.
"""

from localroaster.api import ControllerConfig, RoasterFault, RoasterState, Telemetry
from localroaster.controller import HardwareDriver, RoasterController
from localroaster.factory import create_controller
from localroaster.mock import MockHardwareDriver, create_mock_controller

__all__ = [
    "ControllerConfig",
    "RoasterFault",
    "RoasterState",
    "Telemetry",
    "HardwareDriver",
    "RoasterController",
    "MockHardwareDriver",
    "create_controller",
    "create_mock_controller",
]

