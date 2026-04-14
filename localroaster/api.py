from dataclasses import dataclass
from enum import StrEnum

from localroaster import parameter_catalog


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
    kp: float = parameter_catalog.PID_DEFAULT_KP
    ki: float = parameter_catalog.PID_DEFAULT_KI
    kd: float = parameter_catalog.PID_DEFAULT_KD
    sample_period_s: float = parameter_catalog.SAMPLE_PERIOD_DEFAULT_S
    pwm_cycle_s: float = parameter_catalog.PWM_CYCLE_DEFAULT_S
    ambient_temp_k: float = parameter_catalog.AMBIENT_DEFAULT_K
    max_temp_k: float = parameter_catalog.SAFETY_MAX_TEMP_DEFAULT_K
    mock_thermal_max_temp_k: float = parameter_catalog.MOCK_THERMAL_MAX_DEFAULT_K
    mock_tau_s: float = parameter_catalog.MOCK_TAU_DEFAULT_S
    mock_fan_cooling_k_per_step: float = parameter_catalog.MOCK_FAN_COOLING_DEFAULT_K_PER_STEP
    min_display_temp_k: float = parameter_catalog.MIN_DISPLAY_TEMP_DEFAULT_K
    heater_cutoff_enabled: bool = parameter_catalog.HEATER_CUTOFF_DEFAULT_ENABLED


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

