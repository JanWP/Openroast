import logging

from localroaster.api import ControllerConfig
from localroaster.controller import HardwareDriver, RoasterController
from localroaster.mock import MockHardwareDriver


def create_controller(
    config: ControllerConfig | None = None,
    hardware_driver: HardwareDriver | None = None,
) -> RoasterController:
    """Create a controller using a supplied driver or a default one.

    If no real hardware driver is installed yet, the mock driver is used so the
    API remains runnable during frontend and integration development.
    """
    config = config or ControllerConfig()
    driver = hardware_driver or _load_default_driver(config)
    return RoasterController(driver, config=config)


def _load_default_driver(config: ControllerConfig) -> HardwareDriver:
    try:
        from localroaster.drivers.default import create_driver  # type: ignore
        logging.info("localroaster: using localroaster.drivers.default")
        return create_driver(config)
    except ImportError:
        logging.warning(
            "localroaster: default hardware driver not found; using mock driver. "
            "Add localroaster/drivers/default.py to control real hardware."
        )
        return MockHardwareDriver(config)

