# Compilation mode, standalone everywhere, except on macOS there app bundle
# nuitka-project-if: {OS} in ("Windows", "Linux", "FreeBSD"):
#    nuitka-project: --mode=standalone
#    nuitka-project: --windows-console-mode=disable
#    nuitka-project: --windows-icon-from-ico={MAIN_DIRECTORY}/docs/icon.ico
# nuitka-project-else:
#    nuitka-project: --mode=standalone
#    nuitka-project: --macos-create-app-bundle
#
# nuitka-project: --enable-plugin=pyside6
# nuitka-project: --include-data-files={MAIN_DIRECTORY}/docs/icon.ico=docs/icon.ico
# nuitka-project: --include-data-files={MAIN_DIRECTORY}/docs/splash.png=docs/splash.png
# nuitka-project: --include-data-dir={MAIN_DIRECTORY}/assets=assets
# nuitka-project: --include-data-dir={MAIN_DIRECTORY}/locales=locales
# nuitka-project: --mingw64
# nuitka-project: --output-dir=dist

import functools
import importlib
import json
import locale

import sys
import os

import traceback
import logging



from config import log


log.setup_logging()

import gettext
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel,
    QFileDialog, QMessageBox, QAbstractItemView, QMenu, QDialog, QFormLayout, QLineEdit,
    QDialogButtonBox, QStatusBar, QProgressBar, QHeaderView, QTableView, QStyleOptionViewItem,
    QStyledItemDelegate, QFileSystemModel, QTreeView, QSplitter, QStyle, QSlider,
    QListView, QToolButton, QAbstractScrollArea, QSizePolicy, QFileIconProvider
)
from PySide6.QtCore import Qt, QSize, Signal, QModelIndex, QSortFilterProxyModel, QAbstractTableModel, \
    QPersistentModelIndex, QFileInfo, QEvent, QRect, QTimer, QObject, QMimeData, QByteArray, QDataStream, QIODevice, QDir, QKeyCombination, QThread
from PySide6.QtGui import QAction, QIcon, QBrush, QPalette, QColor, QPainter, QKeyEvent, QFont, QFontMetrics, \
    QActionGroup, QDropEvent, QPen

from vlc import MediaPlayer

from config.settings import AppSettings, SettingKeys, SettingsDialog, Preset, \
    CATEGORY_MAX, CATEGORY_MIN, CAT_VALENCE, CAT_AROUSAL, MusicCategory, set_music_categories, \
    get_music_categories, set_music_tags, get_music_tags, set_presets, add_preset, remove_preset, reset_presets, get_music_category, get_presets
from config.theme import app_theme
from config.utils import get_path, get_latest_version, is_latest_version, get_current_version, clear_layout, is_frozen

from components.sliders import CategoryWidget, VolumeSlider, ToggleSlider, RepeatMode, RepeatButton, JumpSlider, BPMSlider
from components.widgets import StarRating, IconLabel, FeatureOverlay, FileFilterProxyModel
from components.visualizer import Visualizer, EmptyVisualizerWidget
from components.layouts import FlowLayout
from components.charts import RussellEmotionWidget
from components.dialogs import EditSongDialog, AboutDialog
from components.tables import DirectoryTree, AutoSearchHelper, EffectList, SongTable
from components.filter import FilterConfig
from components.models import EffectTableModel, SongTableModel

from logic.mp3 import Mp3Entry, update_mp3_favorite, parse_mp3, update_mp3_title, update_mp3_category, \
    create_m3u, list_mp3s, append_m3u, remove_m3u, update_mp3_album, update_mp3_artist, update_mp3_genre, update_mp3_bpm, \
    update_mp3_tags, get_m3u_paths, update_mp3_cover, Mp3FileLoader
from logic.audioengine import AudioEngine
from logic.analyzer import Analyzer

# --- Constants ---

logger = logging.getLogger("main")

class EffectWidget(QWidget):
    open_item: QPushButton = None

    last_index: QPersistentModelIndex = None

    icon_size = QSize(16, 16)

    def __init__(self, list_mode: QListView.ViewMode = QListView.ViewMode.ListMode):
        super().__init__()

        effects_dir = AppSettings.value(SettingKeys.EFFECTS_DIRECTORY, None, type=str)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.engine = AudioEngine(False)

        self.list_widget = EffectList(self, list_mode=list_mode)
        self.list_widget.doubleClicked.connect(self.on_item_double_clicked)

        self.player_layout = QHBoxLayout()
        self.player_layout.setContentsMargins(0, 0, 0, 0)
        self.player_layout.setSpacing(0)

        self.btn_play = QToolButton(icon=QIcon.fromTheme(QIcon.ThemeIcon.MediaPlaybackStart))
        self.btn_play.setProperty("cssClass", "play small")
        self.btn_play.setCheckable(True)
        self.btn_play.setEnabled(False)
        self.btn_play.setIcon(app_theme.create_play_pause_icon())
        self.btn_play.clicked.connect(self.toogle_play)
        self.btn_play.setShortcut("Ctrl+E")

        self.volume_slider = VolumeSlider()
        self.volume_slider.volume_changed.connect(self.on_volume_changed)
        self.volume_slider.btn_volume.setProperty("cssClass", "mini")
        self.volume_slider.slider_vol.setProperty("cssClass", "buttonSmall")
        self.player_layout.addWidget(self.btn_play, 0, Qt.AlignmentFlag.AlignBottom)
        self.player_layout.addLayout(self.volume_slider, 1)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.headerLabel = IconLabel(QIcon.fromTheme("effects"), _("Effects"))
        self.headerLabel.set_icon_size(app_theme.icon_size_small)
        self.headerLabel.set_alignment(Qt.AlignmentFlag.AlignCenter)
        self.headerLabel.text_label.setProperty("cssClass", "header")

        list_view = QToolButton(icon=QIcon.fromTheme("list"))
        list_view.setProperty("cssClass", "mini")
        list_view.clicked.connect(self.list_widget.set_list_view)

        grid_view = QToolButton(icon=QIcon.fromTheme("grid"))
        grid_view.setProperty("cssClass", "mini")
        grid_view.clicked.connect(self.list_widget.set_grid_view)

        self.headerLabel.add_widget(list_view)
        self.headerLabel.add_widget(grid_view)

        self.layout.addWidget(self.headerLabel, 0)

        if effects_dir is None or effects_dir == '':
            self.open_item = QPushButton(icon=QIcon.fromTheme(QIcon.ThemeIcon.DocumentOpen), text=_("Open Directory"))
            self.open_item.clicked.connect(self.pick_effects_directory)
            self.layout.addWidget(self.open_item, 0)
        else:
            self.load_directory(effects_dir)

        self.layout.addLayout(self.player_layout, 0)
        self.layout.addWidget(self.list_widget, 1)

        self.list_widget.calculate_grid_size()

    def show_context_menu(self, point):
        index = self.list_widget.indexAt(self.list_widget.mapFromGlobal(self.mapToGlobal(point)))
        menu = QMenu(self)

        open_dir = QAction(icon=QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen), text=_("Open Directory"), parent=self)
        open_dir.triggered.connect(self.pick_effects_directory)
        menu.addAction(open_dir)

        effects_dir = AppSettings.value(SettingKeys.EFFECTS_DIRECTORY, None, type=str)

        self.refresh_dir_action = QAction(icon=QIcon.fromTheme(QIcon.ThemeIcon.ViewRefresh), text=_("Refresh"), parent=self)
        self.refresh_dir_action.triggered.connect(self.refresh_directory)
        self.refresh_dir_action.setVisible(effects_dir is not None)
        menu.addAction(self.refresh_dir_action)


        menu.addSeparator()

        set_image_action = QAction(icon=QIcon.fromTheme(QIcon.ThemeIcon.DocumentOpen), text=_("Select Image"), parent=self)
        set_image_action.triggered.connect(functools.partial(self.pick_image_file, index))
        menu.addAction(set_image_action)

        menu.show()
        menu.exec(self.mapToGlobal(point))

    def changeEvent(self, event, /):
        if event.type() == QEvent.Type.PaletteChange:
            self.headerLabel.set_icon(QIcon.fromTheme("effects"))
            self.btn_play.setIcon(app_theme.create_play_pause_icon())
        elif event.type() == QEvent.Type.FontChange:
            self.headerLabel.set_icon_size(app_theme.icon_size_small)

            # for btn in [self.btn_prev, self.btn_play, self.btn_next, self.slider_vol.btn_volume, self.btn_repeat]:

    def toogle_play(self):
        if self.engine.pause_toggle():
            self.btn_play.setChecked(True)
        else:
            self.btn_play.setChecked(False)

    def on_volume_changed(self, volume: int = 70):
        self.engine.set_user_volume(volume)

    def on_item_double_clicked(self, index: QModelIndex):
        data = index.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, Mp3Entry):
            self.play_effect(data)

            if self.last_index is not None:
                self.list_widget.model().setData(self.last_index, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
            self.list_widget.model().setData(index, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
            self.last_index = QPersistentModelIndex(index)

    def play_effect(self, effect: Mp3Entry):
        self.engine.loop_media(effect.path)
        self.btn_play.setChecked(True)
        self.btn_play.setEnabled(True)

    def refresh_directory(self):
        effects_dir = AppSettings.value(SettingKeys.EFFECTS_DIRECTORY, None, type=str)
        self.load_directory(effects_dir)

    def load_directory(self, dir_path):
        if self.open_item is not None:
            self.layout.removeWidget(self.open_item)
            self.open_item.setParent(None)

        effect_files = list_mp3s(dir_path)
        effects = [parse_mp3(os.path.join(dir_path, file_path)) for file_path in effect_files]

        self.list_widget.setModel(EffectTableModel(effects))

    def pick_effects_directory(self):
        directory = QFileDialog.getExistingDirectory(self, _("Select Effects Directory"),
                                                     dir=AppSettings.value(SettingKeys.EFFECTS_DIRECTORY))
        if directory:
            AppSettings.setValue(SettingKeys.EFFECTS_DIRECTORY, directory)
            self.refresh_dir_action.setVisible(True)
            self.load_directory(directory)

    def pick_image_file(self, index:QModelIndex):
        file_path, ignore = QFileDialog.getOpenFileName(self, _("Select Image"),
                                                        filter=_("Image (*.png *.jpg *.jpeg *.gif *.bmp);;All (*)"))
        if file_path:
            mp3_entry = self.list_widget.mp3_data(index)
            update_mp3_cover(mp3_entry.path, file_path)
            self.refresh_directory()

class Player(QWidget):
    icon_prev: QIcon = QIcon.fromTheme(QIcon.ThemeIcon.MediaSkipBackward)
    icon_next: QIcon = QIcon.fromTheme(QIcon.ThemeIcon.MediaSkipForward)
    icon_open: QIcon = QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen)

    volume_changed = Signal(int)
    trackChanged = Signal(int, Mp3Entry)
    repeat_mode_changed = Signal(RepeatMode)
    openClicked = Signal()

    track_count = 0
    current_index = 0
    current_data = None

    _update_progress_ticks: bool = True

    def __init__(self, audioEngine: AudioEngine, parent=None):
        super().__init__(parent)

        self.player_layout = QVBoxLayout(self)
        self.player_layout.setObjectName("player_layout")
        self.player_layout.setSpacing(app_theme.spacing)

        self.engine = audioEngine
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
        self.controls_layout.setSpacing(app_theme.spacing)

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
        self.controls_layout.addWidget(self.btn_prev, alignment=Qt.AlignmentFlag.AlignBottom)
        self.controls_layout.addWidget(self.btn_next, alignment=Qt.AlignmentFlag.AlignBottom)

        self.visualizer = Visualizer.get_visualizer(self.engine)
        if isinstance(self.visualizer, EmptyVisualizerWidget):
            self.controls_layout.addLayout(self.seeker_layout, 2)
        else:
            self.player_layout.insertLayout(0, self.seeker_layout)
            self.controls_layout.addWidget(self.visualizer, 2)

        self.controls_layout.addLayout(self.slider_vol)
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

    def on_repeat_mode_changed(self, mode):
        AppSettings.setValue(SettingKeys.REPEAT_MODE, self.btn_repeat.REPEAT_MODES.index(mode))

    def repeat_mode(self):
        return self.btn_repeat.repeat_mode()

    def fire_open_clicked(self):
        self.openClicked.emit()

    def adjust_volume(self, value):
        self.engine.set_user_volume(value)
        self.visualizer.set_state(self.engine.player.is_playing(), value)
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

    def on_playback_state_changed(self, is_playing):
        self.visualizer.set_state(is_playing, self.slider_vol.volume)

    def on_track_finished(self):
        repeatMode = self.btn_repeat.repeat_mode()

        if repeatMode == RepeatMode.REPEAT_SINGLE:
            self.engine.stop()
            self.trackChanged.emit(-1, self.current_data)
        elif repeatMode == RepeatMode.REPEAT_ALL:
            next_idx = (self.current_index + 1) % self.track_count
            self.engine.stop()
            self.trackChanged.emit(next_idx, None)
        elif repeatMode == RepeatMode.NO_REPEAT:
            self.stop()
            self.engine.stop()

    def toggle_play(self):
        if self.engine.player.is_playing():
            self.engine.pause_toggle()
            # self.btn_play.setIcon(self.icon_play)
            self.play_action.setChecked(False)
        else:
            if self.engine.player.get_media() is None:
                if self.track_count >= 0:
                    self.trackChanged.emit(0, None)
                else:
                    return
            else:
                self.engine.pause_toggle()
            # self.btn_play.setIcon(self.icon_pause)
            self.play_action.setChecked(True)

    def next_track(self):
        if self.track_count == 0:
            return
        current_index = (self.current_index + 1) % self.track_count
        self.engine.stop()
        self.trackChanged.emit(current_index, None)

    def prev_track(self):
        if self.track_count == 0:
            return
        current_index = (self.current_index - 1) % self.track_count
        self.engine.stop()
        self.trackChanged.emit(current_index, None)

    def play(self):
        self.play_action.setChecked(True)

    def stop(self):
        self.play_action.setChecked(False)
        self.progress_slider.setValue(0)
        self.time_label.setText("00:00")

    def reset(self):
        self.time_label.setText("00:00")
        self.duration_label.setText("00:00")
        self.progress_slider.setValue(0)
        self._update_progress_ticks = True

    def elide_text(self, label, text):
        metrics = QFontMetrics(label.font())
        elided = metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, label.width())
        label.setText(elided)
        if elided != text:
            label.setToolTip(text)
        else:
            label.setToolTip(None)

    def play_track(self, data, index):
        self.current_data = data
        if data:
            track_path = data.path
            self.current_index = index
            try:
                self.engine.load_media(track_path)
                self.visualizer.load_mp3(track_path)
                self.visualizer.set_state(True, self.slider_vol.volume)
                self.elide_text(self.track_label, data.name)

                # Reset progress on new track
                self.reset()
                self.play()
                self.engine.play()

            except Exception as e:
                self.track_label.setText(_("Error loading file"))
                logger.error("File error: {0}", e)


class DirectoryWidget(QWidget):

    def __init__(self, player: Player, media_player: MediaPlayer, parent=None):
        super(DirectoryWidget, self).__init__(parent)

        self.player = player
        self.media_player = media_player
        self.directory_tree = DirectoryTree(self, self.player, self.media_player)

        self.directory_layout = QVBoxLayout(self)
        self.directory_layout.setContentsMargins(0, 0, 0, 0)
        self.directory_layout.setSpacing(0)

        self.headerLabel = IconLabel(QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen), _("Files"), parent = self)
        self.headerLabel.set_icon_size(app_theme.icon_size_small)
        self.headerLabel.set_alignment(Qt.AlignmentFlag.AlignCenter)
        self.headerLabel.text_label.setProperty("cssClass", "header")

        up_view_button = QToolButton()
        up_view_button.setProperty("cssClass", "mini")
        up_view_button.setDefaultAction(self.directory_tree.go_parent_action)
        self.headerLabel.insert_widget(0, up_view_button)

        open_button = QToolButton()
        open_button.setProperty("cssClass", "mini")
        open_button.setDefaultAction(self.directory_tree.open_action)
        self.headerLabel.insert_widget(1, open_button)

        set_home_button = QToolButton()
        set_home_button.setProperty("cssClass", "mini")
        set_home_button.setDefaultAction(self.directory_tree.set_home_action)

        clear_home_button = QToolButton()
        clear_home_button.setProperty("cssClass", "mini")
        clear_home_button.setDefaultAction(self.directory_tree.clear_home_action)

        self.headerLabel.add_widget(set_home_button)
        self.headerLabel.add_widget(clear_home_button)

        self.directory_layout.addWidget(self.headerLabel)
        self.directory_layout.addWidget(self.directory_tree)

    def changeEvent(self, event, /):
        if event.type() == QEvent.Type.PaletteChange:
            self.headerLabel.set_icon(QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen))
        elif event.type() == QEvent.Type.FontChange:
            self.headerLabel.set_icon_size(app_theme.icon_size_small)






class FilterWidget(QWidget):
    values_changed = Signal()

    sliders: dict[MusicCategory, CategoryWidget] = {}

    filter_config = FilterConfig()

    def __init__(self, media_player: MediaPlayer, parent=None):
        super().__init__(parent)
        self.media_player = media_player

        self.russel_widget = RussellEmotionWidget()
        self.russel_widget.valueChanged.connect(self.on_russel_changed)
        self.russel_widget.mouseReleased.connect(self.on_russel_released)

        self.bpm_widget = BPMSlider()
        self.bpm_widget.value_changed.connect(self.on_bpm_changed)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.filter_layout = QVBoxLayout(self)
        self.filter_layout.setObjectName("filter_layout")
        self.filter_layout.setContentsMargins(0, 0, 0, 0)
        self.filter_layout.setSpacing(0)

        self.slider_tabs = QTabWidget()
        self.slider_tabs.tabBar().setAutoHide(True)

        # sliders_container.addWidget(self.sliders_widget, 1)
        self.presets_widget = QWidget()
        self.presets_layout = QHBoxLayout(self.presets_widget)
        self.presets_layout.setObjectName("presets_layout")
        self.presets_layout.setContentsMargins(0, 0, 0, 0)
        self.presets_layout.setSpacing(0)
        self.presets_layout.addStretch()

        self.filter_layout.addWidget(self.presets_widget, 0)
        self.filter_layout.addWidget(self.slider_tabs, 1)
        # --------------------------------------

        self.tags_genres_widget = QWidget()
        self.tags_genres_widget.setBackgroundRole(QPalette.ColorRole.Mid)
        self.tags_genres_widget.setAutoFillBackground(True)
        self.tags_genres_widget.setContentsMargins(4, 4, 4, 4)
        self.filter_layout.addWidget(self.tags_genres_widget)

        tags_genres_layout = QVBoxLayout(self.tags_genres_widget)
        tags_genres_layout.setContentsMargins(0, 0, 0, 0)
        tags_genres_layout.setSpacing(0)

        self.tags_widget = QWidget()
        tags_widget_layout = QVBoxLayout(self.tags_widget)
        tags_widget_layout.setContentsMargins(0, 4, 0, 0)
        tags_widget_layout.setSpacing(0)

        self.tags_layout = FlowLayout()
        self.tags_layout.setObjectName("tags_layout")

        label_font = QFont()
        label_font.setBold(True)
        tags_label = QLabel(_("Tags"))
        tags_label.setFont(label_font)
        tags_label.setProperty("cssClass", "mini")
        tags_label.setStyleSheet("text-transform:uppercase")
        tags_widget_layout.addWidget(tags_label)
        tags_widget_layout.addLayout(self.tags_layout)

        self.genres_widget = QWidget()
        genres_widget_layout = QVBoxLayout(self.genres_widget)
        genres_widget_layout.setContentsMargins(0, 4, 0, 0)
        genres_widget_layout.setSpacing(0)

        self.genres_layout = FlowLayout()
        self.genres_layout.setObjectName("genres_layout")

        genres_label = QLabel(_("Genres"))
        genres_label.setFont(label_font)
        genres_label.setProperty("cssClass", "mini")
        genres_label.setStyleSheet("text-transform:uppercase")
        genres_widget_layout.addWidget(genres_label)
        genres_widget_layout.addLayout(self.genres_layout)

        tags_genres_layout.addWidget(self.tags_widget)
        tags_genres_layout.addWidget(self.genres_widget)

        self.update_presets()
        self.update_sliders()
        self.update_tags()
        self.update_genres()


    def on_table_data_changed(self, table_data:list[Mp3Entry]):
        self.update_presets()
        self.update_sliders()
        self.update_tags()
        self.update_genres()
        self.update_russel_heatmap(table_data)

    def show_context_menu(self, point):
        # index = self.indexAt(point)
        menu = QMenu(self)

        if len(get_presets()) > 0:
            presets_menu = QMenu(_("Presets"), icon=QIcon.fromTheme("russel"))
            for preset in get_presets():
                add_action = presets_menu.addAction(preset.name)
                add_action.triggered.connect(functools.partial(self.select_preset, preset))

            menu.addMenu(presets_menu)
            menu.addSeparator()

        save_preset_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.DocumentSaveAs), _("Save as Preset"), self)
        save_preset_action.triggered.connect(self.save_preset_action)
        menu.addAction(save_preset_action)

        clear_preset_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.EditClear), _("Clear Values"), self)
        clear_preset_action.triggered.connect(self.clear_sliders)
        menu.addAction(clear_preset_action)

        reset_preset_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.ViewRestore), _("Reset Presets"), self)
        reset_preset_action.triggered.connect(self.reset_preset_action)
        menu.addAction(reset_preset_action)

        menu.show()
        menu.exec(self.mapToGlobal(point))

    def apply_settings(self):
        self.russel_widget.setVisible(AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool))
        self.bpm_widget.setVisible(AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool))

        if (not AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool)
                and not AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool)
                and not AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool)):
            self.slider_tabs.setVisible(False)
        else:
            self.slider_tabs.setVisible(True)

    def build_sliders(self, categories: list[MusicCategory], group: str = None):
        sliders_widget = QWidget()
        russle_layout = QHBoxLayout(sliders_widget)

        sliders_layout = QVBoxLayout()
        sliders_layout.setObjectName("sliders_layout")
        sliders_layout.setContentsMargins(4, 0, 4, 0)

        if group is None or group == '':
            russle_layout.addWidget(self.russel_widget, 0)

        russle_layout.addLayout(sliders_layout, 1)

        if group is None or group == '':
            russle_layout.addWidget(self.bpm_widget, 0)

        # self.clear_layout(sliders_layout)
        two_rows = len(categories) > 15

        row1 = QHBoxLayout()
        row1.setObjectName("slider_row1")
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(0)

        row2 = None
        sliders_layout.addLayout(row1, 1)
        if two_rows:
            row2 = QHBoxLayout()
            row2.setObjectName("slider_row2")
            row2.setContentsMargins(0, 0, 0, 0)
            row2.setSpacing(0)
            sliders_layout.addLayout(row2, 1)

        if AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool):
            visible_categories = [cat for cat in categories if not cat.equals(CAT_VALENCE) and not cat.equals(CAT_AROUSAL)]
        else:
            visible_categories = categories

        mid = (len(visible_categories) + 1) // 2

        for i, cat in enumerate(visible_categories):

            cat_slider = CategoryWidget(category=cat, min_value=CATEGORY_MIN, max_value=CATEGORY_MAX)
            cat_slider.valueChanged.connect(self.on_slider_value_changed)

            self.sliders[cat] = cat_slider
            if not two_rows or i < mid:
                row1.addLayout(cat_slider, 1)
            else:
                row2.addLayout(cat_slider, 1)

        return sliders_widget

    def on_slider_value_changed(self):
        self.values_changed.emit()

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()

        AppSettings.setValue(SettingKeys.FILTER_VISIBLE, self.isVisible())

    def toggle_russel_widget(self):
        AppSettings.setValue(SettingKeys.RUSSEL_WIDGET, not AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool))
        self.russel_widget.setVisible(AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool))

        if AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool):
            if self.media_player.current_table() is not None:
                self.update_russel_heatmap(self.media_player.current_table().get_raw_data())
            else:
                self.update_russel_heatmap([])
        else:
            self.update_russel_heatmap([])
            self.russel_widget.reset()

        self.update_sliders()

    def toggle_category_widgets(self):
        AppSettings.setValue(SettingKeys.CATEGORY_WIDGETS, not AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool))

        if not AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool):
            for category, slider in self.sliders.items():
                slider.reset()

        self.update_sliders()

    def toggle_presets(self):
        AppSettings.setValue(SettingKeys.PRESET_WIDGETS, not AppSettings.value(SettingKeys.PRESET_WIDGETS, True, type=bool))
        self.update_presets()

    def toggle_bpm_widget(self):
        AppSettings.setValue(SettingKeys.BPM_WIDGET, not AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool))
        self.bpm_widget.setVisible(AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool))

        if not AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool):
            self.bpm_widget.reset()

        self.update_sliders()

    def toggle_tags_widget(self):
        AppSettings.setValue(SettingKeys.TAGS_WIDGET, not AppSettings.value(SettingKeys.TAGS_WIDGET, True, type=bool))

        if not AppSettings.value(SettingKeys.TAGS_WIDGET, True, type=bool):
            self.filter_config.tags.clear()

        self.update_tags()

    def toggle_genres_widget(self):
        AppSettings.setValue(SettingKeys.GENRES_WIDGET, not AppSettings.value(SettingKeys.GENRES_WIDGET, True, type=bool))

        if not AppSettings.value(SettingKeys.GENRES_WIDGET, True, type=bool):
            self.filter_config.genres.clear()

        self.update_genres()

    def toggle_tag(self, state):
        toggle = self.sender()
        self.filter_config.toggle_tag(toggle.property("tag"), state)
        self.values_changed.emit()

    def toggle_genre(self, state):
        toggle = self.sender()
        self.filter_config.toggle_genre(toggle.property("genre"), state)
        self.values_changed.emit()

    def update_tags(self):
        clear_layout(self.tags_layout)

        if AppSettings.value(SettingKeys.TAGS_WIDGET, True, type=bool):
            self.tags_genres_widget.setVisible(True)
            self.tags_widget.setVisible(True)
            for tag in self.media_player.get_available_tags():
                toggle = ToggleSlider(checked_text=tag, unchecked_text=tag)
                toggle.setProperty("tag", tag)

                if tag in get_music_tags():
                    toggle.setToolTip(get_music_tags()[tag])
                toggle.stateChanged.connect(self.toggle_tag)
                toggle.setChecked(tag in self.filter_config.tags)
                self.tags_layout.addWidget(toggle)
        else:
            self.tags_widget.setVisible(False)
            if not AppSettings.value(SettingKeys.GENRES_WIDGET, True, type=bool):
                self.tags_genres_widget.setVisible(False)

    def update_genres(self):
        clear_layout(self.genres_layout)
        if AppSettings.value(SettingKeys.GENRES_WIDGET, True, type=bool):
            self.tags_genres_widget.setVisible(True)
            self.genres_widget.setVisible(True)
            genre_palette = QPalette(self.palette())
            genre_palette.setBrush(QPalette.ColorRole.Highlight, app_theme.get_green_brush(255))

            for genre in self.media_player.get_available_genres():
                toggle = ToggleSlider(checked_text=genre, unchecked_text=genre, draggable=False)
                toggle.setPalette(genre_palette)
                toggle.setProperty("genre", genre)
                toggle.stateChanged.connect(self.toggle_genre)
                toggle.setChecked(genre in self.filter_config.genres)
                self.genres_layout.addWidget(toggle)
        else:
            self.genres_widget.setVisible(False)
            if not AppSettings.value(SettingKeys.TAGS_WIDGET, True, type=bool):
                self.tags_genres_widget.setVisible(False)


    def update_sliders(self):
        self.russel_widget.setParent(None)
        self.bpm_widget.setParent(None)

        self.slider_tabs.clear()
        self.sliders = {}

        if (not AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool)
                and not AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool)
                and not AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool)):
            self.slider_tabs.setVisible(False)
        else:
            self.slider_tabs.setVisible(True)

        if AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool):
            general_categories = [cat.key for cat in self.media_player.get_available_categories()]
            categories_group = {}
            for cat in self.media_player.get_available_categories():
                category_group = cat.group
                if category_group not in categories_group:
                    categories_group[category_group] = []
                categories_group[category_group].append(cat)

            for (group, categories) in sorted(categories_group.items()):
                self.slider_tabs.addTab(self.build_sliders(categories, group),
                                        _("General") if group is None or group == "" else group)

                general_categories = [category for category in general_categories if category not in categories]
        else:
            self.slider_tabs.addTab(self.build_sliders([], None),
                                    _("General"))

    def update_presets(self):
        clear_layout(self.presets_layout)

        if AppSettings.value(SettingKeys.PRESET_WIDGETS, True, type=bool):
            self.presets_widget.setVisible(True)
            self.presets_layout.addStretch()
            for preset in get_presets():
                button = QPushButton(text=preset.name)
                button.setProperty("cssClass", "small")
                button.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)

                remove_preset = QAction(QIcon.fromTheme(QIcon.ThemeIcon.EditDelete), _("Remove"), self)
                remove_preset.setData(preset)
                remove_preset.triggered.connect(self.remove_preset_action)
                button.addAction(remove_preset)

                reset_preset = QAction(QIcon.fromTheme(QIcon.ThemeIcon.ViewRestore), _("Reset Presets"), self)
                reset_preset.triggered.connect(self.reset_preset_action)
                button.addAction(reset_preset)

                button.clicked.connect(functools.partial(self.select_preset, preset))
                self.presets_layout.addWidget(button)

            save_preset = QToolButton(icon=QIcon.fromTheme(QIcon.ThemeIcon.DocumentSaveAs))
            save_preset.setProperty("cssClass", "small")
            save_preset.clicked.connect(self.save_preset_action)
            self.presets_layout.addWidget(save_preset)

            clear_preset = QToolButton(icon=QIcon.fromTheme(QIcon.ThemeIcon.EditClear))
            clear_preset.setProperty("cssClass", "small")
            clear_preset.clicked.connect(self.clear_sliders)
            self.presets_layout.addWidget(clear_preset)
        else:
            self.presets_widget.setVisible(False)

    def clear_sliders(self):
        for slider in self.sliders.values():
            slider.reset(False)

        if self.russel_widget.isVisible():
            self.russel_widget.set_value(5, 5)

        self.filter_config.tags.clear()
        self.filter_config.genres.clear()
        self.update_tags()
        self.update_genres()

        self.values_changed.emit()

    def reset_preset_action(self):
        reset_presets()
        self.update_presets()

    def remove_preset_action(self, checked: bool = False, data=None):
        if data is None:
            data = self.sender().data()
        remove_preset(data)
        self.update_presets()

    def select_preset(self, preset: Preset):

        for slider in self.sliders.values():
            slider.set_value(0, False)

        for cat, scale in preset.categories.items():
            category = get_music_category(cat)
            if category in self.sliders:
                self.sliders[category].set_value(scale, False)

        if preset.tags:
            self.filter_config.tags = preset.tags.copy()
        else:
            self.filter_config.tags.clear()
        self.update_tags()

        if preset.genres:
            self.filter_config.genres = preset.genres.copy()
        else:
            self.filter_config.genres.clear()
        self.update_genres()

        if CAT_VALENCE in preset.categories and CAT_AROUSAL in preset.categories:
            self.russel_widget.set_value(preset.categories[CAT_VALENCE], preset.categories[CAT_AROUSAL], False)
        if _(CAT_VALENCE) in preset.categories and _(CAT_AROUSAL) in preset.categories:
            self.russel_widget.set_value(preset.categories[_(CAT_VALENCE)], preset.categories[_(CAT_AROUSAL)], False)

        self.values_changed.emit()

    def save_preset_action(self):
        save_preset_dialog = QDialog()
        save_preset_dialog.setWindowTitle(_("Save as Preset"))
        save_preset_dialog.setWindowIcon(QIcon.fromTheme(QIcon.ThemeIcon.DocumentSaveAs))
        save_preset_dialog.setModal(True)

        layout = QFormLayout(save_preset_dialog)
        layout.setObjectName("save_preset_layout")
        name_edit = QLineEdit()
        layout.addRow("Name", name_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(save_preset_dialog.accept)
        button_box.rejected.connect(save_preset_dialog.reject)
        layout.addWidget(button_box)

        if save_preset_dialog.exec():
            preset = Preset(name_edit.text(), self.filter_config.categories, self.filter_config.tags, self.filter_config.genres)
            add_preset(preset)
            self.update_presets()

    def update_russel_heatmap(self, table_data: list[Mp3Entry]):
        # Extract values first, then filter
        raw_values = (
            (file.get_category_value(CAT_VALENCE), file.get_category_value(CAT_AROUSAL))
            for file in table_data
        )
        # Filter out pairs where either value is None
        points = (p for p in raw_values if all(v is not None for v in p))
        self.russel_widget.set_reference_points(points)

    def on_russel_changed(self, valence: float, arousal: float):
        cat_valence = get_music_category(CAT_VALENCE)
        cat_arousal = get_music_category(CAT_AROUSAL)
        self.set_category_value(cat_valence, valence, False)
        self.set_category_value(cat_arousal, arousal, False)

    def set_category_value(self, cat: str, value, notify: bool = True):
        if cat in self.sliders:
            self.sliders[cat].set_value(round(value), False)

        if notify:
            self.values_changed.emit()

    def config(self):
        self.filter_config.categories = self.categories()
        self.filter_config.bpm = self.bpm_widget.value()
        return self.filter_config

    def categories(self):
        _categories = {}
        for category, slider in self.sliders.items():
            _categories[category.key] = slider.value()

        if self.russel_widget.isVisible():
            valence, arousal = self.russel_widget.get_value()
            if valence == 5 and arousal == 5:
                _categories[CAT_VALENCE] = None
                _categories[CAT_AROUSAL] = None
            else:
                _categories[CAT_VALENCE] = valence
                _categories[CAT_AROUSAL] = arousal

        return _categories

    def on_russel_released(self):
        valence, arousal = self.russel_widget.get_value()

        cat_valence = get_music_category(CAT_VALENCE)
        cat_arousal = get_music_category(CAT_AROUSAL)
        self.set_category_value(cat_valence, valence, False)
        self.set_category_value(cat_arousal, arousal, True)

    def on_bpm_changed(self, value: int):
        self.values_changed.emit()


class MusicPlayer(QMainWindow):
    trackChanged = Signal(int)

    dir_tree_action: QAction
    light_theme_action: QAction
    dark_theme_action: QAction

    table_tabs = None

    def __init__(self, application: QApplication):
        super().__init__()

        icon_path = get_path("docs/icon.ico")
        if icon_path is not None and os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setWindowTitle(application.applicationName() + " " + application.applicationVersion())
        self.resize(1200, 700)

        self.analyzer = Analyzer.get_analyzer()
        # Load custom categories and tags
        try:
            custom_categories = AppSettings.value(SettingKeys.CATEGORIES)
            if custom_categories:
                list_of_custom_categories = json.loads(custom_categories)
                set_music_categories([MusicCategory(**d) for d in list_of_custom_categories])
        except Exception as e:
            AppSettings.remove(SettingKeys.CATEGORIES)
            logger.error("Failed to load custom categories: {0}", e)

        try:
            custom_tags = AppSettings.value(SettingKeys.TAGS)
            if custom_tags:
                set_music_tags(json.loads(custom_tags))
        except Exception as e:
            AppSettings.remove(SettingKeys.TAGS)
            logger.error("Failed to load custom tags: {0}", e)

        try:
            custom_presets = AppSettings.value(SettingKeys.PRESETS)
            if custom_presets:
                list_of_custom_presets = json.loads(custom_presets)
                set_presets([Preset(**d) for d in list_of_custom_presets])
        except Exception as e:
            AppSettings.remove(SettingKeys.PRESETS)
            logger.error("Failed to load custom presets: {0}", e)

        # Initialize Analyzer with settings

        self.current_index = -1
        self.engine = AudioEngine()

        self.init_ui()
        self.load_initial_directory()

        self.check_newer_version()

        if AppSettings.value(SettingKeys.START_TOUR, True, type=bool):
            QTimer.singleShot(500, lambda: self.start_tour())

    def check_newer_version(self):
        if not is_latest_version() and is_frozen():
            version_text = _("Newer version available {0}").format(get_latest_version())
            self.statusBar().showMessage(version_text)

    def exit(self):
        sys.exit(0)

    def init_main_menu(self):

        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu(_("File"))
        file_menu.setContentsMargins(0, 0, 0, 0)

        open_dir_action = QAction(_("Open Directory"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen))
        open_dir_action.triggered.connect(self.pick_load_directory)
        file_menu.addAction(open_dir_action)

        open_playlist_action = QAction(_("Open Playlist"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.DocumentOpen))
        open_playlist_action.triggered.connect(self.pick_load_playlist)
        file_menu.addAction(open_playlist_action)

        save_favorites_action = QAction(_("Save Favorites"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.DocumentSave))
        save_favorites_action.triggered.connect(self.pick_save_playlist)
        file_menu.addAction(save_favorites_action)

        file_menu.addSeparator()

        self.analyze_file_action = QAction(_("Analyze File"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.Scanner))
        self.analyze_file_action.triggered.connect(self.pick_analyze_file)
        self.analyze_file_action.setVisible(AppSettings.value(SettingKeys.VOXALYZER_URL, "", type=str) != "")
        file_menu.addAction(self.analyze_file_action)

        file_menu.addSeparator()

        settings_action = QAction(_("Settings"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.DocumentProperties))
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()

        exit_action = QAction(_("Exit"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.ApplicationExit))
        exit_action.triggered.connect(self.exit)
        file_menu.addAction(exit_action)

        view_menu = menu_bar.addMenu(_("View"))

        self.dir_tree_action = QAction(_("Directory Tree"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen))
        self.dir_tree_action.setCheckable(True)
        self.dir_tree_action.setChecked(AppSettings.value(SettingKeys.DIRECTORY_TREE, True, type=bool))
        self.dir_tree_action.triggered.connect(self.toggle_directory_tree)
        view_menu.addAction(self.dir_tree_action)

        filter_menu = QMenu(_("Filter"), self, icon=QIcon.fromTheme("filter"))

        view_menu.addMenu(filter_menu)

        filter_action = QAction(_("Toggle Filter"), self, icon=QIcon.fromTheme("filter"))
        filter_action.setCheckable(True)
        filter_action.setChecked(AppSettings.value(SettingKeys.FILTER_VISIBLE, True, type=bool))
        filter_action.triggered.connect(self.filter_widget.toggle)
        filter_menu.addAction(filter_action)

        self.presets_action = QAction(_("Presets"), self, icon=QIcon.fromTheme("russel"))
        self.presets_action.setCheckable(True)
        self.presets_action.setChecked(AppSettings.value(SettingKeys.PRESET_WIDGETS, True, type=bool))
        self.presets_action.triggered.connect(self.filter_widget.toggle_presets)
        filter_menu.addAction(self.presets_action)

        self.russel_action = QAction(_("Circumplex model of emotion"), self, icon=QIcon.fromTheme("russel"))
        self.russel_action.setCheckable(True)
        self.russel_action.setChecked(AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool))
        self.russel_action.triggered.connect(self.filter_widget.toggle_russel_widget)
        filter_menu.addAction(self.russel_action)

        self.categories_action = QAction(_("Category Sliders"), self, icon=QIcon.fromTheme("filter"))
        self.categories_action.setCheckable(True)
        self.categories_action.setChecked(AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool))
        self.categories_action.triggered.connect(self.filter_widget.toggle_category_widgets)
        filter_menu.addAction(self.categories_action)

        self.bpm_action = QAction(_("Beats per Minute"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical))
        self.bpm_action.setCheckable(True)
        self.bpm_action.setChecked(AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool))
        self.bpm_action.triggered.connect(self.filter_widget.toggle_bpm_widget)
        filter_menu.addAction(self.bpm_action)

        self.tags_action = QAction(_("Tags"), self, icon=QIcon.fromTheme("tags"))
        self.tags_action.setCheckable(True)
        self.tags_action.setChecked(AppSettings.value(SettingKeys.TAGS_WIDGET, True, type=bool))
        self.tags_action.triggered.connect(self.filter_widget.toggle_tags_widget)
        filter_menu.addAction(self.tags_action)

        self.genres_action = QAction(_("Genres"), self, icon=QIcon.fromTheme("tags"))
        self.genres_action.setCheckable(True)
        self.genres_action.setChecked(AppSettings.value(SettingKeys.GENRES_WIDGET, True, type=bool))
        self.genres_action.triggered.connect(self.filter_widget.toggle_genres_widget)
        filter_menu.addAction(self.genres_action)

        self.effects_tree_action = QAction(_("Effects Tree"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.AudioCard))
        self.effects_tree_action.setCheckable(True)
        self.effects_tree_action.setChecked(AppSettings.value(SettingKeys.EFFECTS_TREE, True, type=bool))
        self.effects_tree_action.triggered.connect(self.toggle_effects_tree)
        view_menu.addAction(self.effects_tree_action)

        font_size_small_action = QAction(_("Smaller"), self)
        font_size_small_action.setShortcut(QKeyCombination(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_Minus))
        font_size_small_action.triggered.connect(lambda: setattr(app_theme, 'font_size', app_theme.font_size - 1.0))

        font_size_medium_action = QAction(_("Medium"), self)
        font_size_medium_action.setShortcut(QKeyCombination(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_0))
        font_size_medium_action.triggered.connect(lambda: setattr(app_theme, 'font_size', 10.5))

        font_size_large_action = QAction(_("Larger"), self)
        font_size_large_action.setShortcut(QKeyCombination(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_Plus))
        font_size_large_action.triggered.connect(lambda: setattr(app_theme, 'font_size', app_theme.font_size + 1.0))

        font_size_group = QActionGroup(self, exclusionPolicy=QActionGroup.ExclusionPolicy.Exclusive)
        font_size_group.addAction(font_size_small_action)
        font_size_group.addAction(font_size_medium_action)
        font_size_group.addAction(font_size_large_action)

        font_size_menu = QMenu(_("Font Size"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.FormatTextBold))

        font_size_menu.addAction(font_size_small_action)
        font_size_menu.addAction(font_size_medium_action)
        font_size_menu.addAction(font_size_large_action)
        view_menu.addMenu(font_size_menu)

        visualizer_menu = QMenu(_("Visualizer"), self, icon=QIcon.fromTheme("spectrum"))

        visualizer_group = QActionGroup(self, exclusionPolicy=QActionGroup.ExclusionPolicy.Exclusive)

        vis_vlc_action = QAction(_("VLC Spectrum"), self)
        vis_vlc_action.setCheckable(True)
        vis_vlc_action.triggered.connect(self.set_visualizer_vlc)

        vis_fake_action = QAction(_("Fake"), self)
        vis_fake_action.setCheckable(True)
        vis_fake_action.triggered.connect(self.set_visualizer_fake)

        vis_none_action = QAction(_("None"), self)
        vis_none_action.setCheckable(True)
        vis_none_action.triggered.connect(self.set_visualizer_none)

        visualizer_group.addAction(vis_vlc_action)

        visualizer_group.addAction(vis_fake_action)
        visualizer_group.addAction(vis_none_action)

        vis = AppSettings.value(SettingKeys.VISUALIZER, "NONE", type=str)
        if vis == "FAKE":
            vis_fake_action.setChecked(True)
        elif vis == "VLC":
            vis_vlc_action.setChecked(True)
        else:
            vis_none_action.setChecked(True)

        visualizer_menu.addAction(vis_vlc_action)
        visualizer_menu.addAction(vis_fake_action)
        visualizer_menu.addAction(vis_none_action)

        view_menu.addMenu(visualizer_menu)

        theme_menu = QMenu(_("Theme"), self, icon=QIcon.fromTheme("theme"))

        theme_group = QActionGroup(self, exclusionPolicy=QActionGroup.ExclusionPolicy.Exclusive)

        self.light_theme_action = QAction(_("Light"), self)
        self.light_theme_action.triggered.connect(self.set_light_theme)
        self.light_theme_action.setCheckable(True)

        self.dark_theme_action = QAction(_("Dark"), self)
        self.dark_theme_action.triggered.connect(self.set_dark_theme)
        self.dark_theme_action.setCheckable(True)
        if app_theme.theme() == "LIGHT":
            self.light_theme_action.setChecked(True)
        else:
            self.dark_theme_action.setChecked(True)

        theme_group.addAction(self.light_theme_action)
        theme_group.addAction(self.dark_theme_action)

        theme_menu.addActions(theme_group.actions())

        view_menu.addMenu(theme_menu)

        # Help Menu
        help_menu = menu_bar.addMenu(_("Help"))

        tour_action = QAction(_("Show Tour"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.HelpFaq))
        tour_action.triggered.connect(self.start_tour)
        help_menu.addAction(tour_action)

        about_action = QAction(_("About"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.HelpAbout))
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def change_font_size(self, change: float):
        current_size = app_theme.font_size
        setattr(app_theme, "font_size", current_size + change)

    def get_first_slider(self):
        if len(self.filter_widget.sliders.values()) > 0:
            return next(iter(self.filter_widget.sliders.values())).slider
        else:
            return None

    def start_tour(self):
        steps = [
            {"widget": self.directory_widget, 'message': _("Tour Directory Tree")},
            {'widget': self.filter_widget.russel_widget, 'message': _("Tour Russel Widget")},
            {'widget': self.get_first_slider(), 'message': _("Tour Category Slider")},
            {'widget': self.filter_widget.bpm_widget, 'message': _("Tour BPM Widget")},
            {'widget': self.filter_widget.tags_genres_widget, 'message': _("Tour Tags Widget")},
            {'widget': self.filter_widget.presets_widget, 'message': _("Tour Presets Widget")},
            {'widget': self.table_tabs, 'message': _("Tour Song Table")},
            {'widget': self.effects_widget, 'message': _("Tour Effectslist")},
            {'widget': self.menuBar(), 'message': _("Tour Menubar")}
        ]
        self.overlay = FeatureOverlay(self, steps)
        AppSettings.setValue(SettingKeys.START_TOUR, False)

    def show_about_dialog(self):
        dialog = AboutDialog(self)
        dialog.exec()

    def set_light_theme(self):
        self.light_theme_action.setChecked(True)

        app_theme.set_theme("LIGHT")

    def set_dark_theme(self):
        self.dark_theme_action.setChecked(True)

        app_theme.set_theme("DARK")

    def set_visualizer_vlc(self):
        AppSettings.setValue(SettingKeys.VISUALIZER, "VLC")
        self.player.refresh_visualizer()

    def set_visualizer_fake(self):
        AppSettings.setValue(SettingKeys.VISUALIZER, "FAKE")
        self.player.refresh_visualizer()

    def set_visualizer_real(self):
        AppSettings.setValue(SettingKeys.VISUALIZER, "REAL")
        self.player.refresh_visualizer()

    def set_visualizer_none(self):
        AppSettings.setValue(SettingKeys.VISUALIZER, "NONE")
        self.player.refresh_visualizer()

    def toggle_directory_tree(self, visible: bool = None):

        if visible is None:
            visible = not AppSettings.value(SettingKeys.DIRECTORY_TREE, True, type=bool)

        if visible:
            sizes = self.central_splitter.sizes()
            sizes[1] = sizes[1] - 200
            sizes[0] = 200
            self.central_splitter.setSizes(sizes)
            AppSettings.setValue(SettingKeys.DIRECTORY_TREE, True)
            self.directory_widget.setEnabled(True)
        else:
            sizes = self.central_splitter.sizes()
            sizes[1] = sizes[1] + sizes[0]
            sizes[0] = 0
            self.central_splitter.setSizes(sizes)
            AppSettings.setValue(SettingKeys.DIRECTORY_TREE, False)
            self.directory_widget.setEnabled(False)

    def toggle_effects_tree(self, visible: bool = None):

        if visible is None:
            visible = not AppSettings.value(SettingKeys.EFFECTS_TREE, True, type=bool)

        if visible:
            sizes = self.central_splitter.sizes()
            sizes[1] = sizes[1] - 200
            sizes[2] = 200
            self.central_splitter.setSizes(sizes)
            AppSettings.setValue(SettingKeys.EFFECTS_TREE, True)
            self.effects_widget.setEnabled(True)
        else:
            sizes = self.central_splitter.sizes()
            sizes[1] = sizes[1] + sizes[2]
            sizes[2] = 0
            self.central_splitter.setSizes(sizes)
            AppSettings.setValue(SettingKeys.EFFECTS_TREE, False)
            self.effects_widget.setEnabled(False)

    def open_settings(self):

        dialog = SettingsDialog(self)
        if dialog.exec():
            self.filter_widget.update_sliders()
            self.filter_widget.update_tags()
            self.filter_widget.update_genres()
            self.filter_widget.update_presets()
            if self.current_table() is not None:
                self.current_table().update_category_column_visibility()

            self.analyze_file_action.setVisible(AppSettings.value(SettingKeys.VOXALYZER_URL, "", type=str) != "")

    def on_layout_splitter_moved(self, pos_x: int, index: int):
        if index == 1:
            if pos_x == 0:
                self.dir_tree_action.setChecked(False)
                self.directory_widget.setEnabled(False)
            else:
                self.dir_tree_action.setChecked(True)
                self.directory_widget.setEnabled(True)
        else:
            if pos_x + self.central_splitter.handleWidth() >= self.width():
                self.effects_tree_action.setChecked(False)
                self.effects_widget.setEnabled(False)
            else:
                self.effects_tree_action.setChecked(True)
                self.effects_widget.setEnabled(True)

    def init_ui(self):

        self.player = Player(audioEngine=self.engine)
        self.player.trackChanged.connect(self.play_track)
        self.player.openClicked.connect(self.pick_load_directory)

        self.central_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.central_splitter.splitterMoved.connect(self.on_layout_splitter_moved)
        self.setCentralWidget(self.central_splitter)

        self.directory_widget = DirectoryWidget(self.player, self)
        self.central_splitter.addWidget(self.directory_widget)
        self.central_splitter.setCollapsible(0, True)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setObjectName("main_layout")
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.central_splitter.addWidget(main_widget)
        self.central_splitter.setCollapsible(1, False)

        self.effects_widget = EffectWidget()
        self.central_splitter.addWidget(self.effects_widget)
        self.central_splitter.setCollapsible(2, True)

        # Menu Bar
        self.filter_widget = FilterWidget(self)
        self.filter_widget.values_changed.connect(self.on_update_category_values)
        main_layout.addWidget(self.filter_widget)
        self.filter_widget.setVisible(AppSettings.value(SettingKeys.FILTER_VISIBLE, True, type=bool))

        main_layout.addWidget(self.player, 0)

        self.toggle_directory_tree(AppSettings.value(SettingKeys.DIRECTORY_TREE, True, type=bool))
        self.toggle_effects_tree(AppSettings.value(SettingKeys.EFFECTS_TREE, True, type=bool))
        # -------------------------------------

        # Table Widget for Playlist

        self.table_tabs = QTabWidget()
        self.table_tabs.tabBar().setMovable(True)
        self.table_tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_tabs.tabBar().customContextMenuRequested.connect(self.show_tabs_context_menu)
        self.table_tabs.tabBar().setAutoHide(True)
        self.table_tabs.setTabsClosable(True)
        self.table_tabs.currentChanged.connect(self.on_table_tab_changed)
        self.table_tabs.tabCloseRequested.connect(self.on_table_tab_close)
        self.table_tabs.tabBar().tabMoved.connect(self.on_table_tab_moved)

        main_layout.addWidget(self.table_tabs, 2)

        self.setStatusBar(QStatusBar())
        self.statusBar().messageChanged.connect(self.update_status_message)

        self.status_progress = QProgressBar()
        self.status_progress.setContentsMargins(0, 0, 0, 0)
        self.status_progress.setRange(0, 0)
        self.statusBar().addPermanentWidget(self.status_progress)

        self.statusBar().setVisible(False)

        self.analyzer.progress.connect(self.update_status_label)
        self.analyzer.error.connect(self.update_status_label)
        self.analyzer.result.connect(self.update_table_entry)

        self.init_main_menu()

    def update_table_entry(self, path):
        self.current_table().refresh_item(path)

    def show_tabs_context_menu(self, position):
        # 4. Identify which tab was clicked
        tab_index = self.table_tabs.tabBar().tabAt(position)

        if tab_index == -1:
            return  # Right-click happened on empty space of the tab bar

        # Create the menu
        menu = QMenu(self)

        refresh_action = QAction(_("Refresh"), icon=QIcon.fromTheme(QIcon.ThemeIcon.ViewRefresh))
        refresh_action.triggered.connect(functools.partial(self.reload_table, tab_index))
        menu.addAction(refresh_action)

        close_tables_action = QAction(_("Close All"), icon=QIcon.fromTheme(QIcon.ThemeIcon.WindowClose))
        close_tables_action.triggered.connect(self.close_tables)
        menu.addAction(close_tables_action)

        menu.exec(self.table_tabs.tabBar().mapToGlobal(position))

    def hide_status_label(self):
        if self.analyzer.active_worker() == 0:
            self.statusBar().setVisible(False)
            self.status_progress.setVisible(False)

    def update_status_message(self, msg: str):
        if msg is None or msg == "":
            self.statusBar().setVisible(False)
        else:
            self.statusBar().setVisible(True)

    def update_status_label(self, msg: str, progress: bool = True):
        if msg is not None:
            self.statusBar().setVisible(True)
            self.statusBar().showMessage(msg, 5000)
            self.status_progress.setVisible(progress)

    def add_table_tab(self, table:SongTable, name: str, icon: QIcon, activate: bool = True):
        current_table = self.current_table()
        if current_table is not None and current_table.playlist is None and current_table.directory is None:
            self.table_tabs.removeTab(self.table_tabs.currentIndex())

        index = self.table_tabs.addTab(table, icon, name)

        if activate:
            self.table_tabs.setCurrentIndex(index)

    def on_table_content_changed(self, table: SongTable = None):
        if table is None:
            table = self.sender()

        if table == self.current_table():
            self.player.track_count = table.rowCount()
            self.filter_widget.on_table_data_changed(table.get_raw_data())

    def on_table_tab_changed(self, index: int):
        table: SongTable = self.table_tabs.widget(index)

        if table:
            if not table.is_loaded:
                table.load()

            table.update_category_column_visibility()
            table_data = table.get_raw_data()
        else:
            table_data = []

        self.filter_widget.on_table_data_changed(table_data)


    def on_table_tab_close(self, index: int):
        self.table_tabs.removeTab(index)
        self.table_tabs.tabBar().setVisible(self.table_tabs.count() > 1)

        AppSettings.setValue(SettingKeys.OPEN_TABLES, self.get_open_tables())

    def on_table_tab_moved(self, fromIndex: int, toIndex: int):
        AppSettings.setValue(SettingKeys.OPEN_TABLES, self.get_open_tables())

    def on_update_category_values(self):
        self.sort_table_data()

    def pick_analyze_file(self):
        file_path, ignore = QFileDialog.getOpenFileName(self, _("Select File to Analyze"),
                                                        dir=self._get_default_directory(),
                                                        filter=_("Mp3 (*.mp3 *.MP3);;All (*)"))
        if file_path:
            self.analyze_file(file_path)

    def analyze_file(self, file_path: str | os.PathLike[str]):
        try:
            self.analyzer.process(file_path)
            self.current_table().refresh_item(file_path)
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, _("Analysis Error"), _("Failed to analyze file: {0}").format(e))

    def _get_default_directory(self) -> str:
        if AppSettings.value(SettingKeys.ROOT_DIRECTORY):
            return str(AppSettings.value(SettingKeys.ROOT_DIRECTORY))
        elif AppSettings.value(SettingKeys.LAST_DIRECTORY):
            return str(AppSettings.value(SettingKeys.LAST_DIRECTORY))
        else:
            return os.path.abspath(Path.home())

    def pick_load_playlist(self):
        file_path, ignore = QFileDialog.getOpenFileName(self, _("Select Playlist to Load"),
                                                        dir=self._get_default_directory(),
                                                        filter=_("Playlist (*.m3u *.M3U);;All (*)"))
        if file_path:
            self.load_playlist(file_path)

    def pick_new_playlist(self, entries: list[Mp3Entry] = None):
        new_play_list = self.pick_save_playlist(entries)

        if new_play_list is not None:
            self.load_playlist(new_play_list)

    def pick_save_playlist(self, entries: list[Mp3Entry] = None):
        file_path, ignore = QFileDialog.getSaveFileName(self, _("Select Playlist to Save"),
                                                        dir=self._get_default_directory(),
                                                        filter=_("Playlist (*.m3u *M3U);;All (*)"))
        if file_path:
            try:
                if self.save_playlist(file_path, entries):
                    self.statusBar().showMessage(_("Save Complete") + ": " + _("File {0} processed.").format(Path(file_path).name), 5000)
                    return file_path
                else:
                    QMessageBox.critical(self, _("Save Error"), _("No favorites found."))
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, _("Save Error"), _("Failed to save file: {0}").format(e))
        return None

    def pick_load_directory(self):
        directory = QFileDialog.getExistingDirectory(self, _("Select Music Directory"),
                                                     dir=self._get_default_directory())
        if directory:
            self.load_directory(directory)

    def generate_table(self, playlist_path = None, directory = None, lazy: bool = False):
        table = SongTable(self.analyzer, self)
        table.play_track.connect(self.play_track)
        table.contentChanged.connect(self.on_table_content_changed)

        if playlist_path is not None:
            table.playlist = playlist_path
            mp3_files = get_m3u_paths(playlist_path)

            self.load_files(table, mp3_files, lazy=lazy)

        elif directory is not None:
            table.directory = directory

            base_path = Path(directory)
            mp3_files = list(base_path.rglob("*.mp3"))

            self.load_files(table, mp3_files, lazy=lazy)

        return table

    def load_playlist(self, playlist_path: str | os.PathLike[str], activate: bool = True, lazy: bool = False) -> SongTable:
        try:
            if playlist_path in self.get_playlists():
                self.statusBar().showMessage(_("Playlist already opened"))
                return
            self.statusBar().showMessage(_("Loading playlist"), 2000)
            QApplication.processEvents()


            name = Path(playlist_path).name.removesuffix(".m3u").removesuffix(".M3U")

            table = self.generate_table(playlist_path=playlist_path, lazy=lazy)

            self.add_table_tab(table, name, QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical), activate=activate)

            AppSettings.setValue(SettingKeys.OPEN_TABLES, self.get_open_tables())

            self.statusBar().clearMessage()

            return table
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, _("Open Error"), _("Failed to load playlist: {0}").format(e))

    def save_playlist(self, playlist_path, entries: list[Mp3Entry] = None) -> bool:
        if entries is None:
            table = self.current_table()
            if table is None:
                return False

            entries = [x for x in table.mp3_datas() if x.favorite]

        if entries and len(entries) > 0:
            create_m3u(entries, playlist_path)
            return True
        else:
            return False

    def add_to_playlist(self, playlist: os.PathLike[str], songs: list[Mp3Entry]):
        for i in range(self.table_tabs.count()):
            table = self.table_tabs.widget(i)
            if table.playlist == playlist:
                table.table_model.addRows(songs)
                break

        if table:
            create_m3u(table.mp3_datas(), playlist)

    def get_open_tables(self) -> list[os.PathLike[str]]:
        open_tables = []
        for i in range(self.table_tabs.count()):
            table = self.table_tabs.widget(i)
            if table.playlist is not None:
                open_tables.append(table.playlist)
            else:
                open_tables.append(table.directory)

        return open_tables

    def get_playlists(self) -> list[os.PathLike[str]]:
        playlists = []
        for i in range(self.table_tabs.count()):
            table = self.table_tabs.widget(i)
            if table.playlist is not None:
                playlists.append(table.playlist)

        return playlists

    def get_directories(self) -> list[os.PathLike[str]]:
        directories = []
        for i in range(self.table_tabs.count()):
            table = self.table_tabs.widget(i)
            if table.directory is not None:
                directories.append(table.directory)

        return directories

    def load_directory(self, directory: str | os.PathLike[str], activate: bool = True, lazy: bool = False) -> SongTable:
        try:
            if directory in self.get_directories():
                self.statusBar().showMessage(_("Directory already opened"))
                return

            self.statusBar().showMessage(_("Loading directory"), 5000)
            QApplication.processEvents()

            AppSettings.setValue(SettingKeys.LAST_DIRECTORY, directory)

            table = self.generate_table(directory=directory, lazy=lazy)

            self.add_table_tab(table, Path(directory).name, QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen), activate=activate)

            AppSettings.setValue(SettingKeys.OPEN_TABLES, self.get_open_tables())

            self.statusBar().clearMessage()
            return table
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, _("Error"), _("Failed to scan directory: {0}").format(e))

    def get_available_categories(self) -> list[MusicCategory]:
        table = self.current_table()
        return table.table_model.available_categories if table is not None else []
    def get_available_tags(self) -> list[str]:
        table = self.current_table()
        return table.table_model.available_tags if table is not None else []
    def get_available_genres(self) -> list[str]:
        table = self.current_table()
        return table.table_model.available_genres if table is not None else []

    def load_files(self, table: SongTable, mp3_files: list[Path | Mp3Entry], lazy: bool = False):
        if not mp3_files:
            QMessageBox.information(self, _("Scan"), _("No MP3 files found."))
            return

        if isinstance(mp3_files[0], Path):
            table.set_files(mp3_files)
            if not lazy and table == self.current_table():
                table.load()
        else:
            table.populate_table(mp3_files)
            self.on_table_content_changed(table)


    def close_tables(self):
        self.table_tabs.clear()
        self.add_table_tab(SongTable(_analyzer=self.analyzer, _music_player=self), "Welcome", QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical))

    def reload_table(self, index: int):
        table = self.table(index)

        if table.playlist:
            mp3_files = get_m3u_paths(table.playlist)
            self.load_files(table, mp3_files)
        else:
            base_path = Path(table.directory)
            mp3_files = list(base_path.rglob("*.mp3"))
            self.load_files(table, mp3_files)

    def table(self, index: int) -> SongTable | None:
        return self.table_tabs.widget(index) if self.table_tabs is not None else None

    def current_table(self) -> SongTable | None:
        return self.table_tabs.currentWidget() if self.table_tabs is not None else None
        # if len(self.tables)>0:
        #     return self.tables[self.table_tabs.currentIndex()]
        # else:
        #     return None;

    def sort_table_data(self):
        table = self.current_table()
        if table is None:
            return

        data = table.mp3_data(self.player.current_index)

        table.table_model.set_filter_values(self.filter_widget.config())
        table.update_category_column_visibility()

        current_track_path = None

        if data:
            current_track_path = data.path

        table.selectRow(0)
        table.sortByColumn(SongTableModel.SCORE_COL, Qt.SortOrder.AscendingOrder)

        if current_track_path:
            self.player.current_index = table.index_of(data)

    def load_initial_directory(self):
        open_tables = AppSettings.value(SettingKeys.OPEN_TABLES, [], type=list)

        if open_tables:
            for index, open_table in enumerate(open_tables):
                self.load(open_table, lazy=True, activate=index==0)
        else:
            last_dir = AppSettings.value(SettingKeys.LAST_DIRECTORY)
            if last_dir:
                self.load(last_dir, lazy=True)
            else:
                self.add_table_tab(SongTable(_analyzer=self.analyzer, _music_player=self), "Welcome", QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical))

        current_table = self.current_table()
        if current_table is not None:
            current_table.load()

    def load(self, path: str | os.PathLike[str], activate = True, lazy: bool = False):
        if Path(path).is_dir():
            self.load_directory(path, lazy=lazy, activate=activate)
        elif Path(path).is_file():
            self.load_playlist(path, lazy=lazy, activate=activate)
        else:
            QMessageBox.critical(self, _("Open Error"), _("Failed to load: {0}").format(path))

    def play_track(self, index: int, entry: Mp3Entry | None):
        table = self.current_table()
        if table is None:
            if entry is not None:
                self.player.play_track(entry, -1)
                return
            else:
                return

        if index < 0:
            # calc index of entry
            entry_index = table.index_of(entry)
            if entry_index >= 0:
                self.current_index = entry_index
                table.clearSelection()
                table.selectRow(entry_index)
            self.player.play_track(entry, entry_index)

        elif 0 <= index < table.rowCount():
            self.current_index = index
            table.clearSelection()
            table.selectRow(index)
            data = table.mp3_data(index)
            self.player.play_track(data, index)


app: QApplication
window: QMainWindow


def hide_splash(window: QMainWindow):
    if '_PYI_SPLASH_IPC' in os.environ and importlib.util.find_spec("pyi_splash"):
        import pyi_splash
        pyi_splash.close()

        # bring window to top and act like a "normal" window!
        window.setWindowFlags(window.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)  # set always on top flag, makes window disappear
        window.show()  # makes window reappear, but it's ALWAYS on top
        window.setWindowFlags(
            window.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowCloseButtonHint)  # clear always on top flag, makes window disappear
        window.show()  # makes window reappear, acts like normal window now (on top now but can be underneath if you raise another window)
    else:
        window.show()


def main():
    global app, window

    if "DEBUG" in os.environ:
        logger.setLevel(logging.DEBUG)

    app = QApplication(sys.argv)

    # Set up Gettext

    language = AppSettings.value(SettingKeys.LOCALE, type=str)
    if language is None or language == "":
        loc, encoding = locale.getlocale()
        language = loc

    i18n = gettext.translation("DungeonTuber", get_path("locales"), fallback=True, languages=[language])

    # Create the "magic" function
    i18n.install()

    app.setOrganizationName("Gandulf")
    app.setApplicationName("Dungeon Tuber")
    app.setApplicationVersion(get_current_version())

    app_theme.application = app
    app_theme.apply_stylesheet()

    window = MusicPlayer(app)
    hide_splash(window)

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        logger.exception("Main crashed. Error: {0}", e)
