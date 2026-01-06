import random

from PySide6.QtCore import QTimer
from PySide6.QtGui import QPainter, QColor, QLinearGradient
from PySide6.QtWidgets import QWidget

_green = QColor("#5CB338")
_yellow = QColor("#ECE852")
_orange = QColor("#FFC145")
_red = QColor("#FB4141")

class VisualizerWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(40)
        self.setContentsMargins(4, 4, 4, 4)
        self.playing = False
        self.sleeping = True
        self.amplitude = 0
        self.bars = 30
        self.values = [0.0] * self.bars

        self.hop_length_secs = 1 / 30
        self.timer = QTimer(self)

        self.timer.timeout.connect(self.update_fake_visualization)
        self.timer.start(int(self.hop_length_secs * 1000))

    def load_mp3(self, filename):
        # not needed for fake one
        return

    def set_position(self, position_0_1000):
        # not needed for fake one
        return

    def set_state(self, is_playing, volume):
        self.playing = is_playing
        self.amplitude = volume / 100.0

    def update_fake_visualization(self):
        if self.playing:
            # Simulate spectrum data
            for i in range(self.bars):
                # Random noise smoothed by amplitude
                target = random.random() * self.amplitude
                # Simple decay/attack smoothing
                self.values[i] = (self.values[i] * 0.8) + (target * 0.2)
        else:
            # Decay to zero
            for i in range(self.bars):
                self.values[i] *= 0.85

        self.update()  # Trigger paintEvent

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width() - self.contentsMargins().left() - self.contentsMargins().right()
        h = self.height() - self.contentsMargins().top() - self.contentsMargins().bottom()

        base_color = QColor(self.palette().base().color())
        base_color.setAlpha(100)

        painter.fillRect(self.rect(), base_color)

        bar_width = w / self.bars

        # Gradient brush for a modern look
        gradient = QLinearGradient(0, h, 0, 0)
        gradient.setColorAt(0.0, _green)  # Green
        gradient.setColorAt(0.4, _yellow)  # yellow
        gradient.setColorAt(0.6, _orange)  # Orange
        gradient.setColorAt(1.0, _red)  # Red

        for i, val in enumerate(self.values):
            bar_h = max(1, int(val * h * 1.2))  # make the bars fill up more space by using factor 1.2
            x = self.contentsMargins().left() + i * bar_width
            y = self.contentsMargins().top() + h - bar_h

            painter.fillRect(int(x), int(y), int(bar_width - 2), int(bar_h), gradient)
