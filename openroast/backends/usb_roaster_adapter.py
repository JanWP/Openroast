# -*- coding: utf-8 -*-
"""Compatibility wrapper for USB backends.

The external `freshroastsr700` package does not currently expose a formal
capabilities API. This adapter provides a backend-owned capability surface
for Openroast without coupling to app-level config constants.
"""

USB_BACKEND_FAN_SPEED_MAX = 9


class USBRoasterAdapter:
    """Thin proxy that adds capability properties expected by Openroast."""

    def __init__(self, roaster):
        self._roaster = roaster

    @property
    def max_fan_speed(self):
        return int(USB_BACKEND_FAN_SPEED_MAX)


    def __getattr__(self, name):
        return getattr(self._roaster, name)

    def __setattr__(self, name, value):
        if name == "_roaster":
            super().__setattr__(name, value)
            return
        setattr(self._roaster, name, value)

