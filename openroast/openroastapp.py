# -*- coding: utf-8 -*-
# Roastero, released under GPLv3
import os
import sys
import shutil
import logging
import pathlib
import argparse
import multiprocessing

# Allow running the app directly as a script from the repo root, e.g.
# `python3 openroast/openroastapp.py ...`, by making both the `openroast`
# package and the sibling `localroaster` package importable.
if __package__ in (None, ""):
    _repo_root = pathlib.Path(__file__).resolve().parent.parent
    _repo_root_str = str(_repo_root)
    if _repo_root_str not in sys.path:
        sys.path.insert(0, _repo_root_str)

try:
    from PyQt5 import QtCore, QtGui, QtWidgets
except ImportError as exc:
    raise RuntimeError(
        "PyQt5 is required to run Openroast. On Raspberry Pi install "
        "python3-pyqt5 and python3-pyqtgraph from apt, "
        "or use pip with openroast[gui]."
    ) from exc

from openroast.controllers import recipe
from openroast.temperature import TEMP_UNIT_C, set_default_display_temperature_unit
from openroast.views import mainwindow
from openroast import utils as utils


def _parse_args():
    """Parse command-line arguments. Known args are consumed; Qt args are left."""
    parser = argparse.ArgumentParser(
        description="Openroast coffee roaster controller",
        add_help=True,
    )
    parser.add_argument(
        "--backend",
        choices=["usb", "usb-mock", "local", "local-mock"],
        default="usb",
        help=(
            "Hardware backend to use.  "
            "'usb'       – FreshRoast SR700 via USB (default).  "
            "'usb-mock'  – Simulated USB roaster (no hardware).  "
            "'local'     – Home-built roaster via the local backend package.  "
            "'local-mock' – Simulated local backend (no hardware)."
        ),
    )
    parser.add_argument(
        "--compact-ui",
        action="store_true",
        default=False,
        help="Use a denser layout tuned for 800x480 touchscreen displays.",
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        default=False,
        help="Start in fullscreen mode.",
    )
    known, _remaining = parser.parse_known_args()
    return known


def _create_roaster(args):
    """Instantiate and return the appropriate roaster backend object."""
    if args.backend in ("local", "local-mock"):
        try:
            from openroast.backends.local_roaster import LocalRoaster
            if args.backend == "local-mock":
                logging.info("openroastapp: using LOCAL MOCK backend")
                return LocalRoaster(thermostat=True, force_mock=True)
            logging.info("openroastapp: using LOCAL hardware backend")
            return LocalRoaster(thermostat=True)
        except ImportError as exc:
            if args.backend == "local-mock":
                from openroast import freshroastsr700_mock as freshroastsr700
                logging.warning(
                    "openroastapp: local backend import failed in local-mock mode; "
                    "falling back to USB mock backend for development."
                )
                logging.debug("local_roaster import failure", exc_info=exc)
                return freshroastsr700.freshroastsr700(thermostat=True)
            raise RuntimeError(
                "The local backend package is not importable. "
                "Use --backend local-mock for simulation, or install/fix local backend imports."
            ) from exc
    else:
        # USB backend
        if args.backend == "usb-mock":
            from openroast import freshroastsr700_mock as freshroastsr700
            logging.info("openroastapp: using MOCK USB backend")
        else:
            try:
                import freshroastsr700
                logging.info("openroastapp: using real USB backend (freshroastsr700)")
            except ImportError as exc:
                raise RuntimeError(
                    "The 'freshroastsr700' package is required for the USB backend. "
                    "Install it or choose --backend local."
                ) from exc
        return freshroastsr700.freshroastsr700(thermostat=True)


def _compact_style_overrides():
    # Keep this as late-appended CSS so it overrides mainStyle.css only in compact mode.
    return """
QToolBar {
    margin: 2% 2% 0px 2%;
}

QLabel#logo{
    padding: 6px 10px 2px 10px;
    font-size: 16px;
}

QLabel#heaterDebugLabel {
    font-size: 10px;
    margin: 6px 2px 2px 6px;
}

QLabel#heaterDebugLed {
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
    margin: 8px 4px 2px 2px;
}

QPushButton#toolbar {
    width: 88px;
    height: 24px;
    margin: 4px 4px 2px 4px;
    font-size: 11px;
}

QPushButton#toolbarUtility {
    width: 76px;
    height: 26px;
    margin: 4px 2px 2px 2px;
    font-size: 10px;
}

QPushButton {
    height: 30px;
    margin: 3px;
    font-size: 11px;
}

QLabel#label {
    font-size: 12px;
    padding: 6px;
}

QLabel#tempGauge {
    font-size: 30px;
    padding: 4px;
}

QLabel#timeWindow {
    font-size: 30px;
    padding: 4px;
}

QProgressBar {
    height: 22px;
}

QPushButton#nextButton {
    width: 90px;
    height: 24px;
}

QSpinBox#miniSpinBox {
    height: 22px;
}

QTimeEdit#miniSpinBox {
    height: 22px;
}
"""


def _screen_is_small(app):
    screen = app.primaryScreen()
    if screen is None:
        return False
    geometry = screen.availableGeometry()
    return geometry.height() <= 520


class OpenroastApp(object):
    """Main application class."""
    def __init__(self, args=None):
        """Set up application, styles, fonts, and global object."""
        if args is None:
            args = _parse_args()
        self._args = args

        # app
        self.app = QtWidgets.QApplication(sys.argv)
        if not self._args.compact_ui and _screen_is_small(self.app):
            self._args.compact_ui = True
            logging.info("openroastapp: auto-enabled compact UI for small display")
        # fonts
        # QtGui.QFontDatabase.addApplicationFont(
        #     "static/fonts/asap/asap-regular.ttf")
        qba = QtCore.QByteArray(
            utils.get_resource_string(
                "static/fonts/asap/asap-regular.ttf"
                )
            )
        QtGui.QFontDatabase.addApplicationFontFromData(qba)
        # QtGui.QFontDatabase.addApplicationFont(
        #     "static/fonts/asap/asap-bold.ttf")
        qba = QtCore.QByteArray(
            utils.get_resource_string(
                "static/fonts/asap/asap-bold.ttf"
                )
            )
        QtGui.QFontDatabase.addApplicationFontFromData(qba)
        # QtGui.QFontDatabase.addApplicationFont(
        #     "static/fonts/asap/asap-bold-italic.ttf")
        qba = QtCore.QByteArray(
            utils.get_resource_string(
                "static/fonts/asap/asap-bold-italic.ttf"
                )
            )
        QtGui.QFontDatabase.addApplicationFontFromData(qba)
        # QtGui.QFontDatabase.addApplicationFont(
        #     "static/fonts/asap/asap-italic.ttf")
        qba = QtCore.QByteArray(
            utils.get_resource_string(
                "static/fonts/asap/asap-italic.ttf"
                )
            )
        QtGui.QFontDatabase.addApplicationFontFromData(qba)
        # styles
        style = utils.get_resource_string(
            "static/mainStyle.css"
            ).decode("utf-8")
        style = style.replace(
            'static/images/downArrow.png',
            pathlib.Path(
                utils.get_resource_filename('static/images/downArrow.png')
                ).as_posix())
        style = style.replace(
            'static/images/upArrow.png',
            pathlib.Path(
                utils.get_resource_filename('static/images/upArrow.png')
                ).as_posix())
        if self._args.compact_ui:
            style += "\n" + _compact_style_overrides()
        QtWidgets.QApplication.setStyleSheet(self.app, style)

        # copy recipes to user folder, if it doesn't exist
        # (to prevent overwriting pre-existing user data!)
        self.check_user_folder()

        # initialize roaster backend and recipe object
        self.roaster = _create_roaster(self._args)
        # Centralize default display temperature unit once at startup.
        # This can later be wired to a user preference.
        self._default_display_temperature_unit = TEMP_UNIT_C
        set_default_display_temperature_unit(self._default_display_temperature_unit)
        self.recipes = recipe.Recipe(self.roaster, self)
        if(not self.roaster.set_state_transition_func(
            self.recipes.move_to_next_section)):
            # signal an error somehow
            logging.error(
                "OpenroastApp.__init__ failed to set state transition "
                "callback.  This won't work."
                )

    def check_user_folder(self):
        """Checks copies user folder if no user folder exists."""
        user_folder = os.path.expanduser('~/Documents/Openroast/')

        if not os.path.isdir(user_folder):
            # shutil.copytree("static/Recipes",
            #     os.path.join(user_folder, "Recipes"))
            shutil.copytree(
                utils.get_resource_filename("static/Recipes"),
                os.path.join(user_folder, "Recipes"))

    def roasttab_flag_update_controllers(self):
        # print("app.roasttab_flag_update_controllers called")
        self.window.roast.schedule_update_controllers()

    def run(self):
        """Turn everything on."""
        self.roaster.auto_connect()
        self.window = mainwindow.MainWindow(
            self.recipes,
            self.roaster,
            compact_ui=self._args.compact_ui,
            fullscreen=self._args.fullscreen)
        # Apply mode after window creation and explicitly request fullscreen
        # to avoid backend/window-manager differences at startup.
        self.window.apply_window_mode()
        if self._args.fullscreen:
            self.window.showFullScreen()
        else:
            self.window.show()
        qt_exec = getattr(self.app, "exec", self.app.exec_)
        sys.exit(qt_exec())


# def get_script_dir(follow_symlinks=True):
    # """Checks where the script is being executed from to verify the imports
    # will work properly."""
    # if getattr(sys, 'frozen', False):
        # path = os.path.abspath(sys.executable)
    # else:
        # path = inspect.getabsfile(get_script_dir)

    # if follow_symlinks:
        # path = os.path.realpath(path)

    # return os.path.dirname(path)


def main():
    args = _parse_args()
    #os.chdir(get_script_dir())
    startup_dir = os.path.dirname(sys.argv[0])
    if startup_dir:
        os.chdir(startup_dir)
        print("changing to folder %s" % startup_dir)
    multiprocessing.freeze_support()
    app = OpenroastApp(args)
    app.run()


if __name__ == '__main__':
    main()
