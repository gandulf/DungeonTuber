import logging
import platform
import random
from os import PathLike

from PySide6.QtCore import Signal, QSize, QTimer, QPersistentModelIndex, Qt, QEvent
from PySide6.QtGui import QResizeEvent, QLinearGradient, QColor, QPainter, QPaintEvent, QFontMetrics, QIcon, QPalette, QAction
from PySide6.QtWidgets import QWidget, QFrame, QLabel, QSlider, QToolButton, QSizePolicy, QVBoxLayout, QHBoxLayout

from config.settings import AppSettings, SettingKeys
from logic.audioengine import AudioEngine, EngineState
from logic.mp3 import Mp3Entry
from config.theme import app_theme
from components.widgets import RepeatMode, RepeatButton, JumpSlider, VolumeSlider

logger = logging.getLogger(__file__)

_green = QColor("#5CB338")
_yellow = QColor("#ECE852")
_orange = QColor("#FFC145")
_red = QColor("#FB4141")

class Visualizer:

    video_frame = None
    visualizer = None

    last_state: EngineState = None
    last_value = None
    last_track = None
    last_position = None

    state: EngineState = EngineState.STOP

    def __init__(self, engine : AudioEngine=None):
        self.engine: AudioEngine = engine
        self.state = EngineState.STOP

    @classmethod
    def get_visualizer(cls, engine: AudioEngine, visualizer=None):
        vis = AppSettings.value(SettingKeys.VISUALIZER, "NONE", type=str)
        _visualizer = None
        if vis == "VLC":
            _visualizer = VlcVisualizerFrame(engine)
        elif vis == "FAKE":
            _visualizer= FakeVisualizerWidget(engine)
        else:
            _visualizer= EmptyVisualizerWidget(engine)

        if visualizer is not None:
            if visualizer.last_state is not None:
                _visualizer.set_state(visualizer.last_state, visualizer.last_value)
            if visualizer.last_position is not None:
                _visualizer.set_position(visualizer.last_position)
            if visualizer.last_track is not None:
                _visualizer.load_mp3(visualizer.last_track)
        return _visualizer

    def set_state(self, state: EngineState | None, value: int | None):
        if state is not None:
            self.last_state = state
            self.state = state
        if value is not None:
            self.last_value = value

    def set_position(self, position_0_1000: int):
        logger.debug("Set position to {0} promille", position_0_1000)
        self.last_position = position_0_1000

    def load_mp3(self, track_path: PathLike[str]):
        logger.debug("File {0} loaded for visualizer", track_path)
        self.last_track = track_path

class VlcVisualizerFrame(QFrame, Visualizer):
    resized = Signal(QSize)

    def __init__(self, engine: AudioEngine=None):
        super().__init__(engine=engine)
        self.setAutoFillBackground(True)
        self.attach_video_frame()

    def resizeEvent(self, event: QResizeEvent):
        self.resized.emit(event.size())
        super().resizeEvent(event)

    def attach_video_frame(self):
        self.resized.connect(self.engine.set_aspect_ratio)
        self.engine.set_aspect_ratio(self.size())

        # The media player has to be 'connected' to the QFrame (otherwise the
        # video would be displayed in it's own window). This is platform
        # specific, so we must give the ID of the QFrame (or similar object) to
        # vlc. Different platforms have different functions for this
        self.engine.attach_window(int(self.winId()))

class EmptyVisualizerWidget(QWidget, Visualizer):
    def __init__(self, engine=None):
        super().__init__(engine = engine)
        self.engine.attach_window(None)

class FakeVisualizerWidget(QWidget, Visualizer):

    def __init__(self, engine: AudioEngine):
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

        self.engine.attach_window(None)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ParentChange:
            if self.parent() is None:
                self.timer.stop()
            else:
                self.timer.start(int(self.hop_length_secs * 1000))

        # Always call the super class event to ensure normal behavior
        super().changeEvent(event)

    def set_state(self, state: EngineState | None, volume: int | None = None):
        super().set_state(state, volume)
        if volume is not None:
            self.amplitude = volume / 100.0

    def update_fake_visualization(self):
        if self.state == EngineState.PLAY:
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


class PlayerWidget(QWidget):
    icon_prev: QIcon = QIcon.fromTheme(QIcon.ThemeIcon.MediaSkipBackward)
    icon_next: QIcon = QIcon.fromTheme(QIcon.ThemeIcon.MediaSkipForward)
    icon_open: QIcon = QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen)

    volume_changed = Signal(int)
    track_changed = Signal(QPersistentModelIndex, Mp3Entry)
    repeat_mode_changed = Signal(RepeatMode)

    current_index = QPersistentModelIndex()
    current_data: Mp3Entry = None

    _update_progress_ticks: bool = True

    def __init__(self, parent=None):
        super().__init__(parent)

        self.player_layout = QVBoxLayout(self)
        self.player_layout.setObjectName("player_layout")
        self.player_layout.setSpacing(app_theme.spacing)

        self.engine = AudioEngine()
        self.engine.state_changed.connect(self.on_playback_state_changed)
        self.engine.position_changed.connect(self.update_progress)
        self.engine.track_finished.connect(self.on_track_finished)

        self.seeker_layout = QVBoxLayout()
        self.seeker_layout.setObjectName("seeker_layout")

        self.track_label = QLabel(_("No Track Selected"))
        self.track_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.track_label.setMinimumWidth(100)
        self.track_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.track_label.setObjectName("trackLabel")
        self.seeker_layout.addWidget(self.track_label)

        # --- Progress Bar and Time Labels ---
        self.progress_layout = QHBoxLayout()
        self.progress_layout.setObjectName("progress_layout")
        self.progress_layout.setSpacing(app_theme.spacing)
        self.time_label = QLabel("00:00")
        self.progress_slider = JumpSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.setMinimumWidth(100)
        self.duration_label = QLabel("00:00")
        self.progress_slider.setTickPosition(QSlider.TickPosition.TicksAbove)
        self.progress_slider.setTickInterval(50)
        self.progress_slider.sliderReleased.connect(self.seek_position)
        self.progress_slider.valueChanged.connect(self.jump_to_position)

        self.progress_layout.addWidget(self.time_label)
        self.progress_layout.addWidget(self.progress_slider)
        self.progress_layout.addWidget(self.duration_label)

        self.seeker_layout.addLayout(self.progress_layout)

        # --- End Progress Bar ---

        controls_widget = QWidget()
        self.controls_layout = QHBoxLayout(controls_widget)
        self.controls_layout.setSpacing(0)
        self.controls_layout.setContentsMargins(0,0,0,0)

        prev_action = QAction(self.icon_prev, _("Previous"), self)
        prev_action.setShortcut("Ctrl+B")
        prev_action.triggered.connect(self.prev_track)

        self.play_action = QAction(app_theme.create_play_pause_icon(), _("Play"), self)
        self.play_action.setShortcut("Ctrl+P")
        self.play_action.setCheckable(True)
        self.play_action.triggered.connect(self.toggle_play)

        next_action = QAction(self.icon_next, _("Next"), self)
        next_action.setShortcut("Ctrl+N")
        next_action.triggered.connect(self.next_track)

        self.btn_prev = QToolButton()
        self.btn_prev.setProperty("cssClass", "small")
        self.btn_prev.setDefaultAction(prev_action)
        self.btn_play = QToolButton()
        self.btn_play.setProperty("cssClass", "play")
        self.btn_play.setDefaultAction(self.play_action)
        self.btn_next = QToolButton()
        self.btn_next.setProperty("cssClass", "small")
        self.btn_next.setDefaultAction(next_action)

        self.btn_repeat = RepeatButton(AppSettings.value(SettingKeys.REPEAT_MODE, 0, type=int))
        self.btn_repeat.value_changed.connect(self.on_repeat_mode_changed)

        self.repeat_mode_changed = self.btn_repeat.value_changed

        self.slider_vol = VolumeSlider(AppSettings.value(SettingKeys.VOLUME, 70, type=int), shortcut="Ctrl+M")
        self.slider_vol.btn_volume.setProperty("cssClass", "small")
        self.slider_vol.slider_vol.setMinimumWidth(200)

        self.slider_vol.volume_changed.connect(self.adjust_volume)
        self.volume_changed = self.slider_vol.volume_changed

        self.controls_layout.addWidget(self.btn_play)
        self.controls_layout.addSpacing(app_theme.spacing)
        self.controls_layout.addWidget(self.btn_prev, alignment=Qt.AlignmentFlag.AlignBottom)
        self.controls_layout.addWidget(self.btn_next, alignment=Qt.AlignmentFlag.AlignBottom)
        self.controls_layout.addSpacing(app_theme.spacing)

        self.visualizer = Visualizer.get_visualizer(self.engine)
        if isinstance(self.visualizer, EmptyVisualizerWidget):
            self.controls_layout.addLayout(self.seeker_layout, 2)
        else:
            self.player_layout.insertLayout(0, self.seeker_layout)
            self.controls_layout.addWidget(self.visualizer, 2)

        self.controls_layout.addSpacing(app_theme.spacing)
        self.controls_layout.addLayout(self.slider_vol)
        self.controls_layout.addSpacing(app_theme.spacing)
        self.controls_layout.addWidget(self.btn_repeat)
        self.setBackgroundRole(QPalette.ColorRole.Midlight)
        self.setAutoFillBackground(True)

        self.player_layout.addWidget(controls_widget, 1)

        self.adjust_volume(self.slider_vol.volume)

    def refresh_visualizer(self):
        index = self.controls_layout.indexOf(self.visualizer)
        if index is None or index == -1:
            index = self.controls_layout.indexOf(self.seeker_layout)
            self.controls_layout.takeAt(index)
            self.seeker_layout.setParent(None)
        else:
            self.controls_layout.takeAt(index)
            self.visualizer.setParent(None)

        self.engine.init_vlc()
        self.visualizer = Visualizer.get_visualizer(self.engine, self.visualizer)
        if isinstance(self.visualizer, EmptyVisualizerWidget):
            self.seeker_layout.setParent(None)
            self.controls_layout.insertLayout(index, self.seeker_layout, 2)
        else:
            self.player_layout.insertLayout(0, self.seeker_layout)
            self.controls_layout.insertWidget(index, self.visualizer, 2)

    def changeEvent(self, event, /):
        if event.type() == QEvent.Type.ApplicationFontChange:
            self.player_layout.setSpacing(app_theme.spacing)
            self.progress_layout.setSpacing(app_theme.spacing)
            self.controls_layout.setSpacing(app_theme.spacing)

        if event.type() == QEvent.Type.PaletteChange:
            self._reload_icons()
            # for btn in [self.btn_prev, self.btn_play, self.btn_next, self.slider_vol.btn_volume, self.btn_repeat]:

    def _reload_icons(self):
        self.icon_prev = QIcon.fromTheme(QIcon.ThemeIcon.MediaSkipBackward)
        self.icon_next = QIcon.fromTheme(QIcon.ThemeIcon.MediaSkipForward)
        self.icon_open = QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen)

        for icon in [self.icon_prev, self.icon_next, self.icon_open]:
            icon.setFallbackThemeName(app_theme.theme())

        self.play_action.setIcon(app_theme.create_play_pause_icon())

    def on_repeat_mode_changed(self, mode: RepeatMode):
        AppSettings.setValue(SettingKeys.REPEAT_MODE, self.btn_repeat.REPEAT_MODES.index(mode))

    def repeat_mode(self):
        return self.btn_repeat.repeat_mode()

    def adjust_volume(self, value: int):
        self.engine.set_user_volume(value)
        self.visualizer.set_state(None, value)
        AppSettings.setValue(SettingKeys.VOLUME, value)

    def seek_position(self, pos: int = None):
        if pos is None:
            pos = self.progress_slider.value()
        else:
            self.progress_slider.setValue(pos)

        self.engine.set_position(pos)
        self.visualizer.set_position(pos)

    def jump_to_position(self):
        if self.progress_slider.isSliderDown():
            self.seek_position()

    def set_enabled(self, enabled: bool):
        self.btn_prev.setEnabled(enabled)
        self.btn_play.setEnabled(enabled)
        self.btn_next.setEnabled(enabled)

    def update_progress(self, position, current_time, total_time):
        if not self.progress_slider.isSliderDown():
            self.progress_slider.setValue(position)
        self.time_label.setText(current_time)
        self.duration_label.setText(total_time)

        if self._update_progress_ticks:
            total_ms = self.engine.get_total_time()
            if total_ms > 0:
                single_step = max(1, round((1000.0 / total_ms) * 1000))
                self.progress_slider.setTickPosition(QSlider.TickPosition.TicksAbove)
                self.progress_slider.setSingleStep(single_step)
                self.progress_slider.setTickInterval(max(10, round(((1000.0 / total_ms) * 1000) * 10)))
                self._update_progress_ticks = False

    def on_playback_state_changed(self, engine_state: EngineState):
        self.visualizer.set_state(engine_state, self.slider_vol.volume)

        if engine_state == EngineState.STOP:
            self.play_action.setChecked(False)
            self.progress_slider.setValue(0)
            self.time_label.setText("00:00")
        elif engine_state == EngineState.PLAY:
            self.play_action.setChecked(True)
        elif engine_state == EngineState.PAUSE:
            self.play_action.setChecked(False)

    def on_track_finished(self):
        repeat_mode = self.btn_repeat.repeat_mode()

        if repeat_mode == RepeatMode.REPEAT_SINGLE:
            self.engine.stop()
            self.play_track(self.current_index, self.current_data)
        elif repeat_mode == RepeatMode.REPEAT_ALL:
            next_index = self._increment_persistent_index(self.current_index, 1)
            self.engine.stop()
            self.track_changed.emit(next_index, next_index.data(Qt.ItemDataRole.UserRole))
        elif repeat_mode == RepeatMode.NO_REPEAT:
            self.engine.stop()

    def toggle_play(self):
        if self.engine.is_playing():
            self.engine.pause_toggle()
            self.play_action.setChecked(False)
        else:
            if self.engine.get_media() is None:
                self.track_changed.emit(QPersistentModelIndex(), None)
            else:
                self.engine.pause_toggle()

            self.play_action.setChecked(True)

    def _increment_persistent_index(self, p_index: QPersistentModelIndex, change: int):
        # 1. Safety check: is it pointing to anything?
        if not p_index.isValid():
            return p_index

        model = p_index.model()
        current_row = p_index.row()
        current_col = p_index.column()
        parent = p_index.parent()

        # 2. Check if the next row exists
        if 0 <= current_row + change < model.rowCount(parent):
            # 3. Create a new standard index for the next row
            next_idx = model.index(current_row + change, current_col, parent)

            # 4. Return a new persistent index (or overwrite your variable)
            return QPersistentModelIndex(next_idx)

        return p_index

    def next_track(self):
        next_index = self._increment_persistent_index(self.current_index, 1)
        self.engine.stop()
        self.track_changed.emit(next_index, None)

    def prev_track(self):
        next_index = self._increment_persistent_index(self.current_index, -1)
        self.engine.stop()
        self.track_changed.emit(next_index, None)

    def reset(self):
        self.time_label.setText("00:00")
        self.duration_label.setText("00:00")
        self.progress_slider.setValue(0)
        self._update_progress_ticks = True

    def elide_text(self, label: QLabel, text: str):
        metrics = QFontMetrics(label.font())
        elided = metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, label.width())
        label.setText(elided)
        if elided != text:
            label.setToolTip(text)
        else:
            label.setToolTip(None)

    def play_track(self, index: QPersistentModelIndex, data: Mp3Entry):
        self.current_data = data
        if data:
            track_path = data.path
            self.current_index = index
            try:
                self.visualizer.load_mp3(track_path)
                self.visualizer.set_state(EngineState.PLAY, self.slider_vol.volume)
                self.elide_text(self.track_label, data.name)

                self.engine.play(track_path)

            except Exception as e:
                self.track_label.setText(_("Error loading file"))
                logger.error("File error: {0}", e)
