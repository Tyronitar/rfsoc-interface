import qtawesome as qta
from PySide6.QtCore import QSize, Qt, Signal, QCoreApplication
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QLineEdit, QSizePolicy

ERROR_ICON_CODE = 'fa5s.exclamation-circle'

class IconLabel(QWidget):

    IconSize = QSize(16, 16)
    HorizontalSpacing = 2

    def __init__(self, qta_id: str, text: str, color: str='black', final_stretch=True, wrap_text: bool=False, parent: QWidget | None=None):
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
        self.label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.label.setWordWrap(wrap_text)
        self.min_width = self.label.fontMetrics().horizontalAdvance(self.label.text())
        self.setColor(color)
        layout.addWidget(self.label)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        if final_stretch:
            layout.addStretch()
    
    def setIcon(self, icon_id: str, color: str='black'):
        self.icon.setPixmap(qta.icon(icon_id, color=color).pixmap(self.IconSize))
    
    def setColor(self, color:str):
        self.label.setStyleSheet(f'color: {color};')
    
    def setText(self, text: str):
        self.label.setText(text)
    

def verify_lineEdit(
    source: QLineEdit,
    error_label: IconLabel,
    toggle_enabled: list[QWidget]=[],
) -> tuple[bool, bool]:
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
        toggled = error_label.isHidden()
        error_label.setVisible(True)
        QCoreApplication.processEvents()
        return False, toggled
    else:  # Value is valid
        # Remove the error label since the value is valid
        toggled = error_label.isVisible()
        error_label.setVisible(False)
        QCoreApplication.processEvents()

        source.setStyleSheet('')
        for widget in toggle_enabled:
            widget.setEnabled(True)
        
        return True, toggled

