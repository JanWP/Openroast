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
    heater_segments: int = 8
    sample_period_s: float = 0.25
    ambient_temp_f: float = 72.0
    max_temp_f: float = 550.0
    min_display_temp_f: float = 150.0


@dataclass(slots=True)
class Telemetry:
    state: RoasterState
    connected: bool
    current_temp_f: float
    target_temp_f: int
    fan_speed: int
    heater_output: bool
    heater_level: int
    time_remaining_s: int
    total_time_s: int
    fault: str | None = None

