import platform
from os import PathLike

from PySide6.QtCore import QTimer, Signal, QObject
from vlc import MediaListPlayer, Media, Instance, PlaybackMode, State

from config.settings import AppSettings, SettingKeys

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

    list_player: MediaListPlayer = None
    player: Media = None

    def __init__(self, visualizer : bool = True):
        super().__init__()

        self.current_volume = DEFAULT_VOLUME
        self.init_vlc(visualizer)
        # Monitor VLC state
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self._check_status)
        self.monitor_timer.start(250)  # Poll more frequently for position

        # Internal flags
        self._manual_stop = False

    def init_vlc(self, visualizer : bool = True):
        vis = AppSettings.value(SettingKeys.VISUALIZER, "NONE", type=str)

        if AppSettings.value(SettingKeys.NORMALIZE_VOLUME, True, type=bool):
            args = [
                "--audio-filter=compressor",
                "--compressor-threshold=-25.0",
                "--compressor-ratio=20.0",
                "--compressor-attack=5.0",
                "--compressor-release=500.0",
                "--compressor-makeup-gain=12.0",
                "--compressor-knee=2.5",
                "--compressor-rms-peak=0.0"  # Peak is better for limiting max volume
            ]
        else:
            args = []

        # Define the audio output module based on the OS
        if platform.system() == "Windows":
            args.append("--aout=directsound")  # or "wasapi" for modern Windows
        elif platform.system() == "Linux":
            args.append("--aout=pulseaudio")
        elif platform.system() == "Darwin":  # macOS
            args.append("--aout=auhal")

        if vis == "VLC" and visualizer:
            args.append("--audio-visual=visual")
            args.append("--effect-list=spectrum")
        else:
            args.append("--no-video")  # Audio only

        self.instance = Instance(args)
        self.list_player = self.instance.media_list_player_new()
        self.player = self.list_player.get_media_player()
        self.player.audio_set_volume(self.current_volume)

    def load_media(self, file_path: PathLike[str]):
        media = self.instance.media_new(file_path)
        self.player.set_media(media)

    def loop_media(self, file_path: PathLike[str]):
        # 2. Create a Media List and add your song
        media_list = self.instance.media_list_new()
        media = self.instance.media_new(file_path)
        media_list.add_media(media)

        # 3. Create a Media List Player and associate the list
        if self.list_player is None:
            self.list_player = self.instance.media_list_player_new()
        else:
            self.list_player.stop()
        self.list_player.set_media_list(media_list)

        # 4. Set the playback mode to Loop (Repeat)
        self.list_player.set_playback_mode(PlaybackMode.loop)
        self.list_player.get_media_player().audio_set_volume(75)
        # Start playing
        self.list_player.play()

    def is_playing(self)->bool:
        return self.player.is_playing()

    def pause_toggle(self)-> bool:
        if self.player.is_playing():
            self.pause()
            return False
        else:
            self.play()
            return True

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

    def set_user_volume(self, value_0_150: int):
        """Logarithmic volume mapping."""
        if value_0_150 <= 0:
            vol = 0
        else:
            vol = int((value_0_150 ** 2) / 100)

        self.current_volume = vol
        self.player.audio_set_volume(vol)

    def set_position(self, position_0_1000: int):
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
        if state == State.Ended:
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
def format_time(ms: int):
    """Converts milliseconds to MM:SS string."""
    if ms < 0:
        return "00:00"
    seconds = ms // 1000
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins:02d}:{secs:02d}"
