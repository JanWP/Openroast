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

The default real driver (`localroaster/drivers/default.py`) expects:

- MAX31855 thermocouple on SPI
- an SSR connected to a digital GPIO for heater on/off

Hardware wiring details are read from `localroaster/hardware_config.json`
(or from a file pointed to by `LOCALROASTER_HW_CONFIG`).

You can inspect the active file and parsed values with:

```sh
python -m localroaster.show_hw_config
```

Controller defaults are tuned for the requested local behavior:

- thermocouple sampling at 2 Hz (`sample_period_s=0.5`)
- PID output in percent (`0..100`)
- low-frequency PWM for SSR with ~1 second cycle (`pwm_cycle_s=1.0`)

`sample_period_s` and `pwm_cycle_s` are configurable in `ControllerConfig`.
Board pin assignment is intentionally *not* part of the API and is configured
in `hardware_config.json`.

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

## Suggested tweaks

- If your SSR clicks or the mains load prefers slower switching, increase
  `pwm_cycle_s` (for example to `2.0`).
- If control response is too slow/noisy, tune `kp`, `ki`, and `kd` in
  `ControllerConfig`.

## AI co-authorship disclosure

This fork includes substantial AI-assisted and AI-authored code changes, primarily using GitHub Copilot with GPT-5.3-Codex.

See `../NOTICE_AI.rst` for the project-level notice.

