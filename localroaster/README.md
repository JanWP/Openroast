# localroaster

`localroaster` is a frontend-agnostic controller package for a home-built coffee roaster.

## Goals

- keep GPIO / thermocouple / PID logic reusable outside Openroast
- provide a stable machine-oriented API for future frontends
- let Openroast remain a UI + workflow layer with a thin compatibility adapter

## Public API

- `ControllerConfig`
- `RoasterState`
- `Telemetry`
- `HardwareDriver`
- `RoasterController`
- `create_controller()`
- `create_mock_controller()`

## Default behavior

`create_controller()` tries to import `localroaster.drivers.default.create_driver(config)`.
If that module does not exist yet, it falls back to a mock thermal model.

## Running the demo

```sh
python -m localroaster.demo --seconds 10
```

## Adding a real hardware driver

Create `localroaster/drivers/default.py` that returns a `HardwareDriver` implementation:

```python
from localroaster.controller import HardwareDriver

class MyDriver(HardwareDriver):
    def read_temperature_f(self) -> float:
        ...

    def set_heater(self, on: bool) -> None:
        ...

    def set_fan_speed(self, speed: int) -> None:
        ...

    def close(self) -> None:
        ...


def create_driver(config):
    return MyDriver()
```

