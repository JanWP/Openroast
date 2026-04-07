import argparse
import time

from localroaster import ControllerConfig, create_controller


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the standalone localroaster demo")
    parser.add_argument("--seconds", type=int, default=15, help="How long to run the demo")
    args = parser.parse_args()

    controller = create_controller(ControllerConfig())
    controller.connect()
    controller.target_temp_k = 488.71
    controller.fan_speed = 5
    controller.time_remaining_s = max(0, args.seconds - 3)
    controller.roast()

    start = time.monotonic()
    try:
        while time.monotonic() - start < args.seconds:
            telemetry = controller.telemetry()
            current_temp_c = telemetry.current_temp_k - 273.15
            target_temp_c = telemetry.target_temp_k - 273.15
            print(
                f"state={telemetry.state} temp={current_temp_c:6.1f}C "
                f"target={target_temp_c:6.1f}C fan={telemetry.fan_speed} "
                f"heater_on={int(telemetry.heater_output)} heater_level={telemetry.heater_level} "
                f"remaining={telemetry.time_remaining_s:3d}s total={telemetry.total_time_s:3d}s"
            )
            time.sleep(1.0)
    finally:
        controller.shutdown()


if __name__ == "__main__":
    main()

