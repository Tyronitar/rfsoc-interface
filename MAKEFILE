UI_CC := poetry run pyside6-uic
UI_RCC := poetry run pyside6-rcc
UI_FILE_DIR := ui_resources
UI_PYTHON_DIR := rfsocinterface/ui

# All of the file stems in the ui_resources directory
ui_elements := $(patsubst $(UI_FILE_DIR)/%.ui,%, $(wildcard $(UI_FILE_DIR)/*.ui))
resources:= $(patsubst $(UI_FILE_DIR)/%.qrc,%, $(wildcard $(UI_FILE_DIR)/*.qrc))

all: uic rcc

# Compile all of the ui elements
uic: $(ui_elements)

rcc: $(resources)

# Create a separate rule for each individual element
$(ui_elements): %:
	$(UI_CC) $(UI_FILE_DIR)/$@.ui -o $(UI_PYTHON_DIR)/$@_ui.py --from-imports


$(resources): %:
	$(UI_RCC) $(UI_FILE_DIR)/$@.qrc -o $(UI_PYTHON_DIR)/$@_rc.py