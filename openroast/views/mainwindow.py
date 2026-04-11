# -*- coding: utf-8 -*-
# Roastero, released under GPLv3

import os
import json
import shutil

from PyQt5 import QtGui
from PyQt5 import QtCore
from PyQt5 import QtWidgets

from openroast.views import roasttab
from openroast.views import recipestab
from openroast.views import aboutwindow
from openroast.version import __version__

class MainWindow(QtWidgets.QMainWindow):
    heaterOutputChanged = QtCore.pyqtSignal(bool)
    heaterLevelChanged = QtCore.pyqtSignal(int)

    def __init__(self, recipes, roaster, compact_ui=False, fullscreen=False):
        super(MainWindow, self).__init__()
        self._heaterLedOn = None
        self._heaterLevel = None

        # Define main window for the application.
        self.setWindowTitle('Openroast v%s' % __version__)
        self.setMinimumSize(800, 480)
        self.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        self.compact_ui = compact_ui
        self.fullscreen = fullscreen

        # keep a copy of roaster & recipes, needed here
        self.roaster = roaster
        self.recipes = recipes

        # Create toolbar.
        self.create_toolbar()

        # Create tabs.
        self.create_tabs(self.roaster, recipes)

        # Create menu.
        self.create_actions()
        self.create_menus()
        self.create_shortcuts()

        self.apply_window_mode()
        self.heaterOutputChanged.connect(self._apply_heater_led_state)
        self.heaterLevelChanged.connect(self._apply_heater_level_text)
        register_heater_cb = getattr(self.roaster, "set_heater_output_func", None)
        if callable(register_heater_cb):
            register_heater_cb(self.on_heater_output_changed)
        register_heater_level_cb = getattr(self.roaster, "set_heater_level_func", None)
        if callable(register_heater_level_cb):
            register_heater_level_cb(self.on_heater_level_changed)
        self.update_heater_debug_indicators()


    def create_actions(self):
        # File menu actions.
        self.clearRoastAct = QtWidgets.QAction(
            "&Clear",
            self,
            shortcut=QtGui.QKeySequence(
                QtCore.Qt.CTRL + QtCore.Qt.SHIFT + QtCore.Qt.Key_C),
            statusTip="Clear the roast window",
            triggered=self.roast.clear_roast)

        self.newRoastAct = QtWidgets.QAction("&Roast Again", self,
            shortcut=QtGui.QKeySequence(QtCore.Qt.CTRL + QtCore.Qt.Key_R),
            statusTip="Roast recipe again",
            triggered=self.roast.reset_current_roast)

        self.importRecipeAct = QtWidgets.QAction("&Import Recipe", self,
            shortcut=QtGui.QKeySequence(QtCore.Qt.CTRL + QtCore.Qt.Key_I),
            statusTip="Import a recipe file",
            triggered=self.import_recipe_file)

        self.exportRecipeAct = QtWidgets.QAction("&Export Recipe", self,
            shortcut=QtGui.QKeySequence(QtCore.Qt.CTRL + QtCore.Qt.Key_E),
            statusTip="Export a recipe file",
            triggered=self.export_recipe_file)

        self.saveRoastGraphAct = QtWidgets.QAction("&Save Roast Graph", self,
            shortcut=QtGui.QKeySequence(QtCore.Qt.CTRL + QtCore.Qt.Key_K),
            statusTip="Save an image of the roast graph",
            triggered=self.roast.save_roast_graph)

        self.saveRoastGraphCSVAct = QtWidgets.QAction("&Save Roast Graph CSV", self,
            statusTip="Save the roast graph as a csv",
            triggered=self.roast.save_roast_graph_csv)

        self.openAboutWindow = QtWidgets.QAction("&About", self,
            statusTip="About openroast",
            triggered=self.open_about_window)

        self.quitAppAct = QtWidgets.QAction("&Quit", self,
            shortcut=QtGui.QKeySequence(QtCore.Qt.CTRL + QtCore.Qt.Key_Q),
            statusTip="Quit Openroast",
            triggered=self.close)

    def create_shortcuts(self):
        # Fullscreen toggles for touchscreen/kiosk environments.
        self.fullscreenShortcutF11 = QtWidgets.QShortcut(
            QtGui.QKeySequence(QtCore.Qt.Key_F11), self)
        self.fullscreenShortcutF11.activated.connect(self.toggle_fullscreen)

        self.fullscreenShortcutEsc = QtWidgets.QShortcut(
            QtGui.QKeySequence(QtCore.Qt.Key_Escape), self)
        self.fullscreenShortcutEsc.activated.connect(self.exit_fullscreen)

        # Toggle menu bar visibility (useful when compact mode hides it).
        self.toggleMenuBarShortcut = QtWidgets.QShortcut(
            QtGui.QKeySequence(QtCore.Qt.CTRL + QtCore.Qt.Key_M), self)
        self.toggleMenuBarShortcut.activated.connect(self.toggle_menu_bar)

    def apply_window_mode(self):
        # Keep desktop behavior by default, but fit exactly on small 800x480 screens.
        if self.fullscreen:
            self.showFullScreen()
            self.update_toolbar_utility_buttons()
            return

        screen = self.screen() or QtWidgets.QApplication.primaryScreen()
        if screen is None:
            self.resize(800, 480 if self.compact_ui else 600)
            return

        available = screen.availableGeometry()
        width = min(available.width(), 800)
        height = min(available.height(), 480 if self.compact_ui else 600)
        self.resize(width, height)
        self.update_toolbar_utility_buttons()

    def create_menus(self):
        menubar = self.menuBar()

        # Create file menu.
        self.fileMenu = menubar.addMenu("&File")
        self.fileMenu.addAction(self.clearRoastAct)
        self.fileMenu.addAction(self.newRoastAct)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.importRecipeAct)
        self.fileMenu.addAction(self.exportRecipeAct)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.saveRoastGraphAct)
        self.fileMenu.addAction(self.saveRoastGraphCSVAct)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.quitAppAct)

        # Create help menu.
        self.helpMenu = menubar.addMenu("&Help")
        self.helpMenu.addAction(self.openAboutWindow)

        if self.compact_ui:
            # Reserve vertical space on 480px displays; user can re-enable via MENU button.
            menubar.setVisible(False)

    def create_toolbar(self):
        # Create toolbar.
        self.mainToolBar = self.addToolBar('mainToolBar')
        self.mainToolBar.setMovable(False)
        self.mainToolBar.setFloatable(False)
        if self.compact_ui:
            self.mainToolBar.setIconSize(QtCore.QSize(16, 16))

        # Add logo.
        self.logo = QtWidgets.QLabel("openroast")
        self.logo.setObjectName("logo")
        self.mainToolBar.addWidget(self.logo)

        # Add roasting tab button.
        self.roastTabButton = QtWidgets.QPushButton("ROAST", self)
        self.roastTabButton.setObjectName("toolbar")
        self.roastTabButton.clicked.connect(self.select_roast_tab)
        self.mainToolBar.addWidget(self.roastTabButton)

        # Add recipes tab button.
        self.recipesTabButton = QtWidgets.QPushButton("RECIPES", self)
        self.recipesTabButton.setObjectName("toolbar")
        self.recipesTabButton.clicked.connect(self.select_recipes_tab)
        self.mainToolBar.addWidget(self.recipesTabButton)

        # Add spacer to set login button on the right.
        self.spacer = QtWidgets.QWidget()
        self.spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.mainToolBar.addWidget(self.spacer)

        self.heaterDebugLabel = QtWidgets.QLabel("Heater: 0%")
        self.heaterDebugLabel.setObjectName("heaterDebugLabel")
        self.mainToolBar.addWidget(self.heaterDebugLabel)

        self.heaterDebugLed = QtWidgets.QLabel("")
        self.heaterDebugLed.setObjectName("heaterDebugLed")
        self.heaterDebugLed.setFixedSize(12, 12)
        self.mainToolBar.addWidget(self.heaterDebugLed)

        # Always-available touchscreen controls for kiosk-like setups.
        self.menuToggleButton = QtWidgets.QPushButton("MENU", self)
        self.menuToggleButton.setObjectName("toolbarUtility")
        self.menuToggleButton.clicked.connect(self.toggle_menu_bar)
        self.mainToolBar.addWidget(self.menuToggleButton)

        self.fullscreenToggleButton = QtWidgets.QPushButton("FULL", self)
        self.fullscreenToggleButton.setObjectName("toolbarUtility")
        self.fullscreenToggleButton.clicked.connect(self.toggle_fullscreen)
        self.mainToolBar.addWidget(self.fullscreenToggleButton)

        self.quitTouchButton = QtWidgets.QPushButton("QUIT", self)
        self.quitTouchButton.setObjectName("toolbarUtility")
        self.quitTouchButton.clicked.connect(self.close)
        self.mainToolBar.addWidget(self.quitTouchButton)

        # Add buttons to array to be disabled on selection.
        self.tabButtons = [self.roastTabButton,
                           self.recipesTabButton]

        self.update_toolbar_utility_buttons()

    def create_tabs(self, roaster, recipes):
        self.tabs = QtWidgets.QStackedWidget()

        # Create widgets to add to tabs.
        self.roast = roasttab.RoastTab(
            roaster, recipes, compact_ui=self.compact_ui)
        self.recipes = recipestab.RecipesTab(
            roastTabObject=self.roast,
            MainWindowObject=self,
            recipes_object=self.recipes)

        # Add widgets to tabs.
        self.tabs.insertWidget(0, self.roast)
        self.tabs.insertWidget(1, self.recipes)

        # Set the tabs as the central widget.
        self.setCentralWidget(self.tabs)

        # Set the roast button disabled.
        self.roastTabButton.setEnabled(False)

    def select_roast_tab(self):
        self.tabs.setCurrentIndex(0)
        self.change_blocked_button(0)

    def select_recipes_tab(self):
        self.tabs.setCurrentIndex(1)
        self.change_blocked_button(1)

    def change_blocked_button(self, index):
        # Set all buttons enabled.
        for button in self.tabButtons:
            button.setEnabled(True)

        # Set selected button disabled.
        self.tabButtons[index].setEnabled(False)

    def import_recipe_file(self):
        try:
            recipeFile = QtWidgets.QFileDialog.getOpenFileName(self, 'Select Recipe',
                os.path.expanduser('~/'), 'Recipes (*.json);;All Files (*)')
            shutil.copy2(recipeFile[0],
                os.path.expanduser('~/Documents/Openroast/Recipes/My Recipes/'))
        except FileNotFoundError:
            # Occurs if file browser is canceled
            pass
        else:
            pass

    def export_recipe_file(self):
        try:
            recipeFile = QtWidgets.QFileDialog.getSaveFileName(self, 'Export Recipe',
                os.path.expanduser('~/'), 'Recipes (*.json);;All Files (*)')
            jsonObject = json.dumps(
                self.recipes.currentlySelectedRecipe, indent=4)

            with open(recipeFile[0], 'w', encoding='utf-8') as file:
                file.write(jsonObject)
        except FileNotFoundError:
            # Occurs if file browser is canceled
            pass
        else:
            pass

    def open_about_window(self):
        self.aboutWindow = aboutwindow.About(parent=self)
        dialog_exec = getattr(self.aboutWindow, "exec", self.aboutWindow.exec_)
        dialog_exec()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.fullscreen = False
            self.showNormal()
            self.apply_window_mode()
        else:
            self.fullscreen = True
            self.showFullScreen()
            self.update_toolbar_utility_buttons()

    def exit_fullscreen(self):
        if self.isFullScreen():
            self.fullscreen = False
            self.showNormal()
            self.apply_window_mode()

    def toggle_menu_bar(self):
        self.menuBar().setVisible(not self.menuBar().isVisible())
        self.update_toolbar_utility_buttons()

    def _read_heater_debug_state(self):
        heater_level = getattr(self.roaster, "heater_level", None)
        heater_output = getattr(self.roaster, "heater_output", None)

        if heater_level is None:
            heat_setting = int(getattr(self.roaster, "heat_setting", 0))
            heater_level = int(round((max(0, min(3, heat_setting)) * 100.0) / 3.0))
        heater_level = int(max(0, min(100, heater_level)))

        if heater_output is None:
            heater_output = heater_level > 0

        return heater_level, bool(heater_output)

    def on_heater_output_changed(self, heater_on):
        self.heaterOutputChanged.emit(bool(heater_on))

    def on_heater_level_changed(self, heater_level):
        self.heaterLevelChanged.emit(int(heater_level))

    def update_heater_debug_indicators(self):
        if not hasattr(self, "heaterDebugLabel") or not hasattr(self, "heaterDebugLed"):
            return

        heater_level, heater_on = self._read_heater_debug_state()
        self._apply_heater_level_text(heater_level)
        self._apply_heater_led_state(heater_on)

    def _apply_heater_level_text(self, heater_level):
        heater_level = int(max(0, min(100, int(heater_level))))
        if self._heaterLevel == heater_level:
            return
        self._heaterLevel = heater_level
        self.heaterDebugLabel.setText(f"Heater: {heater_level:3d}%")

    def _apply_heater_led_state(self, heater_on):
        heater_on = bool(heater_on)
        if getattr(self, "_heaterLedOn", None) is heater_on:
            return
        self._heaterLedOn = heater_on

        if heater_on:
            self.heaterDebugLed.setStyleSheet(
                "background-color: #8ab71b; border: 1px solid #649100; border-radius: 6px;"
            )
        else:
            self.heaterDebugLed.setStyleSheet(
                "background-color: #2e3138; border: 1px solid #6d7686; border-radius: 6px;"
            )

    def update_toolbar_utility_buttons(self):
        if hasattr(self, 'menuToggleButton'):
            self.menuToggleButton.setText(
                "MENU ON" if self.menuBar().isVisible() else "MENU OFF")
        if hasattr(self, 'fullscreenToggleButton'):
            self.fullscreenToggleButton.setText(
                "WINDOW" if self.isFullScreen() else "FULL")
        self.update_heater_debug_indicators()

    def closeEvent(self, event):
        self.roaster.disconnect()
