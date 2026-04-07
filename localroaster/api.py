from dataclasses import dataclass
from enum import StrEnum


class RoasterState(StrEnum):
    DISCONNECTED = "disconnected"
    IDLE = "idle"
    ROASTING = "roasting"
    COOLING = "cooling"
    SLEEPING = "sleeping"
    FAULT = "fault"


@dataclass(slots=True)
class ControllerConfig:
    thermostat: bool = True
    kp: float = 0.06
    ki: float = 0.0075
    kd: float = 0.01
    sample_period_s: float = 0.5
    pwm_cycle_s: float = 1.0
    pwm_tick_s: float = 0.05
    ambient_temp_k: float = 295.15
    max_temp_k: float = 560.93
    min_display_temp_k: float = 338.71


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
    fault: str | None = None

