import math
import time

from openroast.temperature import TEMP_UNIT_F, normalize_temperature_unit, temperature_to_celsius


def autotune_pid_for_backend(
    roaster,
    *,
    settle_s=3.0,
    test_duration_s=45.0,
    min_rise_c=3.0,
):
    """Run PID autotune against any supported backend.

    Preferred path is a backend-native `autotune_pid` implementation.
    If missing, run a generic step-response routine over the common
    roaster API (state, temp, target, heat setting, fan speed).
    """
    if roaster is None:
        raise RuntimeError("Autotune unavailable: no backend handle")

    _ensure_connected_idle(roaster)

    backend_autotune = getattr(roaster, "autotune_pid", None)
    if callable(backend_autotune):
        return _run_backend_autotune(
            backend_autotune,
            settle_s=settle_s,
            test_duration_s=test_duration_s,
            min_rise_c=min_rise_c,
        )

    # Compatibility path: some adapters expose autotune on an inner controller.
    controller = getattr(roaster, "_controller", None)
    controller_autotune = getattr(controller, "autotune_pid", None)
    if callable(controller_autotune):
        return _run_backend_autotune(
            controller_autotune,
            settle_s=settle_s,
            test_duration_s=test_duration_s,
            min_rise_c=min_rise_c,
        )

    return _run_generic_autotune(
        roaster,
        settle_s=settle_s,
        test_duration_s=test_duration_s,
        min_rise_c=min_rise_c,
    )


def autotune_pid_table_for_backend(
    roaster,
    *,
    fan_speeds=None,
    settle_s=20.0,
    test_duration_s=30.0,
    min_rise_c=3.0,
    progress_callback=None,
):
    """Run autotune across multiple runtime fan speeds.

    - Fan speeds are normalized to unique low-to-high integer values.
    - Stops on first failing speed.
    - Returns partial successful rows plus failure context.
    """
    if roaster is None:
        raise RuntimeError("Autotune unavailable: no backend handle")

    speeds = _normalize_fan_speed_sequence(roaster, fan_speeds)
    if not speeds:
        raise RuntimeError("Autotune requires at least one valid fan speed")

    original_fan_speed = getattr(roaster, "fan_speed", None)
    results = {}
    completed_speeds = []
    failed_speed = None
    error_text = None

    total_speeds = len(speeds)

    def _emit_progress(stage, *, index, speed, completed):
        if not callable(progress_callback):
            return
        progress_callback(
            {
                "stage": str(stage),
                "index": int(index),
                "total": int(total_speeds),
                "fan_speed": int(speed),
                "completed": int(completed),
            }
        )

    for index, speed in enumerate(speeds):
        display_index = index + 1
        try:
            _emit_progress("running", index=display_index, speed=speed, completed=len(completed_speeds))
            if original_fan_speed is not None:
                roaster.fan_speed = int(speed)
            tune = autotune_pid_for_backend(
                roaster,
                settle_s=settle_s,
                test_duration_s=test_duration_s,
                min_rise_c=min_rise_c,
            )
            row = _extract_plant_keys_for_profile_row(tune)
            results[str(int(speed))] = row
            completed_speeds.append(int(speed))
            _emit_progress("completed", index=display_index, speed=speed, completed=len(completed_speeds))
        except Exception as exc:
            failed_speed = int(speed)
            error_text = str(exc)
            _emit_progress("failed", index=display_index, speed=speed, completed=len(completed_speeds))
            break

    if original_fan_speed is not None:
        try:
            roaster.fan_speed = int(original_fan_speed)
        except Exception:
            # Ignore restoration failures in orchestration summary.
            pass

    return {
        "ok": failed_speed is None,
        "results": results,
        "completed_speeds": completed_speeds,
        "failed_speed": failed_speed,
        "error": error_text,
        "fan_speeds": speeds,
    }


def _normalize_fan_speed_sequence(roaster, fan_speeds):
    if fan_speeds is None:
        runtime_max = getattr(roaster, "max_fan_speed", None)
        if runtime_max is None:
            runtime_max = max(1, int(getattr(roaster, "fan_speed", 1)))
        fan_speeds = range(1, int(runtime_max) + 1)

    normalized = []
    seen = set()
    for value in fan_speeds:
        try:
            speed = int(value)
        except (TypeError, ValueError):
            continue
        if speed < 1 or speed in seen:
            continue
        seen.add(speed)
        normalized.append(speed)

    normalized.sort()
    return normalized


def _ensure_connected_idle(roaster):
    connected = bool(getattr(roaster, "connected", False))
    if not connected:
        raise RuntimeError("Autotune requires a connected backend")

    get_state = getattr(roaster, "get_roaster_state", None)
    if not callable(get_state):
        return

    state = get_state()
    if state == "idle":
        return

    idle = getattr(roaster, "idle", None)
    if callable(idle):
        idle()
        time.sleep(0.1)


def _run_backend_autotune(backend_autotune, *, settle_s, test_duration_s, min_rise_c):
    try:
        return backend_autotune(
            settle_s=float(settle_s),
            test_duration_s=float(test_duration_s),
            min_rise_c=float(min_rise_c),
        )
    except TypeError:
        # Backward-compatible path for adapters exposing no kwargs.
        return backend_autotune()


def _extract_plant_keys_for_profile_row(tune):
    """Extract plant-model keys using one canonical tune contract.

    Canonical mapping:
    - process_gain -> K
    - tau_s -> tau_s
    - dead_time_s -> L
    """
    if not isinstance(tune, dict):
        return {}

    def _as_positive_float(value):
        try:
            fvalue = float(value)
        except (TypeError, ValueError):
            return None
        if not (math.isfinite(fvalue) and fvalue > 0.0):
            return None
        return fvalue

    K = _as_positive_float(tune.get("process_gain"))
    tau_s = _as_positive_float(tune.get("tau_s"))
    L = _as_positive_float(tune.get("dead_time_s"))

    profile = {}
    if K is not None:
        profile["K"] = float(K)
    if tau_s is not None:
        profile["tau_s"] = float(tau_s)
    if L is not None:
        profile["L"] = float(L)
    return profile


def _run_generic_autotune(roaster, *, settle_s, test_duration_s, min_rise_c):
    temp_unit = normalize_temperature_unit(getattr(roaster, "temperature_unit", TEMP_UNIT_F), default=TEMP_UNIT_F)
    sample_dt = _get_sample_period_s(roaster)

    original_fan_speed = getattr(roaster, "fan_speed", None)
    original_heat_setting = getattr(roaster, "heat_setting", None)
    original_target_temp = getattr(roaster, "target_temp", None)

    baseline_samples_c = []
    response_samples = []
    start_time = time.monotonic()

    try:
        if original_fan_speed is not None:
            roaster.fan_speed = max(1, int(original_fan_speed))
        if original_heat_setting is not None:
            roaster.heat_setting = 0

        roast = getattr(roaster, "roast", None)
        if callable(roast):
            roast()

        settle_deadline = time.monotonic() + max(0.2, float(settle_s))
        while time.monotonic() < settle_deadline:
            baseline_samples_c.append(_read_temp_c(roaster, temp_unit))
            time.sleep(sample_dt)

        if not baseline_samples_c:
            raise RuntimeError("Autotune baseline sampling failed")
        baseline_c = sum(baseline_samples_c) / len(baseline_samples_c)

        step_input = _apply_generic_step_input(roaster, temp_unit, baseline_c)

        test_deadline = time.monotonic() + max(1.0, float(test_duration_s))
        while time.monotonic() < test_deadline:
            now = time.monotonic()
            response_samples.append((now - start_time, _read_temp_c(roaster, temp_unit)))
            time.sleep(sample_dt)

        if not response_samples:
            raise RuntimeError("Autotune response sampling failed")

        peak_c = max(temp_c for _, temp_c in response_samples)
        delta_c = peak_c - baseline_c
        if delta_c < float(min_rise_c):
            raise RuntimeError(
                f"Autotune rise too small ({delta_c:.2f} C); increase test duration"
            )

        rise_threshold_c = baseline_c + 0.5
        dead_time_s = next((t for t, temp_c in response_samples if temp_c >= rise_threshold_c), None)
        if dead_time_s is None:
            dead_time_s = 0.5

        tau_target_c = baseline_c + 0.632 * delta_c
        tau_time_s = next((t for t, temp_c in response_samples if temp_c >= tau_target_c), None)
        if tau_time_s is None:
            raise RuntimeError("Autotune failed to estimate time constant")

        process_gain = delta_c / max(1e-3, step_input)
        dead_time_s = max(0.2, float(dead_time_s))
        tau_s = max(0.2, float(float(tau_time_s) - dead_time_s))

        kp = 1.2 * tau_s / (process_gain * dead_time_s)
        ti_s = 2.0 * dead_time_s
        td_s = 0.5 * dead_time_s
        ki = kp / max(1e-3, ti_s)
        kd = kp * td_s

        if not all(math.isfinite(v) and v > 0.0 for v in (kp, ki, kd)):
            raise RuntimeError("Autotune produced non-finite PID values")

        return {
            "kp": float(kp),
            "ki": float(ki),
            "kd": float(kd),
            "baseline_c": float(baseline_c),
            "peak_c": float(peak_c),
            "delta_c": float(delta_c),
            "dead_time_s": float(dead_time_s),
            "tau_s": float(tau_s),
            "step_input": float(step_input),
        }
    finally:
        idle = getattr(roaster, "idle", None)
        if callable(idle):
            idle()

        if original_fan_speed is not None:
            roaster.fan_speed = int(original_fan_speed)
        if original_heat_setting is not None:
            roaster.heat_setting = int(original_heat_setting)
        if original_target_temp is not None:
            roaster.target_temp = int(original_target_temp)


def _get_sample_period_s(roaster):
    controller = getattr(roaster, "_controller", None)
    if controller is not None:
        config = getattr(controller, "config", None)
        if config is not None:
            sample_period = getattr(config, "sample_period_s", None)
            if sample_period is not None:
                return max(0.05, float(sample_period))
    return 0.25


def _read_temp_c(roaster, unit):
    return temperature_to_celsius(float(roaster.current_temp), unit)


def _apply_generic_step_input(roaster, unit, baseline_c):
    target_step_c = 45.0
    step_input = target_step_c

    if hasattr(roaster, "target_temp"):
        baseline_native = float(roaster.current_temp)
        target_native = baseline_native + _temperature_step_for_unit(target_step_c, unit)
        max_temp = getattr(roaster, "temperature_max", None)
        if max_temp is not None:
            target_native = min(float(max_temp), target_native)
        roaster.target_temp = int(round(target_native))

    if hasattr(roaster, "heat_setting"):
        roaster.heat_setting = 3

    return step_input


def _temperature_step_for_unit(step_c, unit):
    if unit == "F":
        return float(step_c) * 9.0 / 5.0
    if unit == "K":
        return float(step_c)
    return float(step_c)

