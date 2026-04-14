from dataclasses import dataclass
from enum import StrEnum


class RoasterState(StrEnum):
    DISCONNECTED = "disconnected"
    IDLE = "idle"
    ROASTING = "roasting"
    COOLING = "cooling"
    SLEEPING = "sleeping"
    FAULT = "fault"


class RoasterFault(StrEnum):
    """Known fault conditions for the roaster controller.

    Over-temperature faults are *latching*: once set, they persist until the
    user explicitly calls ``clear_fault()``.  There is no automatic recovery,
    even if the measured temperature drops below the configured limit.  This
    ensures the operator is always aware that a safety event occurred.
    """

    OVER_TEMPERATURE = "over-temperature safety cutoff"
    SENSOR_ERROR = "sensor-error"


@dataclass(slots=True)
class ControllerConfig:
    thermostat: bool = True
    # kp: float = 0.06
    # ki: float = 0.0075
    # kd: float = 0.01
    # Defaults migrated from Fahrenheit-tuned values to Celsius-domain PID.
    # Scale factor is 9/5 because error_F = error_C * 9/5.
    kp: float = 0.108
    ki: float = 0.0135
    kd: float = 0.018
    sample_period_s: float = 0.5
    pwm_cycle_s: float = 1.0
    pwm_tick_s: float = 0.05
    ambient_temp_k: float = 295.15
    max_temp_k: float = 560.93
    min_display_temp_k: float = 338.71
    heater_cutoff_enabled: bool = True


@dataclass(slots=True)
class Telemetry:
    state: RoasterState
    connected: bool
    current_temp_k: float
    target_temp_k: float
    fan_speed: int
    heater_output: bool
    heater_level: int
    time_remaining_s: int
    total_time_s: int
    fault: RoasterFault | str | None = None

