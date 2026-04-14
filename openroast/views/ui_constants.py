"""Centralized UI constants shared across Openroast views."""


class SharedWindow:
    MAIN_WINDOW_MIN_WIDTH = 800
    MAIN_WINDOW_MIN_HEIGHT_COMPACT = 480
    MAIN_WINDOW_MIN_HEIGHT_DEFAULT = 600
    MAIN_WINDOW_RESIZE_WIDTH_DEFAULT = 980
    MAIN_WINDOW_RESIZE_HEIGHT_DEFAULT = 680


class SharedTabStyle:
    # Style metrics (not palette values).
    TAB_PADDING_V = 6
    TAB_PADDING_H = 12


class SharedColors:
    # Core text/surface tokens.
    FOREGROUND_TEXT = "#ffffff"
    FOREGROUND_TEXT_MUTED = "#cfd6e0"
    SURFACE_PANEL = "#23252a"
    SURFACE_TAB_PANE = "#444952"
    SURFACE_TAB_INACTIVE = "#2e3138"

    # Borders/accents.
    BORDER_PANEL = "#23252a"
    BORDER_NEUTRAL = "#6d7686"
    ACCENT_PRIMARY = "#8ab71b"
    ACCENT_PRIMARY_BORDER = "#649100"


class SharedButtons:
    CORNER_BUTTON_HEIGHT = 30


class SharedLayout:
    ROOT_MARGIN = 6
    ROOT_SPACING = 6
    PAGE_MARGIN = 4
    PAGE_SPACING = 8
    FORM_H_SPACING = 6
    FORM_V_SPACING = 4


class SharedText:
    ACTION_CLOSE = "CLOSE"
    ACTION_SAVE = "SAVE"
    ACTION_SAVE_AS = "SAVE AS"
    ACTION_CANCEL = "Cancel"
    ACTION_APPLY = "Apply"


class DialogText:
    # Shared button labels for question dialogs.
    YES = "Yes"
    NO = "No"

    # Roast tab confirmations.
    ROAST_RESET_TITLE = "Reset roast"
    ROAST_RESET_STATE_MESSAGE = "Reset the current roast and recipe state?"
    ROAST_RESET_BEGINNING_MESSAGE = "Reset the current roast to the beginning?"
    ROAST_STOP_TITLE = "Stop roast"
    ROAST_STOP_MESSAGE = "Stop the current roast now?"

    # Preferences tab confirmations.
    AUTOTUNE_RUN_TITLE = "Run PID autotune"
    AUTOTUNE_RUN_MESSAGE = (
        "Autotune applies a heating step test and may take up to about a minute. Continue?"
    )
    SAFETY_CUTOFF_DISABLE_TITLE = "Disable safety cutoff?"
    SAFETY_CUTOFF_DISABLE_MESSAGE = (
        "Disabling over-temperature cutoff can damage equipment and increase fire risk. Continue?"
    )
    REVERT_EXPERT_TITLE = "Revert expert changes"
    REVERT_EXPERT_MESSAGE = "Revert unsaved expert options to last saved values?"
    REVERT_USER_TITLE = "Revert user changes"
    REVERT_USER_MESSAGE = "Revert unsaved user preferences to last saved values?"
    EXPERT_WARNING_TITLE = "Expert options warning"
    EXPERT_WARNING_MESSAGE = (
        "These parameters affect control and safety behavior. "
        "Incorrect values can cause unstable heating or unsafe operation. "
        "Only change them if you understand the risks. Continue?"
    )
    RESTORE_EXPERT_TITLE = "Restore expert defaults"
    RESTORE_EXPERT_MESSAGE = "Reset all expert options to their defaults?"
    RESTORE_USER_TITLE = "Restore user defaults"
    RESTORE_USER_MESSAGE = "Reset all user preferences to their defaults?"


class RoastTabUI:
    NON_COMPACT_PROGRESS_ROW_MIN_HEIGHT = 34
    COMPACT_CONTENTS_MARGINS = (4, 2, 4, 2)
    COMPACT_HORIZONTAL_SPACING = 8
    COMPACT_VERTICAL_SPACING = 4

    BUTTON_ROAST = "ROAST"
    BUTTON_COOL = "COOL"
    BUTTON_STOP = "STOP"
    BUTTON_RESET = "RESET"

    LABEL_TARGET_TEMP = "TARGET TEMP"
    LABEL_SECTION_DURATION = "SECTION DURATION"
    LABEL_FAN_SPEED = "FAN SPEED"
    LABEL_CURRENT_TEMP = "CURRENT TEMP"
    LABEL_REMAINING_SECTION_DURATION = "REMAINING SECTION DURATION"
    LABEL_TOTAL_TIME = "TOTAL TIME"
    BUTTON_NEXT = "NEXT"
    BUTTON_NEXT_WIDTH = 72

    # Timeline/progress widget spacing and marker geometry.
    TIMELINE_MAX_LABELS = 6
    TIMELINE_COMPACT_SPACING = 1
    TIMELINE_DEFAULT_SPACING = 2
    TIMELINE_TICK_WIDTH = 1
    TIMELINE_TICK_HEIGHT = 10
    TIMELINE_LABEL_GAP = 3

    CONNECT_TEXT_PLEASE_CONNECT = "Please connect your roaster."
    CONNECT_TEXT_CONNECTING = "Found roaster, connecting. This could take >20 seconds "

    DIALOG_RESET_TITLE = DialogText.ROAST_RESET_TITLE
    DIALOG_RESET_STATE_MESSAGE = DialogText.ROAST_RESET_STATE_MESSAGE
    DIALOG_RESET_BEGINNING_MESSAGE = DialogText.ROAST_RESET_BEGINNING_MESSAGE
    DIALOG_STOP_TITLE = DialogText.ROAST_STOP_TITLE
    DIALOG_STOP_MESSAGE = DialogText.ROAST_STOP_MESSAGE

    FAULT_BANNER_TEXT = "\u26a0 Over-temperature safety cutoff"
    FAULT_RESET_BUTTON_TEXT = "RESET FAULT"
    FAULT_BANNER_STYLE = (
        "background-color: #b71c1c; color: #ffffff; padding: 4px 8px; "
        "font-weight: bold; border-radius: 3px;"
    )
    FAULT_RESET_BUTTON_STYLE = (
        "background-color: #d32f2f; color: #ffffff; padding: 2px 8px; "
        "font-weight: bold; border-radius: 3px;"
    )

    DIALOG_GRAPH_BOUNDS_TITLE = "Graph capacity notice"
    DIALOG_GRAPH_BOUNDS_MESSAGE = (
        "This recipe is {total_minutes:.1f} min long. At the current plot "
        "refresh rate, the graph can display up to {max_minutes:.1f} min of data.\n\n"
        "The roast will proceed normally, but the earliest ~{lost_seconds} s of "
        "graph data will be dropped once the buffer fills."
    )


class PreferencesUI:
    LEFT_COLUMN_MAX_WIDTH = 520
    RIGHT_COLUMN_MAX_WIDTH = 420
    ROOT_MARGIN = SharedLayout.ROOT_MARGIN
    ROOT_SPACING = SharedLayout.ROOT_SPACING
    PAGE_MARGIN = SharedLayout.PAGE_MARGIN
    CORNER_SPACING = 6

    TAB_TITLE_USER = "User preferences"
    TAB_TITLE_EXPERT = "Expert options"

    BUTTON_REVERT = "REVERT CHANGES"
    BUTTON_RESTORE_DEFAULTS = "RESTORE DEFAULTS"
    BUTTON_SAVE = SharedText.ACTION_SAVE
    BUTTON_AUTOTUNE = "AUTOTUNE"

    LABEL_CONFIG_PATH_TEMPLATE = "Config file: {path}"

    FORM_LABEL_DISPLAY_TEMPERATURE_UNIT = "Display temperature unit:"
    FORM_LABEL_DEFAULT_BACKEND = "Default backend:"
    FORM_LABEL_ENABLE_COMPACT_UI_DEFAULT = "Enable compact UI by default:"
    FORM_LABEL_START_FULLSCREEN = "Start in fullscreen:"
    FORM_LABEL_ENABLE_EXPERT_OPTIONS = "Enable expert options:"
    FORM_LABEL_UI_REFRESH_INTERVAL = "UI refresh interval:"
    FORM_LABEL_PLOT_Y_AXIS_HEADROOM = "Plot y-axis headroom:"
    FORM_LABEL_PLOT_Y_AXIS_STEP = "Plot y-axis step:"
    FORM_LABEL_SHOW_PLOT_GRID = "Show plot grid:"
    FORM_LABEL_PLOT_LINE_WIDTH = "Plot line width:"
    FORM_LABEL_CONFIRM_ON_STOP = "Confirm on STOP:"
    FORM_LABEL_CONFIRM_ON_RESET = "Confirm on RESET:"
    FORM_LABEL_PID_KP = "PID Kp:"
    FORM_LABEL_PID_KI = "PID Ki:"
    FORM_LABEL_PID_KD = "PID Kd:"
    FORM_LABEL_PWM_CYCLE_PERIOD = "PWM cycle period:"
    FORM_LABEL_CONTROL_SAMPLE_PERIOD = "Control sample period:"
    FORM_LABEL_MAX_SAFE_TEMPERATURE = "Max safe temperature:"
    FORM_LABEL_ENABLE_HEATER_CUTOFF = "Enable heater over-temp cutoff:"

    STATUS_UNSAVED_CHANGES = "Unsaved changes"
    STATUS_AUTOTUNE_UNAVAILABLE = "Autotune unavailable: no backend handle"
    STATUS_AUTOTUNE_CANCELED = "Autotune canceled"
    STATUS_AUTOTUNE_RUNNING = "Running autotune..."
    STATUS_AUTOTUNE_FAILED_TEMPLATE = "Autotune failed: {error}"
    STATUS_AUTOTUNE_COMPLETE_AND_SAVED = "Autotune complete and saved"
    STATUS_PREFERENCES_SAVED = "Preferences saved. Some changes apply on next start."

    # Object names used for unified numeric control styling.
    NUMERIC_EDITOR_OBJECT_NAME = "inlineValueEditor"
    NUMERIC_EDITOR_COMPACT_OBJECT_NAME = "inlineValueEditorCompact"
    NUMERIC_EDITOR_HEIGHT_DEFAULT = 26
    NUMERIC_EDITOR_HEIGHT_COMPACT = 24
    REFRESH_INTERVAL_STEP_SMALL_MS = 10
    REFRESH_INTERVAL_STEP_LARGE_MS = 100
    PID_STEP_SMALL = 0.005
    PID_STEP_LARGE = 0.1

    DIALOG_AUTOTUNE_TITLE = DialogText.AUTOTUNE_RUN_TITLE
    DIALOG_AUTOTUNE_MESSAGE = DialogText.AUTOTUNE_RUN_MESSAGE
    DIALOG_DISABLE_CUTOFF_TITLE = DialogText.SAFETY_CUTOFF_DISABLE_TITLE
    DIALOG_DISABLE_CUTOFF_MESSAGE = DialogText.SAFETY_CUTOFF_DISABLE_MESSAGE
    DIALOG_REVERT_EXPERT_TITLE = DialogText.REVERT_EXPERT_TITLE
    DIALOG_REVERT_EXPERT_MESSAGE = DialogText.REVERT_EXPERT_MESSAGE
    DIALOG_REVERT_USER_TITLE = DialogText.REVERT_USER_TITLE
    DIALOG_REVERT_USER_MESSAGE = DialogText.REVERT_USER_MESSAGE
    DIALOG_EXPERT_WARNING_TITLE = DialogText.EXPERT_WARNING_TITLE
    DIALOG_EXPERT_WARNING_MESSAGE = DialogText.EXPERT_WARNING_MESSAGE
    DIALOG_RESTORE_EXPERT_TITLE = DialogText.RESTORE_EXPERT_TITLE
    DIALOG_RESTORE_EXPERT_MESSAGE = DialogText.RESTORE_EXPERT_MESSAGE
    DIALOG_RESTORE_USER_TITLE = DialogText.RESTORE_USER_TITLE
    DIALOG_RESTORE_USER_MESSAGE = DialogText.RESTORE_USER_MESSAGE


class RecipeEditorUI:
    # Window sizing
    WINDOW_MIN_WIDTH = SharedWindow.MAIN_WINDOW_MIN_WIDTH
    WINDOW_MIN_HEIGHT_COMPACT = SharedWindow.MAIN_WINDOW_MIN_HEIGHT_COMPACT
    WINDOW_MIN_HEIGHT_DEFAULT = SharedWindow.MAIN_WINDOW_MIN_HEIGHT_DEFAULT
    WINDOW_RESIZE_WIDTH_DEFAULT = SharedWindow.MAIN_WINDOW_RESIZE_WIDTH_DEFAULT
    WINDOW_RESIZE_HEIGHT_DEFAULT = SharedWindow.MAIN_WINDOW_RESIZE_HEIGHT_DEFAULT
    ROOT_MARGIN = SharedLayout.ROOT_MARGIN
    ROOT_SPACING = SharedLayout.ROOT_SPACING
    PAGE_MARGIN = SharedLayout.PAGE_MARGIN
    PAGE_SPACING = SharedLayout.PAGE_SPACING
    FORM_H_SPACING = SharedLayout.FORM_H_SPACING
    FORM_V_SPACING = SharedLayout.FORM_V_SPACING

    # Steps table geometry
    COLUMN_WIDTH_TEMP_COMPACT = 42
    COLUMN_WIDTH_TEMP_DEFAULT = 68
    COLUMN_WIDTH_FAN = 34
    COLUMN_WIDTH_DURATION_COMPACT = 64
    COLUMN_WIDTH_DURATION_DEFAULT = 72
    COLUMN_WIDTH_MODIFY_COMPACT = 72
    COLUMN_WIDTH_MODIFY_DEFAULT = 136
    TABLE_MIN_EXTRA_WIDTH = 14
    TABLE_ROW_HEIGHT_COMPACT = 30

    # In-cell editor widths
    TEMP_EDITOR_WIDTH_COMPACT = 36
    TEMP_EDITOR_WIDTH_DEFAULT = 60
    FAN_EDITOR_WIDTH_COMPACT = 26
    FAN_EDITOR_WIDTH_DEFAULT = 32
    TIME_EDITOR_WIDTH_COMPACT = 58
    TIME_EDITOR_WIDTH_DEFAULT = 64

    # Compact touch duration picker increments and limits
    DURATION_STEP_SMALL_S = 5
    DURATION_STEP_LARGE_S = 30
    DURATION_MAX_S = 59 * 60 + 59

    # Short cooling label to fit narrow temperature column
    COOLING_LABEL = "Cool"

    # Tab styling
    TAB_WIDGET_OBJECT_NAME = "recipeEditorTabs"
    TAB_PAGE_OBJECT_NAME_INFO = "recipeInfoPage"
    TAB_PAGE_OBJECT_NAME_PROFILE = "heatingProfilePage"
    TAB_TITLE_INFO = "Recipe info"
    TAB_TITLE_PROFILE = "Heating profile"
    WINDOW_TITLE = "Openroast"

    FORM_LABEL_RECIPE_NAME = "Recipe Name:"
    FORM_LABEL_CREATED_BY = "Created by:"
    FORM_LABEL_ROAST_TYPE = "Roast Type:"
    FORM_LABEL_BEAN_REGION = "Bean Region:"
    FORM_LABEL_BEAN_COUNTRY = "Bean Country:"
    FORM_LABEL_BEAN_LINK = "Bean Link:"
    FORM_LABEL_BEAN_STORE_NAME = "Bean Store Name:"
    FORM_LABEL_TEMPERATURE_UNIT = "Temperature unit:"
    FORM_LABEL_DESCRIPTION = "Description:"

    SECTION_LABEL_HEATING_CURVE = "Heating curve:"
    SECTION_LABEL_LOADING_CURVE = "Loading curve..."

    TABLE_HEADER_TEMPERATURE_PREFIX = "T"
    TABLE_HEADER_FAN = "Fan"
    TABLE_HEADER_DURATION = "Duration"
    TABLE_HEADER_MODIFY = "Modify"

    PLOT_AXIS_TIME = "Time"
    PLOT_AXIS_TEMPERATURE = "Temperature"

    COLOR_TAB_PANE_BG = SharedColors.SURFACE_TAB_PANE
    COLOR_TAB_PANE_BORDER = SharedColors.BORDER_PANEL
    COLOR_TAB_BG = SharedColors.SURFACE_TAB_INACTIVE
    COLOR_TAB_TEXT = SharedColors.FOREGROUND_TEXT_MUTED
    COLOR_TAB_SELECTED_TEXT = SharedColors.FOREGROUND_TEXT
    TAB_PADDING_V = SharedTabStyle.TAB_PADDING_V
    TAB_PADDING_H = SharedTabStyle.TAB_PADDING_H

    # Corner action button sizing
    CORNER_BUTTON_HEIGHT = SharedButtons.CORNER_BUTTON_HEIGHT
    CORNER_BUTTON_WIDTH_CLOSE = 72
    CORNER_BUTTON_WIDTH_SAVE = 72
    CORNER_BUTTON_WIDTH_SAVE_AS = 92
    CORNER_BUTTON_TEXT_CLOSE = SharedText.ACTION_CLOSE
    CORNER_BUTTON_TEXT_SAVE = SharedText.ACTION_SAVE
    CORNER_BUTTON_TEXT_SAVE_AS = SharedText.ACTION_SAVE_AS

    # Curve panel minimum heights
    CURVE_MIN_HEIGHT_COMPACT = 220
    CURVE_MIN_HEIGHT_DEFAULT = 360
    PLOT_BG_COLOR = SharedColors.SURFACE_PANEL
    PLOT_LINE_COLOR = SharedColors.ACCENT_PRIMARY
    PLOT_LABEL_COLOR = SharedColors.FOREGROUND_TEXT

    # Compact touch temperature picker increments (display-unit steps)
    TEMP_PICKER_STEP_SMALL = 1
    TEMP_PICKER_STEP_LARGE = 5
    PICKER_DIALOG_WIDTH_COMPACT = 320
    PICKER_DIALOG_WIDTH_DEFAULT = 360
    PICKER_CANCEL_TEXT = SharedText.ACTION_CANCEL
    PICKER_APPLY_TEXT = SharedText.ACTION_APPLY
    PICKER_TEMPERATURE_TITLE = "Set Temperature"
    PICKER_DURATION_TITLE = "Set Duration"

    ALERT_MIN_STEPS_TITLE = "openroast"
    ALERT_MIN_STEPS_TEXT = "You must have at least one step!"

    FILE_DIALOG_SAVE_AS_TITLE = "Save Recipe As"
    FILE_DIALOG_SAVE_AS_FILTER = "Recipe Files (*.json);;All Files (*)"

    SPLITTER_LAYOUT_OVERHEAD = 36
    SPLITTER_MIN_PLOT_WIDTH = 240

    TAB_INDEX_INFO = 0
    TAB_INDEX_PROFILE = 1


class MainWindowUI:
    WINDOW_TITLE_TEMPLATE = "Openroast v{version}"
    LOGO_TEXT = "openroast"

    TAB_BUTTON_ROAST = "ROAST"
    TAB_BUTTON_RECIPES = "RECIPES"
    TAB_BUTTON_PREFERENCES = "PREFERENCES"

    TOOLBAR_MENU_TOGGLE = "MENU"
    TOOLBAR_FULLSCREEN_TOGGLE = "FULL"
    TOOLBAR_QUIT = "QUIT"

    TOOLBAR_MENU_ON = "MENU ON"
    TOOLBAR_MENU_OFF = "MENU OFF"
    TOOLBAR_WINDOW = "WINDOW"

    HEATER_LABEL_TEMPLATE = "Heater: {level:3d}%"

    ACTION_CLEAR = "&Clear"
    ACTION_ROAST_AGAIN = "&Roast Again"
    ACTION_IMPORT_RECIPE = "&Import Recipe"
    ACTION_EXPORT_RECIPE = "&Export Recipe"
    ACTION_SAVE_ROAST_GRAPH = "&Save Roast Graph"
    ACTION_SAVE_ROAST_GRAPH_CSV = "&Save Roast Graph CSV"
    ACTION_ABOUT = "&About"
    ACTION_QUIT = "&Quit"

    STATUS_CLEAR_ROAST = "Clear the roast window"
    STATUS_ROAST_AGAIN = "Roast recipe again"
    STATUS_IMPORT_RECIPE = "Import a recipe file"
    STATUS_EXPORT_RECIPE = "Export a recipe file"
    STATUS_SAVE_ROAST_GRAPH = "Save an image of the roast graph"
    STATUS_SAVE_ROAST_GRAPH_CSV = "Save the roast graph as a csv"
    STATUS_ABOUT = "About openroast"
    STATUS_QUIT = "Quit Openroast"

    MENU_FILE = "&File"
    MENU_HELP = "&Help"

    FILE_DIALOG_SELECT_RECIPE_TITLE = "Select Recipe"
    FILE_DIALOG_EXPORT_RECIPE_TITLE = "Export Recipe"
    FILE_DIALOG_RECIPE_FILTER = "Recipes (*.json);;All Files (*)"


class RecipesTabUI:
    BUTTON_NEW_RECIPE = "NEW RECIPE"
    BUTTON_ROAST_NOW = "ROAST NOW"
    BUTTON_EDIT = "EDIT"
    BUTTON_PURCHASE_BEANS = "PURCHASE BEANS"

    LABEL_RECIPE_NAME = "Recipe Name"
    LABEL_CREATED_BY = "Created by "
    LABEL_TOTAL_TIME = "Total Time: "
    LABEL_ROAST_TYPE = "Roast Type: "
    LABEL_BEAN_REGION = "Bean Region: "
    LABEL_BEAN_COUNTRY = "Bean Country: "

    TABLE_HEADER_TEMPERATURE_PREFIX = "T"
    TABLE_HEADER_FAN = "FAN"
    TABLE_HEADER_DURATION = "DURATION"
    TABLE_CELL_COOLING = "Cooling"
    TOTAL_TIME_SUFFIX = " minutes"


class AboutUI:
    WINDOW_TITLE = "About Openroast"
    WINDOW_MIN_WIDTH = 600
    WINDOW_MIN_HEIGHT = 400

    LABEL_APP_NAME = "openroast"
    LABEL_LICENSE = "License"
    LABEL_AUTHORS = "Authors"
    LABEL_VERSION_TEMPLATE = "Version {version}"

    AUTHOR_1_NAME = "Mark Spicer"
    AUTHOR_1_URL = "https://markspicer.me"
    AUTHOR_2_NAME = "Caleb Coffie"
    AUTHOR_2_URL = "https://CalebCoffie.com"


class GraphUI:
    AXIS_BOTTOM_TIME = "TIME"
    AXIS_LEFT_TEMPERATURE_TEMPLATE = "TEMPERATURE ({unit})"
    SAVE_GRAPH_TITLE = "Save Roast Graph"
    SAVE_GRAPH_FILTER = "Graph (*.png);;All Files (*)"
    SAVE_GRAPH_CSV_TITLE = "Save Roast Graph CSV"
    SAVE_GRAPH_CSV_FILTER = "CSV (*.csv);;All Files (*)"
    CSV_HEADER = "Seconds,Temperature\n"


