import random
import logging
from os import PathLike

from PySide6.QtCore import Signal, QSize, QTimer
from PySide6.QtGui import QResizeEvent, QLinearGradient, QColor, QPainter, QPaintEvent, QBrush
from PySide6.QtWidgets import QWidget, QFrame

from config.settings import AppSettings, SettingKeys

logger = logging.getLogger("main")

class Visualizer:
    visualizer_widget = None
    video_frame = None
    visualizer = None

    last_playing = None
    last_value = None
    last_track = None
    last_position = None

    def __init__(self, engine):
        self.engine = engine

    def refresh(self):
        # vis = settings.value(SettingKeys.VISUALIZER, "FAKE", type=str)
        result = self.setup()

        if self.visualizer_widget is not None:
            if self.last_playing is not None:
                self.visualizer_widget.set_state(self.last_playing, self.last_value)
            if self.last_position is not None:
                self.visualizer_widget.set_position(self.last_position)
            if self.last_track is not None:
                self.visualizer_widget.load_mp3(self.last_track)

        return result

    def setup(self):
        vis = AppSettings.value(SettingKeys.VISUALIZER, "FAKE", type=str)

        self.visualizer_widget = None
        self.video_frame = None
        self.visualizer = None

        if vis == "VLC":
            self.video_frame = VisualizerFrame()
            self.engine.attach_video_frame(self.video_frame)
            return self.video_frame
        elif vis == "FAKE":
            self.visualizer_widget = FakeVisualizerWidget()
            return self.visualizer_widget
        else:
            self.visualizer = QWidget()
            return self.visualizer

    def set_state(self, playing, value):
        self.last_playing = playing
        self.last_value = value
        if self.visualizer_widget is not None:
            self.visualizer_widget.set_state(playing, value)

    def set_position(self, pos: int):
        self.last_position = pos
        if self.visualizer_widget is not None:
            self.visualizer_widget.set_position(pos)

    def load_mp3(self, track_path: str | PathLike[str]):
        self.last_track = track_path
        if self.visualizer_widget is not None:
            self.visualizer_widget.load_mp3(track_path)


class VisualizerFrame(QFrame):
    resized = Signal(QSize)

    def __init__(self, parent=None):
        super(VisualizerFrame, self).__init__(parent)
        self.setAutoFillBackground(True)

    def resizeEvent(self, event: QResizeEvent):
        self.resized.emit(event.size())
        super().resizeEvent(event)


_green = QColor("#5CB338")
_yellow = QColor("#ECE852")
_orange = QColor("#FFC145")
_red = QColor("#FB4141")

class FakeVisualizerWidget(QWidget):

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

    def load_mp3(self, file_name):
        # not needed for fake one
        logger.debug("File {0} loaded for visualizer", file_name)
        return

    def set_position(self, position_0_1000):
        # not needed for fake one
        logger.debug("Set position to {0} promille", position_0_1000)
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

    def paintEvent(self, event: QPaintEvent):
        content_rect = event.rect()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width() - self.contentsMargins().left() - self.contentsMargins().right()
        h = self.height() - self.contentsMargins().top() - self.contentsMargins().bottom()

        base_color = QColor(self.palette().base().color())
        base_color.setAlpha(100)

        painter.fillRect(content_rect, base_color)

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
