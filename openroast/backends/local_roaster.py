# -*- coding: utf-8 -*-
# Local hardware backend for Openroast.
#
# This module replaces the freshroastsr700 USB backend with a direct
# hardware interface for a home-built roaster connected via GPIO / SPI
# (thermocouple) on a Raspberry Pi.
#
# The external library "localroaster" must be installed separately and
# must expose the following API:
#
#   localroaster.read_temperature() -> float
#       Returns the current thermocouple temperature in degrees Fahrenheit.
#
#   localroaster.set_heater(on: bool) -> None
#       Turns the heating element fully on or off (bang-bang control is
#       handled here in this wrapper via the PID + heat_controller
#       classes that are copied from freshroastsr700_mock).
#
#   localroaster.set_fan(speed: int) -> None
#       Sets the fan speed (1-9).  The mapping from speed integer to
#       actual hardware PWM / relay is left to the library.
#
# If "localroaster" is not yet installed a stub is used automatically so
# that the GUI can still be tested on a development machine.

import time
import datetime
import logging
import threading
import multiprocessing as mp
from multiprocessing import sharedctypes
import math

# ---------------------------------------------------------------------------
# Try to import the real hardware library; fall back to a stub so the GUI
# can be developed / tested without actual hardware attached.
# ---------------------------------------------------------------------------
try:
    import localroaster as _hw
    _HW_AVAILABLE = True
    logging.info("local_roaster: using real localroaster hardware library")
except ImportError:
    _HW_AVAILABLE = False
    logging.warning(
        "local_roaster: 'localroaster' library not found – using simulation stub. "
        "Install the library to control real hardware."
    )

    class _HWStub:
        """Minimal stub that simulates hardware so the GUI still works."""
        def __init__(self):
            self._temp = 72.0         # °F
            self._heater_on = False
            self._tau = 30.0
            self._A = math.exp(-0.25 / self._tau)
            self._B = 1.0 - self._A

        def read_temperature(self) -> float:
            target = 550.0 if self._heater_on else 72.0
            self._temp = self._A * self._temp + self._B * target
            return max(self._temp, 72.0)

        def set_heater(self, on: bool) -> None:
            self._heater_on = on

        def set_fan(self, speed: int) -> None:
            pass  # no-op in stub

    _hw = _HWStub()


# ---------------------------------------------------------------------------
# PID controller (identical to freshroastsr700.pid.PID)
# ---------------------------------------------------------------------------
class _PID:
    def __init__(self, kp, ki, kd, Output_max, Output_min):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.max = Output_max
        self.min = Output_min
        self._integral = 0.0
        self._prev_error = 0.0

    def update(self, current, target):
        error = target - current
        self._integral += error
        derivative = error - self._prev_error
        self._prev_error = error
        output = self.kp * error + self.ki * self._integral + self.kd * derivative
        return max(self.min, min(self.max, output))


# ---------------------------------------------------------------------------
# Bang-bang heat controller (identical to freshroastsr700_mock.heat_controller)
# ---------------------------------------------------------------------------
class _HeatController:
    def __init__(self, number_of_segments=8):
        self._num_segments = number_of_segments
        self._output_array = [[False] * number_of_segments
                              for _ in range(1 + number_of_segments)]
        if number_of_segments == 8:
            self._output_array[0] = [False]*8
            self._output_array[1] = [True,  False, False, False, False, False, False, False]
            self._output_array[2] = [True,  False, False, False, True,  False, False, False]
            self._output_array[3] = [True,  False, False, True,  False, False, True,  False]
            self._output_array[4] = [True,  False, True,  False, True,  False, True,  False]
            self._output_array[5] = [True,  True,  False, True,  True,  False, True,  False]
            self._output_array[6] = [True,  True,  True,  False, True,  True,  True,  False]
            self._output_array[7] = [True,  True,  True,  True,  True,  True,  True,  False]
            self._output_array[8] = [True]*8
        else:
            for i in range(1 + number_of_segments):
                for j in range(number_of_segments):
                    self._output_array[i][j] = j < i
        self._heat_level = 0
        self._heat_level_now = 0
        self._current_index = 0

    @property
    def heat_level(self):
        return self._heat_level

    @heat_level.setter
    def heat_level(self, value):
        self._heat_level = max(0, min(self._num_segments, int(round(value))))

    def about_to_rollover(self):
        return self._current_index >= self._num_segments

    def generate_bangbang_output(self):
        if self._current_index >= self._num_segments:
            self._heat_level_now = self._heat_level
            self._current_index = 0
        out = self._output_array[self._heat_level_now][self._current_index]
        self._current_index += 1
        return out


# ---------------------------------------------------------------------------
# LocalRoaster – drop-in replacement for freshroastsr700
# ---------------------------------------------------------------------------
class LocalRoaster:
    """Controls a home-built roaster via the 'localroaster' hardware library.

    Presents exactly the same interface as freshroastsr700 so that the rest
    of the Openroast application needs no changes.
    """

    # State byte-string constants – kept identical to freshroastsr700 so that
    # get_roaster_state() returns the same strings.
    _STATE_IDLE      = b'\x02\x01'
    _STATE_COOLING   = b'\x04\x04'
    _STATE_SLEEPING  = b'\x08\x01'
    _STATE_ROASTING  = b'\x04\x02'

    # Attribute used by roasttab.py to detect the "connecting" phase.
    CS_CONNECTING = 1

    def __init__(self,
                 update_data_func=None,
                 state_transition_func=None,
                 thermostat=True,
                 kp=0.06, ki=0.0075, kd=0.01,
                 heater_segments=8):

        # Shared-memory state (process-safe)
        self._fan_speed      = sharedctypes.Value('i', 1)
        self._heat_setting   = sharedctypes.Value('i', 0)
        self._target_temp    = sharedctypes.Value('i', 150)
        self._current_temp   = sharedctypes.Value('i', 150)
        self._time_remaining = sharedctypes.Value('i', 0)
        self._total_time     = sharedctypes.Value('i', 0)
        self._heater_level   = sharedctypes.Value('i', 0)
        self._current_state  = sharedctypes.Array('c', self._STATE_IDLE)
        self._connected      = sharedctypes.Value('i', 0)
        self._connect_state  = sharedctypes.Value('i', 0)
        self._cont           = sharedctypes.Value('i', 1)

        # PID / thermostat settings (not process-safe – read only at spawn time)
        self._thermostat    = thermostat
        self._pid_kp        = kp
        self._pid_ki        = ki
        self._pid_kd        = kd
        self._heater_segs   = heater_segments

        # Callback infrastructure (mirrors freshroastsr700)
        self._create_update_data_system(update_data_func)
        self._create_state_transition_system(state_transition_func)

        # Spawn background processes
        self._comm_process = mp.Process(
            target=_comm_loop,
            args=(
                self._current_state,
                self._fan_speed,
                self._heat_setting,
                self._target_temp,
                self._current_temp,
                self._heater_level,
                self._connected,
                self._connect_state,
                self._cont,
                self._thermostat,
                self._pid_kp,
                self._pid_ki,
                self._pid_kd,
                self._heater_segs,
                self.update_data_event,
            ),
            daemon=True,
        )
        self._comm_process.start()

        self._timer_process = mp.Process(
            target=_timer_loop,
            args=(
                self._current_state,
                self._time_remaining,
                self._total_time,
                self._cont,
                self.state_transition_event,
            ),
            daemon=True,
        )
        self._timer_process.start()

    # ------------------------------------------------------------------
    # Callback helper infrastructure (mirrors freshroastsr700_mock)
    # ------------------------------------------------------------------
    def _create_update_data_system(self, func, setFunc=True, createThread=False):
        if not hasattr(self, 'update_data_event'):
            self.update_data_event = mp.Event()
        if setFunc:
            self.update_data_func = func
        if self.update_data_func is not None:
            if createThread:
                self._update_data_thread = threading.Thread(
                    name='local_update_data',
                    target=self._event_thread,
                    args=(self.update_data_event, self.update_data_func),
                    daemon=True,
                )
        else:
            self._update_data_thread = None

    def _create_state_transition_system(self, func, setFunc=True, createThread=False):
        if not hasattr(self, 'state_transition_event'):
            self.state_transition_event = mp.Event()
        if setFunc:
            self.state_transition_func = func
        if self.state_transition_func is not None:
            if createThread:
                self._state_transition_thread = threading.Thread(
                    name='local_state_transition',
                    target=self._event_thread,
                    args=(self.state_transition_event, self.state_transition_func),
                    daemon=True,
                )
        else:
            self._state_transition_thread = None

    @staticmethod
    def _event_thread(event, callback):
        while event.wait():
            event.clear()
            callback()

    # ------------------------------------------------------------------
    # Public interface – matches freshroastsr700
    # ------------------------------------------------------------------
    @property
    def connected(self):
        return self._connected.value

    @property
    def connect_state(self):
        return self._connect_state.value

    @property
    def fan_speed(self):
        return self._fan_speed.value

    @fan_speed.setter
    def fan_speed(self, value):
        if value not in range(1, 10):
            raise ValueError("fan_speed must be 1-9")
        self._fan_speed.value = value

    @property
    def heat_setting(self):
        return self._heat_setting.value

    @heat_setting.setter
    def heat_setting(self, value):
        if value not in range(0, 4):
            raise ValueError("heat_setting must be 0-3")
        self._heat_setting.value = value

    @property
    def target_temp(self):
        return self._target_temp.value

    @target_temp.setter
    def target_temp(self, value):
        if value not in range(150, 551):
            raise ValueError("target_temp must be 150-550")
        self._target_temp.value = value

    @property
    def current_temp(self):
        return self._current_temp.value

    @property
    def time_remaining(self):
        return self._time_remaining.value

    @time_remaining.setter
    def time_remaining(self, value):
        self._time_remaining.value = value

    @property
    def total_time(self):
        return self._total_time.value

    @total_time.setter
    def total_time(self, value):
        self._total_time.value = value

    @property
    def heater_level(self):
        return self._heater_level.value

    def get_roaster_state(self):
        value = self._current_state.value
        if value == self._STATE_IDLE:
            return 'idle'
        elif value == self._STATE_COOLING:
            return 'cooling'
        elif value == self._STATE_SLEEPING:
            return 'sleeping'
        elif value == self._STATE_ROASTING:
            return 'roasting'
        elif value == b'\x00\x00' or value == b'':
            return 'connecting'
        else:
            return 'unknown'

    def idle(self):
        self._current_state.value = self._STATE_IDLE

    def roast(self):
        self._current_state.value = self._STATE_ROASTING

    def cool(self):
        self._current_state.value = self._STATE_COOLING

    def sleep(self):
        self._current_state.value = self._STATE_SLEEPING

    def set_state_transition_func(self, func):
        """Must be called before auto_connect(). Mirrors freshroastsr700 API."""
        if self._connected.value:
            logging.error(
                "LocalRoaster.set_state_transition_func must be called before "
                "auto_connect(). Not registering func."
            )
            return False
        self._create_state_transition_system(func)
        return True

    def auto_connect(self):
        """Signal the comm process to start, and launch callback threads."""
        self._connected.value = 1   # local hardware is always "connected"
        self._connect_state.value = 0

        if self.update_data_func is not None:
            self._create_update_data_system(None, setFunc=False, createThread=True)
            self._update_data_thread.start()
        if self.state_transition_func is not None:
            self._create_state_transition_system(None, setFunc=False, createThread=True)
            self._state_transition_thread.start()

    def disconnect(self):
        self._cont.value = 0


# ---------------------------------------------------------------------------
# comm loop – runs in a separate process
# ---------------------------------------------------------------------------
def _comm_loop(current_state, fan_speed, heat_setting, target_temp,
               current_temp, heater_level, connected, connect_state,
               cont, thermostat, kp, ki, kd, heater_segments,
               update_data_event):
    """Background process: reads thermocouple, drives heater & fan via PID."""
    # Re-import inside the spawned process
    try:
        import localroaster as hw
    except ImportError:
        # Use the same stub as above
        import math as _math

        class _Stub:
            def __init__(self):
                self._temp = 72.0
                self._heater_on = False
                _tau = 30.0
                self._A = _math.exp(-0.25 / _tau)
                self._B = 1.0 - self._A

            def read_temperature(self):
                target = 550.0 if self._heater_on else 72.0
                self._temp = self._A * self._temp + self._B * target
                return max(self._temp, 72.0)

            def set_heater(self, on):
                self._heater_on = on

            def set_fan(self, speed):
                pass

        hw = _Stub()

    pidc = None
    heater = None
    if thermostat:
        pidc  = _PID(kp, ki, kd, Output_max=heater_segments, Output_min=0)
        heater = _HeatController(number_of_segments=heater_segments)

    STATE_ROASTING = b'\x04\x02'
    STATE_COOLING  = b'\x04\x04'

    while cont.value:
        start = datetime.datetime.now()

        # --- Read thermocouple ---
        try:
            temp = hw.read_temperature()
        except Exception as exc:
            logging.warning("local_roaster: read_temperature failed: %s", exc)
            temp = current_temp.value  # keep last known value

        current_temp.value = int(round(max(150, min(550, temp))))

        # --- PID / heater control ---
        state = current_state.value
        if thermostat and pidc is not None and heater is not None:
            if state == STATE_ROASTING:
                if heater.about_to_rollover():
                    output = pidc.update(current_temp.value, target_temp.value)
                    heater.heat_level = output
                    heater_level.value = heater.heat_level
                heater_on = heater.generate_bangbang_output()
                heat_setting.value = 3 if heater_on else 0
            else:
                heater.heat_level = 0
                heater_level.value = 0
                heat_setting.value = 0
        else:
            # Manual heat_setting mode (thermostat=False)
            heater_on = heat_setting.value > 0
            heat_setting.value = heat_setting.value  # no-op, already set by GUI

        # --- Fan ---
        try:
            hw.set_heater(heat_setting.value > 0)
            hw.set_fan(fan_speed.value)
        except Exception as exc:
            logging.warning("local_roaster: hardware command failed: %s", exc)

        # --- Notify GUI ---
        if update_data_event is not None:
            update_data_event.set()

        # --- Keep 0.25 s period ---
        elapsed = (datetime.datetime.now() - start).total_seconds()
        sleep_for = 0.25 - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)


# ---------------------------------------------------------------------------
# timer loop – runs in a separate process (identical logic to freshroastsr700)
# ---------------------------------------------------------------------------
def _timer_loop(current_state, time_remaining, total_time, cont,
                state_transition_event):
    STATE_ROASTING = b'\x04\x02'
    STATE_COOLING  = b'\x04\x04'

    while cont.value:
        state = current_state.value
        if state in (STATE_ROASTING, STATE_COOLING):
            time.sleep(1)
            total_time.value += 1
            if time_remaining.value > 0:
                time_remaining.value -= 1
            else:
                if state_transition_event is not None:
                    state_transition_event.set()
        else:
            time.sleep(0.01)

