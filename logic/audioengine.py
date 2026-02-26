import platform
import threading
import time
from enum import Enum
from os import PathLike

from PySide6.QtCore import QTimer, Signal, QObject, QSize
from vlc import MediaListPlayer, Media, Instance, PlaybackMode, State, MediaPlayer

from config.settings import AppSettings, SettingKeys

DEFAULT_VOLUME = 70

def format_time(ms: int):
    """Converts milliseconds to MM:SS string."""
    if ms < 0:
        return "00:00"
    seconds = ms // 1000
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins:02d}:{secs:02d}"


class EngineState(Enum):
    PAUSE = 1
    PLAY = 2
    STOP = 3

class AudioEngine(QObject):
    """
    Manages VLC instance, volume control, and playback state.
    Inherits QObject to use Signals for thread-safe communication.
    """
    # Signals to update UI
    track_finished = Signal()
    state_changed = Signal(EngineState)  # True if playing, False if stopped/paused
    position_changed = Signal(int, str, str)  # position (0-1000), current_time, total_time

    instance:Instance = None
    list_player: MediaListPlayer | None = None
    player: MediaPlayer | None = None
    player_fade: MediaPlayer | None = None

    cross_fade = True

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

    def attach_window(self, window_id: int | None):
        self.cross_fade= window_id is None

        if window_id is not None:
            if platform.system() == "Linux":  # for Linux using the X Server
                self.player.set_xwindow(window_id)
            elif platform.system() == "Windows":  # for Windows
                self.player.set_hwnd(window_id)
            elif platform.system() == "Darwin":  # for MacOS
                self.player.set_nsobject(window_id)

    def set_aspect_ratio(self, size:QSize):
        self.player.video_set_aspect_ratio(f"{size.width()}:{size.height()}")

    def init_vlc(self, visualizer : bool = True):
        player_media = None
        player_fade_media = None

        if self.player is not None:
            if self.player.is_playing():
                player_media = self.player.get_media()
                player_position = self.player.get_position()
            self.player.stop()
            self.player.release()

        if self.player_fade is not None:
            if self.player_fade.is_playing() and player_media is None:
                player_fade_media = self.player_fade.get_media()
                player_fade_position = self.player_fade.get_position()
            self.player_fade.stop()
            self.player_fade.release()

        if self.list_player is not None:
            self.list_player.stop()
            self.list_player.release()
            self.list_player = None

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

        if self.instance is not None:
            self.instance.release()

        self.instance = Instance(args)

        self.player = self.instance.media_player_new()
        self.player.audio_set_volume(self.current_volume)

        if player_media is not None:
            self.player.set_media(player_media)
            self.player.play()
            self.player.set_position(player_position)

        self.player_fade = self.instance.media_player_new()
        self.player_fade.audio_set_volume(self.current_volume)

        if player_fade_media is not None:
            self.player_fade.set_media(player_fade_media)
            self.player_fade.play()
            self.player_fade.set_position(player_fade_position)

    def loop_media(self, file_path: PathLike[str]):
        if self.list_player is None:
            self.list_player = self.instance.media_list_player_new()

        self.player = self.list_player.get_media_player()
        # 2. Create a Media List and add your song
        media_list = self.instance.media_list_new([file_path])

        self.list_player.set_playback_mode(PlaybackMode.loop)
        self.list_player.stop()
        self.list_player.set_media_list(media_list)
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
        self.state_changed.emit(EngineState.PAUSE)

    def _crossfade_thread(self, player_out, player_in, duration_ms=1000, steps=50):
        """Thread function to handle volume crossfade."""
        step_duration = duration_ms / steps / 1000.0  # in seconds
        
        # Get the initial volume of the outgoing player
        initial_volume_out = player_out.audio_get_volume()

        for i in range(steps + 1):
            progress = i / steps
            
            # Fade out the old player
            player_out.audio_set_volume(int(initial_volume_out * (1 - progress)))
            
            # Fade in the new player
            player_in.audio_set_volume(int(self.current_volume * progress))
            
            time.sleep(step_duration)

        player_out.stop()
        # Ensure the new player is at the target volume
        player_in.audio_set_volume(self.current_volume)

    def play(self, file_path: PathLike[str] = None):
        if file_path is not None:
            media = self.instance.media_new(file_path)
            if self.player.is_playing() and self.cross_fade:
                # Swap players for crossfade
                self.player, self.player_fade = self.player_fade, self.player
                self.player.set_media(media)

                # Start crossfade in a new thread
                fade_thread = threading.Thread(
                    target=self._crossfade_thread,
                    args=(self.player_fade, self.player)
                )
                fade_thread.daemon = True
                fade_thread.start()
            else:
                self.player.set_media(media)

        self._manual_stop = False
        self.player.play()
        self.state_changed.emit(EngineState.PLAY)



    def stop(self):
        self._manual_stop = True
        self.player.stop()
        self.state_changed.emit(EngineState.STOP)
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

    def get_media(self):
        return self.player.get_media()

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
