import platform

import vlc

from PySide6.QtCore import QTimer, Signal, QObject, QSize

from components.Visualizer import VisualizerFrame
from config.settings import settings, SettingKeys

DEFAULT_VOLUME = 70

class AudioEngine(QObject):
    """
    Manages VLC instance, volume control, and playback state.
    Inherits QObject to use Signals for thread-safe communication.
    """
    # Signals to update UI
    track_finished = Signal()
    volume_changed = Signal(int)
    state_changed = Signal(bool)  # True if playing, False if stopped/paused
    position_changed = Signal(int, str, str)  # position (0-1000), current_time, total_time

    video_frame : VisualizerFrame

    def __init__(self):
        super().__init__()

        vis = settings.value(SettingKeys.VISUALIZER, "FAKE", type=str)
        if vis == "VLC":
            self.instance = vlc.Instance('--audio-visual=visual', '--effect-list=spectrum')  # Audio only
        else:
            self.instance = vlc.Instance('--no-video')  # Audio only

        self.player = self.instance.media_player_new()

        self.current_volume = DEFAULT_VOLUME
        self.player.audio_set_volume(self.current_volume)

        # Monitor VLC state
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self._check_status)
        self.monitor_timer.start(250)  # Poll more frequently for position

        # Internal flags
        self._manual_stop = False

    def load_media(self, file_path):
        media = self.instance.media_new(file_path)
        self.player.set_media(media)


    def attach_video_frame(self, video_frame: VisualizerFrame):
        self.video_frame = video_frame
        self.video_frame.resized.connect(self.resize_visualizer)
        self.resize_visualizer(self.video_frame.size())

        # The media player has to be 'connected' to the QFrame (otherwise the
        # video would be displayed in it's own window). This is platform
        # specific, so we must give the ID of the QFrame (or similar object) to
        # vlc. Different platforms have different functions for this
        if platform.system() == "Linux":  # for Linux using the X Server
            self.player.set_xwindow(int(self.video_frame.winId()))
        elif platform.system() == "Windows":  # for Windows
            self.player.set_hwnd(int(self.video_frame.winId()))
        elif platform.system() == "Darwin":  # for MacOS
            self.player.set_nsobject(int(self.video_frame.winId()))

    def resize_visualizer(self, size: QSize):
        self.player.video_set_aspect_ratio(f"{size.width()}:{size.height()}")

    def pause_toggle(self):
        if self.player.is_playing():
            self.pause()
        else:
            self.play()

    def pause(self):
        self.player.pause()
        self.state_changed.emit(False)

    def play(self):
        self._manual_stop = False
        self.player.play()
        self.state_changed.emit(True)

    def stop(self):
        self._manual_stop = True
        self.player.stop()
        self.state_changed.emit(False)
        self.set_position(0)

    def set_user_volume(self, value_0_100):
        """Logarithmic volume mapping."""
        if value_0_100 <= 0:
            vol = 0
        else:
            vol = int((value_0_100 ** 2) / 100)

        self.current_volume = vol
        self.player.audio_set_volume(vol)

    def set_position(self, position_0_1000):
        """Set player position (0-1000 scale)."""
        if self.player.is_seekable():
            self.player.set_position(position_0_1000 / 1000.0)
            self._emit_position_changed()

    def get_current_time(self):
        return self.player.get_time()

    def get_total_time(self):
        return self.player.get_length()

    def _check_status(self):
        """Poll VLC status to detect end of track and update position."""
        state = self.player.get_state()
        if state == vlc.State.Ended:
            if not self._manual_stop:
                self.track_finished.emit()

        # Update position
        if self.player.is_playing():
            self._emit_position_changed()

    def _emit_position_changed(self):
        pos = self.player.get_position()
        current_time_ms = self.player.get_time()
        total_time_ms = self.player.get_length()

        self.position_changed.emit(
            int(pos * 1000),
            format_time(current_time_ms),
            format_time(total_time_ms)
        )
def format_time(ms):
    """Converts milliseconds to MM:SS string."""
    if ms < 0: return "00:00"
    seconds = ms // 1000
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins:02d}:{secs:02d}"