import logging

from localroaster.api import ControllerConfig
from localroaster.controller import HardwareDriver, RoasterController
from localroaster.mock import MockHardwareDriver


def create_controller(
    config: ControllerConfig | None = None,
    hardware_driver: HardwareDriver | None = None,
    force_mock: bool = False,
) -> RoasterController:
    """Create a controller using a supplied driver or a default one.

    If no real hardware driver is installed yet, the mock driver is used so the
    API remains runnable during frontend and integration development.
    """
    config = config or ControllerConfig()
    if hardware_driver is not None:
        driver = hardware_driver
    elif force_mock:
        driver = MockHardwareDriver(config)
        logging.info("localroaster: force_mock=True, using mock driver")
    else:
        driver = _load_default_driver(config)
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

