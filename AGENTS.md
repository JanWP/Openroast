# AGENTS.md

This repository contains Python code for controlling coffee roasters, with a PyQt GUI frontend and backend support for USB-controlled and local hardware roasters.
The codebase is split between `openroast/` for UI/orchestration and `localroaster/` for controller and hardware logic.

## Scope
- Repo root is `src/Openroast/`.
- Main packages:
  - `openroast/`: PyQt UI, app config, recipe orchestration, backend selection.
  - `localroaster/`: frontend-agnostic controller, mock/real hardware drivers, safety logic, autotune.

## Architecture that matters
- Startup is in `openroast/openroastapp.py`: parse CLI args, load normalized config, create the selected backend, create `Recipe`, then build `MainWindow`.
- `localroaster/controller.py` is the control-law source of truth: machine state, PID/PWM loops, over-temperature handling, timer transitions, autotune, and shutdown.
- `openroast/backends/local_roaster.py` is a compatibility adapter over `localroaster`; avoid duplicating controller logic there.
- `openroast/controllers/recipe.py` owns roast-section orchestration and runtime fan mapping. It still uses shared memory for the legacy USB path, but local backends use lightweight thread-safe storage.
- UI-facing backend expectations are formalized in `openroast/roaster_protocol.py`.

## Current backend/config model
- Supported backends are `usb`, `usb-mock`, `local`, and `local-mock` (`openroast/app_config.py`, `openroast/openroastapp.py`).
- For `local` / `local-mock`, persisted tuning is plant-model based: `openroast/app_config.py` stores `control.plantProfiles[backend][fan] = {K, tau_s, L}`.
- `localroaster` synthesizes effective PID gains from those plant rows at runtime; fan-speed changes are expected to reapply the active row.
- Recipe fan speeds are still on the legacy scale. Always map them through `openroast/fan_speed.py` instead of assuming recipe and runtime fan domains are identical.
- Use `openroast/app_config.py` for config migration, clamping, and temperature-unit conversion; preserve unknown backend keys/rows on save.

## Hardware and runtime notes
- `localroaster/factory.py` falls back to the mock driver if no real default driver is available, so development should work without real hardware.
- Real local hardware wiring comes from `localroaster/hardware_config.json` or `LOCALROASTER_HW_CONFIG`.
- Public project docs worth checking first are `README.rst`, `localroaster/README.md`, and `NOTICE_AI.rst`.

## Developer workflows
- Linux dev install from repo root: `python3.13 -m venv .venv && . .venv/bin/activate && python -m pip install -U pip && python -m pip install -e .[gui]`
- Local hardware extras: `python -m pip install -e .[local-hw]`
- Run GUI: `openroast --backend local-mock`
- Run from source: `python openroast/openroastapp.py --backend local-mock`
- Standalone backend demo: `python -m localroaster.demo --seconds 10`
- Smoke test: `python scripts/smoke_test.py`

## Commit message convention
- Recent commits on this branch use `type: Imperative summary` subjects, e.g. `feat: Configure standby fan behavior outside roast cycles` or `docs: Clarify PWM dependency in build requirements`.
- Follow with a short bullet-list body when useful.
- AI disclosure is public repo policy (`README.rst`, `NOTICE_AI.rst`): use `Generated-by:` for mostly AI-authored commits, `Assisted-by:` for partial AI help, and do not use `Co-authored-by:` for AI.
- Practical note: shell-built commit commands can mangle blank lines before trailers. Prefer separate message paragraphs / separate `-m` blocks, then verify with `git log -1 --pretty=fuller` and amend if needed.

## Testing conventions in this repo
- Tests are mostly `unittest` style but are routinely run with `pytest`.
- For Qt tests, set `QT_QPA_PLATFORM=offscreen` (see `tests/test_mainwindow_init.py`).
- Prefer focused runs for the layer you changed, e.g. `tests/test_controller.py`, `tests/test_local_roaster.py`, `tests/test_app_config_expert.py`, `tests/test_preferences_tab_expert.py`.
- Prefer polling helpers like `wait_for(...)` over raw sleeps for controller/thread tests.

