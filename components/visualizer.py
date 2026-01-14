import random
import logging
from os import PathLike

from PySide6.QtCore import Signal, QSize, QTimer, QObject
from PySide6.QtGui import QResizeEvent, QLinearGradient, QColor, QPainter, QPaintEvent, QBrush
from PySide6.QtWidgets import QWidget, QFrame

from config.settings import AppSettings, SettingKeys

logger = logging.getLogger("main")

_green = QColor("#5CB338")
_yellow = QColor("#ECE852")
_orange = QColor("#FFC145")
_red = QColor("#FB4141")

class Visualizer:

    video_frame = None
    visualizer = None

    last_playing = None
    last_value = None
    last_track = None
    last_position = None

    playing = False

    def __init__(self, engine=None):
        self.engine = engine
        self.playing = False

    @classmethod
    def get_visualizer(cls, engine, visualizer=None):
        vis = AppSettings.value(SettingKeys.VISUALIZER, "FAKE", type=str)
        _visualizer = None
        if vis == "VLC":
            _visualizer = VisualizerFrame(engine)
        elif vis == "FAKE":
            _visualizer= FakeVisualizerWidget(engine)
        else:
            _visualizer= EmptyVisualizerWidget(engine)

        if visualizer is not None:
            if visualizer.last_playing is not None:
                _visualizer.set_state(visualizer.last_playing, visualizer.last_value)
            if visualizer.last_position is not None:
                _visualizer.set_position(visualizer.last_position)
            if visualizer.last_track is not None:
                _visualizer.load_mp3(visualizer.last_track)
        return _visualizer

    def set_state(self, playing, value):
        self.last_playing = playing
        self.playing = playing
        self.last_value = value

    def set_position(self, position_0_1000: int):
        logger.debug("Set position to {0} promille", position_0_1000)
        self.last_position = position_0_1000

    def load_mp3(self, track_path: str | PathLike[str]):
        logger.debug("File {0} loaded for visualizer", track_path)
        self.last_track = track_path

class VisualizerFrame(QFrame, Visualizer):
    resized = Signal(QSize)

    def __init__(self, engine=None):
        super().__init__(engine =engine)
        self.setAutoFillBackground(True)
        self.engine.attach_video_frame(self)

    def resizeEvent(self, event: QResizeEvent):
        self.resized.emit(event.size())
        super().resizeEvent(event)


class EmptyVisualizerWidget(QWidget, Visualizer):
    def __init__(self, engine=None):
        super().__init__(engine = engine)

class FakeVisualizerWidget(QWidget, Visualizer):

    def __init__(self, engine):
        super().__init__(engine = engine)
        self.setMinimumHeight(40)
        self.setContentsMargins(4, 4, 4, 4)
        self.sleeping = True
        self.amplitude = 0
        self.bars = 30
        self.values = [0.0] * self.bars

        self.hop_length_secs = 1 / 30
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_fake_visualization)
        self.timer.start(int(self.hop_length_secs * 1000))

    def set_state(self, is_playing, volume):
        super().set_state(is_playing, volume)
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
