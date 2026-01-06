from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtWidgets import QStyle, QSlider


class QJumpSlider(QSlider):
    def __init__(self, parent=None):
        super(QJumpSlider, self).__init__(parent)

        # Animation
        self.setMouseTracking(True)
        self._glow_size = 0
        self.max_glow_size = 3.0

        # Setup Animation
        self.ani = QPropertyAnimation(self, b"glow_size")
        self.ani.setDuration(200)
        self.ani.setEasingCurve(QEasingCurve.Type.OutCubic)

    @Property(float)
    def glow_size(self):
        return self._glow_size

    @glow_size.setter
    def glow_size(self, value):
        self._glow_size = value
        self.update()  # Force repaint with new animation value

    def animate_glow(self, target):
        if self.ani.endValue() != target:
            self.ani.stop()
            self.ani.setEndValue(target)
            self.ani.start()

    def enterEvent(self, event):
        # self.animate_glow(self.max_glow_size /2)  # Subtle hover glow
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Only shrink if we aren't currently holding the mouse button down
        if not self.isSliderDown():
            self.animate_glow(0.0)
        super().leaveEvent(event)

    def _roundStep(self, a, stepSize):
        return round(float(a) / stepSize) * stepSize

    def mousePressEvent(self, event):
        # handle glow size
        # self.animate_glow(self.max_glow_size)  # Intense press glow
        # Jump to click position
        self.setSliderDown(True)
        if self.orientation() == Qt.Orientation.Vertical:
            value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.position().y(), self.height(),
                                                   not self.invertedAppearance())
        else:
            value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.position().x(), self.width(),
                                                   self.invertedAppearance())

        value = self._roundStep(value, self.singleStep())

        self.setValue(value)

    def mouseReleaseEvent(self, event):
        # handle glow size
        if not self.underMouse():
            self.animate_glow(0.0)
        #
        self.setSliderDown(False)

    def mouseMoveEvent(self, event):
        low = self.minimum()
        high = self.maximum()
        progress = (self.sliderPosition() - low) / (high - low) if high > low else 0
        progress_x = self.width() * progress

        if abs(progress_x - event.position().x()) < 6:
            self.animate_glow(self.max_glow_size)
        else:
            self.animate_glow(0)

        if self.isSliderDown():
            # Jump to pointer position while moving

            if self.orientation() == Qt.Orientation.Vertical:
                value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.position().y(),
                                                       self.height(), not self.invertedAppearance())
            else:
                value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.position().x(),
                                                       self.width(), self.invertedAppearance())

            value = self._roundStep(value, self.singleStep())
            self.setValue(value)
