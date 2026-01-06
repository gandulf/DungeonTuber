from os import PathLike

from PySide6.QtCore import Signal, QSize
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QWidget, QFrame

from components.VisualizerWidget import VisualizerWidget
from config.settings import settings, SettingKeys


class Visualizer:
    fake_visualizer = None
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

        if (self.fake_visualizer is not None):
            if self.last_playing is not None:
                self.fake_visualizer.set_state(self.last_playing, self.last_value)
            if self.last_position is not None:
                self.fake_visualizer.set_position(self.last_position)
            if self.last_track is not None:
                self.fake_visualizer.load_mp3(self.last_track)

        return result

    def setup(self):
        vis = settings.value(SettingKeys.VISUALIZER, "FAKE", type=str)

        self.fake_visualizer = None
        self.video_frame = None
        self.visualizer = None

        if vis == "VLC":
            self.video_frame = VisualizerFrame()
            self.engine.attach_video_frame(self.video_frame)
            return self.video_frame
        elif vis == "FAKE":
            self.fake_visualizer = VisualizerWidget()
            return self.fake_visualizer
        else:
            self.visualizer = QWidget()
            return self.visualizer

    def set_state(self, playing, value):
        self.last_playing = playing
        self.last_value = value
        if self.fake_visualizer is not None:
            self.fake_visualizer.set_state(playing, value)

    def set_position(self, pos: int):
        self.last_position = pos
        if self.fake_visualizer is not None:
            self.fake_visualizer.set_position(pos)

    def load_mp3(self, track_path: str | PathLike[str]):
        self.last_track = track_path
        if self.fake_visualizer is not None:
            self.fake_visualizer.load_mp3(track_path)


class VisualizerFrame(QFrame):
    resized = Signal(QSize)

    def __init__(self, parent=None):
        super(VisualizerFrame, self).__init__(parent)
        self.setAutoFillBackground(True)

    def resizeEvent(self, event: QResizeEvent):
        self.resized.emit(event.size())
        super().resizeEvent(event)
