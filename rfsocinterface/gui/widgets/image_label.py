"""Special label for displyig images."""

from typing import override

import numpy.typing as npt
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy


class ImageLabel(QLabel):
    """Label for storingan image and rpeserving aspect ratio."""

    def __init__(self, parent=None):
        """Initialize an ImageLabel."""
        super().__init__(parent)

        self._pixmap = None

        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Ignored,
        )
        self.setMinimumSize(250, 125)

    def set_image(self, image: npt.NDArray):
        """Set the image of the label."""
        # Load the QImage
        h, w, _ = image.shape
        bytes_per_line = image.strides[0]
        image = QImage(
            image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888
        ).copy()
        if not image.isNull():
            self.setPixmap(QPixmap.fromImage(image))

    @override
    def setPixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self._update_pixmap()

    @override
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_pixmap()

    def _update_pixmap(self):
        """Update the pixmap, scaling as needed."""
        if self._pixmap is None:
            return

        scaled = self._pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )

        super().setPixmap(scaled)
