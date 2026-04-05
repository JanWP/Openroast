# -*- coding: utf-8 -*-
# Roastero, released under GPLv3
import os
import sys
import shutil
import logging
import pathlib
import argparse
import multiprocessing
try:
    from PyQt5 import QtCore, QtGui, QtWidgets
except ImportError as exc:
    raise RuntimeError(
        "PyQt5 is required to run Openroast. On Raspberry Pi install "
        "python3-pyqt5 and python3-matplotlib from apt, or use pip with openroast[gui]."
    ) from exc

from openroast.controllers import recipe
from openroast.views import mainwindow
from openroast import utils as utils


def _parse_args():
    """Parse command-line arguments. Known args are consumed; Qt args are left."""
    parser = argparse.ArgumentParser(
        description="Openroast coffee roaster controller",
        add_help=False,  # let Qt handle unknown flags without crashing
    )
    parser.add_argument(
        "--backend",
        choices=["usb", "local"],
        default="usb",
        help=(
            "Hardware backend to use.  "
            "'usb'   – FreshRoast SR700 via USB (default).  "
            "'local' – Home-built roaster via the 'localroaster' library."
        ),
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Use mock/simulated USB hardware (for development without a roaster).",
    )
    known, _remaining = parser.parse_known_args()
    return known


def _create_roaster(args):
    """Instantiate and return the appropriate roaster backend object."""
    if args.backend == "local":
        from openroast.backends.local_roaster import LocalRoaster
        logging.info("openroastapp: using LOCAL hardware backend")
        return LocalRoaster(thermostat=True)
    else:
        # USB backend
        if args.mock:
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


class OpenroastApp(object):
    """Main application class."""
    def __init__(self, args=None):
        """Set up application, styles, fonts, and global object."""
        if args is None:
            args = _parse_args()
        self._args = args

        # app
        self.app = QtWidgets.QApplication(sys.argv)
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
        QtWidgets.QApplication.setStyleSheet(self.app, style)

        # copy recipes to user folder, if it doesn't exist
        # (to prevent overwriting pre-existing user data!)
        self.check_user_folder()

        # initialize roaster backend and recipe object
        self.roaster = _create_roaster(self._args)
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
            self.roaster)
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
    #os.chdir(get_script_dir())
    startup_dir = os.path.dirname(sys.argv[0])
    if startup_dir:
        os.chdir(startup_dir)
        print("changing to folder %s" % startup_dir)
    multiprocessing.freeze_support()
    args = _parse_args()
    app = OpenroastApp(args)
    app.run()


if __name__ == '__main__':
    main()
