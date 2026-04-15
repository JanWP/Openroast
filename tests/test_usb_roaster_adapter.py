import unittest

from openroast.backends.usb_roaster_adapter import (
    USBRoasterAdapter,
    USB_BACKEND_FAN_SPEED_MAX,
)


class _DummyUSBRoaster:
    def __init__(self):
        self.fan_speed = 1
        self.some_value = 10

    def roast(self):
        return "roasting"


class USBRoasterAdapterTests(unittest.TestCase):
    def test_exposes_backend_capability_constants(self):
        adapter = USBRoasterAdapter(_DummyUSBRoaster())
        self.assertEqual(adapter.max_fan_speed, USB_BACKEND_FAN_SPEED_MAX)

    def test_attribute_passthrough(self):
        roaster = _DummyUSBRoaster()
        adapter = USBRoasterAdapter(roaster)

        self.assertEqual(adapter.fan_speed, 1)
        adapter.fan_speed = 5
        self.assertEqual(roaster.fan_speed, 5)
        self.assertEqual(adapter.roast(), "roasting")


if __name__ == "__main__":
    unittest.main()

