import qtawesome as qta
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QLineEdit, QSizePolicy

ERROR_ICON_CODE = 'fa5s.exclamation-circle'

class IconLabel(QWidget):

    IconSize = QSize(16, 16)
    HorizontalSpacing = 2

    def __init__(self, qta_id: str, text: str, color: str='black', final_stretch=True, parent: QWidget | None=None):
        super().__init__(parent=parent)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.icon = QLabel()
        self.setIcon(qta_id, color=color)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self.icon)
        layout.addSpacing(self.HorizontalSpacing)
        self.label = QLabel(text)
        self.label.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
        self.label.setWordWrap(True)
        self.setColor(color)
        layout.addWidget(self.label)

        if final_stretch:
            layout.addStretch()
    
    def setIcon(self, icon_id: str, color: str='black'):
        print(color)
        self.icon.setPixmap(qta.icon(icon_id, color=color).pixmap(self.IconSize))
    
    def setColor(self, color:str):
        self.label.setStyleSheet(f'color: {color};')
    
    def setText(self, text: str):
        self.label.setText(text)

def verify_lineEdit(
    source: QLineEdit,
    error_label: IconLabel,
    toggle_enabled: list[QWidget]=[],
) -> bool:
    if not source.hasAcceptableInput():
        # Highlight in red
        source.setStyleSheet(
            """QLineEdit {border-style: solid; border: 2px solid red; color: red;
            border-radius: 5px; 
            background-color: #fff1f1;};
            """
        )
        for widget in toggle_enabled:
            widget.setEnabled(False)

        # Show the error_label 
        error_label.setVisible(True)
        return False
    else:  # Value is valid
        # Remove the error label since the value is valid
        error_label.setVisible(False)

        source.setStyleSheet('')
        for widget in toggle_enabled:
            widget.setEnabled(True)
        
        return True

