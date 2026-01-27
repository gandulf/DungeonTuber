# Compilation mode, standalone everywhere, except on macOS there app bundle
# nuitka-project-if: {OS} in ("Windows", "Linux", "FreeBSD"):
#    nuitka-project: --mode=standalone
#    nuitka-project: --windows-console-mode=hide
#    nuitka-project: --windows-icon-from-ico={MAIN_DIRECTORY}/docs/icon.ico
# nuitka-project-else:
#    nuitka-project: --mode=standalone
#    nuitka-project: --macos-create-app-bundle
#
# nuitka-project: --enable-plugin=pyside6
# nuitka-project: --include-data-files={MAIN_DIRECTORY}/version.txt=version.txt
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
import numbers
import sys
import os

import threading
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
    QListView, QToolButton, QAbstractScrollArea, QSizePolicy, QFileIconProvider, QScrollArea
)
from PySide6.QtCore import Qt, QSize, Signal, QModelIndex, QSortFilterProxyModel, QAbstractTableModel, \
    QPersistentModelIndex, QFileInfo, QEvent, QRect, QTimer, QObject
from PySide6.QtGui import QAction, QIcon, QBrush, QPalette, QColor, QPainter, QKeyEvent, QFont, QFontMetrics, \
    QActionGroup

from vlc import MediaPlayer

from config.settings import AppSettings, SettingKeys, SettingsDialog, Preset, \
    CATEGORY_MAX, CATEGORY_MIN, CAT_VALENCE, CAT_AROUSAL, MusicCategory, set_music_categories, \
    get_music_categories, set_music_tags, get_music_tags, set_presets, add_preset, get_presets, remove_preset, reset_presets, get_music_category, get_categories
from config.theme import app_theme
from config.utils import get_path, get_latest_version, is_latest_version, get_current_version, clear_layout, \
    DOWNLOAD_LINK, is_frozen

from components.sliders import CategoryWidget, VolumeSlider, ToggleSlider, RepeatMode, RepeatButton, JumpSlider, BPMSlider
from components.widgets import StarRating, IconLabel, FeatureOverlay, FileFilterProxyModel
from components.visualizer import Visualizer, EmptyVisualizerWidget
from components.layouts import FlowLayout
from components.charts import RussellEmotionWidget
from components.dialogs import EditSongDialog, AboutDialog

from logic.mp3 import Mp3Entry, update_mp3_favorite, parse_mp3, update_mp3_title, update_mp3_category, parse_m3u, \
    create_m3u, list_mp3s, normalize_category, append_m3u, remove_m3u, update_mp3_album, update_mp3_artist, update_mp3_genre, update_mp3_bpm, update_mp3_data, \
    update_mp3_tags
from logic.audioengine import AudioEngine
from logic.analyzer import Analyzer

# --- Constants ---

logger = logging.getLogger("main")

available_tags: list[str] = []
available_genres: list[str] = []
available_categories : list[MusicCategory] = []
selected_tags: list[str] = []
selected_genres: list[str] = []

categories: dict[str, int] = {}


class FilterConfig:
    categories: dict[str, int]
    tags: list[str]
    bpm: int | None
    genres: list[str]

    def __init__(self, categories={}, tags=[], bpm=None, genres=[]):
        self.categories = categories
        self.tags = tags
        self.bpm = bpm
        self.genres = genres

    def get_category(self, category: str, default: int = None):
        category = normalize_category(category)
        return self.categories.get(category, default)

    def empty(self) -> bool:
        empty = True
        for value in self.categories.values():
            if value is not None:
                empty = False
                break

        empty = empty and (self.tags is None or len(self.tags) == 0) and self.bpm is None and (self.genres is None or len(self.genres) == 0)

        return empty


def _calculate_score(_filter_config: FilterConfig, data: Mp3Entry):
    score = None
    for cat, desired_value in _filter_config.categories.items():
        if desired_value is not None and desired_value >= 0:
            if score is None:
                score = 0
            current_value = data.get_category_value(cat)
            if isinstance(current_value, numbers.Number):
                score += (current_value - desired_value) ** 2
            else:
                score += 10 ** 2

    for desired_tag in _filter_config.tags:
        if score is None:
            score = 0

        if data.tags is not None:
            if desired_tag not in data.all_tags and desired_tag not in data.genres:
                score += 100
        else:
            score += 100

    for desired_genres in _filter_config.genres:
        if score is None:
            score = 0

        if data.genres is not None:
            if desired_genres not in data.genres:
                score += 100
        else:
            score += 100

    if _filter_config.bpm is not None:
        if score is None:
            score = 0

        if data.bpm is None:
            score += 100
        else:
            score += abs(_filter_config.bpm - data.bpm)

    return round(score) if score is not None else None


_black = QColor(Qt.GlobalColor.black)
_transparent = QBrush(Qt.GlobalColor.transparent)


def _get_genre_background_brush(desired_values: list[str] | None, values: list[str]) -> QBrush | None:
    if values is None or desired_values is None:
        return _transparent

    if isinstance(values,str):
        values = ", ".split(values)

    found=0
    for desired_value in desired_values:
        if desired_value in values:
            found = found + 1

    if found == len(desired_values):
        return app_theme.get_green(51)
    elif found>0:
        return app_theme.get_orange(51)
    else:
        return app_theme.get_red(51)


def _get_category_background_brush(desired_value: int | None, value: int) -> QBrush | None:
    if value is None or desired_value is None:
        return _transparent

    value_diff = abs(desired_value - value)

    if value_diff < 4:
        return app_theme.get_green(51)
    elif value_diff < 7:
        return app_theme.get_orange(51)
    else:
        return app_theme.get_red(51)


def _get_bpm_background_brush(desired_value: int | None, value: int) -> QBrush | None:
    if value is None or desired_value is None or desired_value == 0:
        return _transparent

    value_diff = abs(desired_value - value)

    if value_diff <= 40:
        return app_theme.get_green(51)
    elif value_diff <= 80:
        return app_theme.get_orange(51)
    else:
        return app_theme.get_red(51)


def _get_score_foreground_brush(score: int | None) -> QColor | None:
    if score is not None:
        if score < 50:
            return _black
        elif score < 100:
            return _black
        elif score < 150:
            return _black
        else:
            return _black
    else:
        return _black


def _get_score_background_brush(score: int | None) -> QBrush | None:
    if score is not None:
        if score < 50:
            return app_theme.get_green(170)
        elif score < 100:
            return app_theme.get_yellow(170)
        elif score < 150:
            return app_theme.get_orange(170)
        else:
            return app_theme.get_red(170)
    else:
        return None


class AutoSearchHelper():
    _ignore_keys = [Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right]

    def __init__(self, proxy_model: QSortFilterProxyModel, parent: QAbstractScrollArea = None):
        self.parent = parent
        self.proxy_model = proxy_model
        self.search_string = ""

    def keyPressEvent(self, event):
        # If user presses Backspace, remove last char
        if event.key() in self._ignore_keys:
            return False

        if event.key() == Qt.Key_Backspace:
            self.search_string = self.search_string[:-1]
        # If it's a valid character (letter/number), append to search
        elif event.text().isalnum() or event.text() in " _-":
            self.search_string += event.text()
        # If Escape is pressed, clear filter
        elif event.key() == Qt.Key_Escape:
            self.search_string = ""
        else:
            return False

        # Apply the filter to the proxy
        self.proxy_model.setFilterFixedString(self.search_string)

        self.parent.viewport().update()

        return True

    def paintEvent(self, event):

        # 2. If there is a search string, draw the popup overlay
        if self.search_string:
            painter = QPainter(self.parent.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Style settings
            font = QFont()
            font.setPointSizeF(app_theme.font_size_small)
            painter.setFont(font)
            metrics = QFontMetrics(font)

            padding = 10
            text_width = metrics.horizontalAdvance(self.search_string)
            text_height = metrics.height()

            # Calculate the rectangle size and position (Top Right)
            rect_w = text_width + (padding * 2)
            rect_h = text_height + padding
            margin = 10

            popup_rect = QRect(
                self.parent.viewport().width() - rect_w - margin,
                margin,
                rect_w,
                rect_h
            )

            # Draw the background (Semi-transparent dark grey)
            painter.setBrush(QColor(50, 50, 50, 200))
            if self.proxy_model.rowCount() == 0:
                painter.setPen(app_theme.get_red(100))  # Light red border
            else:
                painter.setPen(QColor(200, 200, 200))  # Light border
            painter.drawRoundedRect(popup_rect, 5, 5)

            # Draw the text
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(popup_rect, Qt.AlignmentFlag.AlignCenter, self.search_string)

            painter.end()


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

        self.list_widget = EffectList(list_mode=list_mode)
        self.list_widget.doubleClicked.connect(self.on_item_double_clicked)

        self.player_layout = QHBoxLayout()
        self.player_layout.setContentsMargins(0, 0, 0, 0)
        self.player_layout.setSpacing(0)

        self.btn_play = QToolButton(icon=QIcon.fromTheme(QIcon.ThemeIcon.MediaPlaybackStart))
        self.btn_play.setProperty("class", "play")
        self.btn_play.setCheckable(True)
        self.btn_play.setEnabled(False)
        self.btn_play.setIcon(app_theme.create_play_pause_icon())
        self.btn_play.clicked.connect(self.toogle_play)
        self.btn_play.setShortcut("Ctrl+E")
        self.btn_play.setFixedSize(app_theme.button_size_small)
        self.btn_play.setIconSize(app_theme.icon_size_small)

        self.volume_slider = VolumeSlider()
        self.volume_slider.volume_changed.connect(self.on_volume_changed)
        self.volume_slider.set_button_size(app_theme.button_size_small)
        self.volume_slider.set_icon_size(app_theme.icon_size_small)
        self.volume_slider.slider_vol.setFixedHeight(app_theme.button_height_small)
        self.player_layout.addWidget(self.btn_play, 0)
        self.player_layout.addLayout(self.volume_slider, 1)

        open_dir = QAction(icon=QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen), text=_("Open Directory"), parent=self)
        open_dir.triggered.connect(self.pick_effects_directory)
        self.addAction(open_dir)

        self.refresh_dir = QAction(icon=QIcon.fromTheme(QIcon.ThemeIcon.ViewRefresh), text=_("Refresh"), parent=self)
        self.refresh_dir.triggered.connect(self.refresh_directory)
        self.refresh_dir.setVisible(effects_dir is not None)
        self.addAction(self.refresh_dir)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)

        self.headerLabel = IconLabel(QIcon.fromTheme("effects"), _("Effects"))
        self.headerLabel.set_alignment(Qt.AlignmentFlag.AlignCenter)
        self.headerLabel.text_label.setStyleSheet(f"font-size: {app_theme.font_size}pt; font-weight: bold;")
        self.headerLabel.setFixedHeight(app_theme.button_height_small)

        list_view = QToolButton(icon=QIcon.fromTheme("list"))
        list_view.clicked.connect(self.list_widget.set_list_view)

        grid_view = QToolButton(icon=QIcon.fromTheme("grid"))
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

    def changeEvent(self, event, /):
        if event.type() == QEvent.Type.PaletteChange:
            self.headerLabel.set_icon(QIcon.fromTheme("effects"))
            self.btn_play.setIcon(app_theme.create_play_pause_icon())
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

        self.list_widget.load_effects(effects)

    def pick_effects_directory(self):
        directory = QFileDialog.getExistingDirectory(self, _("Select Effects Directory"),
                                                     dir=AppSettings.value(SettingKeys.EFFECTS_DIRECTORY))
        if directory:
            AppSettings.setValue(SettingKeys.EFFECTS_DIRECTORY, directory)
            self.refresh_dir.setVisible(True)
            self.load_directory(directory)


class EffectTableModel(QAbstractTableModel):
    _checked: QPersistentModelIndex = QPersistentModelIndex()

    def __init__(self, data: list[Mp3Entry] = []):
        super(EffectTableModel, self).__init__()
        self._data = data

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return len(self._data)

    def columnCount(self, parent: QModelIndex = ...) -> int:
        return 1

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        return super().flags(index) | Qt.ItemFlag.ItemIsUserCheckable

    def data(self, index, /, role=...):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if self._checked == index else Qt.CheckState.Unchecked
        elif role == Qt.ItemDataRole.DecorationRole:
            data = index.data(Qt.ItemDataRole.UserRole)
            return QIcon(data.cover) if data.cover is not None else None
        elif role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            data = index.data(Qt.ItemDataRole.UserRole)
            return data.name
        elif role == Qt.ItemDataRole.UserRole:
            return self._data[index.row()]
        else:
            return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):

        if role == Qt.ItemDataRole.CheckStateRole:
            if value == Qt.CheckState.Checked:
                self._checked = index

            # Notify the view that the data has changed so it repaints
            self.dataChanged.emit(index, index, [role])
            return True

        return super().setData(index, value, role)


class EffectList(QListView):
    grid_threshold = 200

    class EffectListItemDelegate(QStyledItemDelegate):
        top_padding = 4
        view_mode: QListView.ViewMode

        def __init__(self, parent: QWidget = None):
            super().__init__(parent)

        def initStyleOption(self, option, index):
            super().initStyleOption(option, index)
            # Remove the 'HasCheckIndicator' feature so Qt doesn't draw the box
            option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator

        def is_list_mode(self):
            return self.parent().viewMode() == QListView.ViewMode.ListMode

        def is_grid_mode(self):
            return self.parent().viewMode() == QListView.ViewMode.IconMode

        def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
            # 1. Initialize the style option
            self.initStyleOption(option, index)

            effect_mp3 = index.data(Qt.ItemDataRole.UserRole)

            check_state = index.data(Qt.ItemDataRole.CheckStateRole)
            if check_state == Qt.CheckState.Checked:
                # Change background for checked items
                painter.save()
                painter.setBrush(app_theme.get_green_brush(50))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(option.rect.adjusted(1, 1, -1, -1))
                painter.restore()

                # Make text bold for checked items
                option.font.setBold(True)

            if self.is_grid_mode() and effect_mp3 is not None and effect_mp3.cover is not None:
                option.rect.setTop(option.rect.top() + self.top_padding)

                # 2. Draw the selection highlight/background
                # option.widget.style().drawControl(
                #     option.widget.style().ControlElement.CE_ItemViewItem,
                #     option, painter, option.widget
                # )

                # 3. Define the drawing area (the icon rectangle)
                # We use option.rect to get the full space for this item
                rect = option.rect

                if check_state == Qt.CheckState.Checked:
                    painter.setBrush(option.palette.color(QPalette.ColorRole.Highlight))
                    painter.drawRoundedRect(rect, 4.0, 4.0)

                # 4. Draw the Icon
                icon = option.icon
                if icon:
                    # Scale icon to fit the rect
                    icon_size = self.parent().iconSize()
                    icon_rect = QRect(
                        rect.left() + (rect.width() - icon_size.width()) // 2,
                        rect.top() + (rect.height() - icon_size.height()) // 2,
                        icon_size.width(),
                        icon_size.height()
                    )
                    icon.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter)

                    rect = icon_rect

                # 5. Draw the Text on top
                text = index.data(Qt.ItemDataRole.DisplayRole)
                if text:
                    # Optional: Add a subtle shadow or background for readability
                    # painter.fillRect(rect, QColor(0, 0, 0, 100))

                    label_height = painter.fontMetrics().height() + 8
                    label_rect = QRect(rect.left(), rect.bottom() - label_height, rect.width(), label_height)

                    painter.setBrush(QColor(0, 0, 0, 100))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRect(label_rect)

                    painter.setPen(Qt.GlobalColor.white)  # Contrast color
                    painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)

                painter.restore()
            else:
                super().paint(painter, option, index)

        def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
            # IMPORTANT: You must increase the size hint,
            # otherwise the bottom of your text will be cut off!
            size = super().sizeHint(option, index)

            if self.is_grid_mode():
                effect_mp3 = index.data(Qt.ItemDataRole.UserRole)

                if option.rect.width() < EffectList.grid_threshold:
                    new_width = option.rect.width()
                else:
                    new_width = (option.rect.width() // 2)
                size.setWidth(new_width)

                if effect_mp3 is not None and effect_mp3.cover is not None:
                    size.setHeight(size.height() + self.top_padding)
                else:
                    size.setHeight(48)
            return size

    def __init__(self, list_mode: QListView.ViewMode = QListView.ViewMode.ListMode, parent=None):
        super().__init__(parent)

        self.setItemDelegate(EffectList.EffectListItemDelegate(parent=self))

        self.table_model = EffectTableModel()
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setDynamicSortFilter(True)
        self.proxy_model.setSourceModel(self.table_model)
        self.setModel(self.proxy_model)

        self.auto_search_helper = AutoSearchHelper(self.proxy_model, self)

        if list_mode == QListView.ViewMode.ListMode:
            self.set_list_view()
        else:
            self.set_grid_view()

    def load_effects(self, data: list[Mp3Entry]):
        self.table_model = EffectTableModel(data)
        self.proxy_model.setSourceModel(self.table_model)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.calculate_grid_size()

    def calculate_grid_size(self):
        if self.viewMode() == QListView.ViewMode.IconMode:
            if self.width() < self.grid_threshold:
                new_width = self.width()
            elif self.width() < self.grid_threshold * 2:
                new_width = (self.width() // 2) - 10
            else:
                new_width = (self.width() // 3) - 10

            new_width = min(128 + 30, new_width)
            new_height = int(new_width * (3.0 / 4.0))
            self.setGridSize(QSize(new_width, new_height))
            self.setIconSize(QSize(new_width - 10, new_height))  # Large covers
            self.setSpacing(0)
        else:
            self.setGridSize(QSize())
            self.setIconSize(QSize(32, 32))  # Large covers
            self.setSpacing(0)

    def set_list_view(self):
        self.setViewMode(QListView.ViewMode.ListMode)
        self.setFlow(QListView.Flow.TopToBottom)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Fixed)

        self.calculate_grid_size()

        self.update()

    def set_grid_view(self):
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)

        self.calculate_grid_size()

        self.update()

    def keyPressEvent(self, event):
        if not self.auto_search_helper.keyPressEvent(event):
            super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        self.auto_search_helper.paintEvent(event)


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
        self.player_layout.setSpacing(8)

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
        progress_layout = QHBoxLayout()
        progress_layout.setObjectName("progress_layout")
        progress_layout.setSpacing(8)
        self.time_label = QLabel("00:00")
        self.progress_slider = JumpSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.setMinimumWidth(100)
        self.duration_label = QLabel("00:00")
        self.progress_slider.setTickPosition(QSlider.TickPosition.TicksAbove)
        self.progress_slider.setTickInterval(50)
        self.progress_slider.sliderReleased.connect(self.seek_position)
        self.progress_slider.valueChanged.connect(self.jump_to_position)

        progress_layout.addWidget(self.time_label)
        progress_layout.addWidget(self.progress_slider)
        progress_layout.addWidget(self.duration_label)

        self.seeker_layout.addLayout(progress_layout)

        # --- End Progress Bar ---

        controls_widget = QWidget()
        self.controls_layout = QHBoxLayout(controls_widget)
        self.controls_layout.setSpacing(8)

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
        self.btn_prev.setDefaultAction(prev_action)
        self.btn_play = QToolButton()
        self.btn_play.setProperty("class", "play")
        self.btn_play.setDefaultAction(self.play_action)
        self.btn_next = QToolButton()
        self.btn_next.setDefaultAction(next_action)

        for btn in [self.btn_prev, self.btn_play, self.btn_next]:
            btn.setFixedSize(app_theme.button_size)
            btn.setIconSize(app_theme.icon_size)

        for btn in [self.btn_prev, self.btn_next]:
            btn.setFixedSize(app_theme.button_size_small)
            btn.setIconSize(app_theme.icon_size_small)

        self.btn_repeat = RepeatButton(AppSettings.value(SettingKeys.REPEAT_MODE, 0, type=int))
        self.btn_repeat.setFixedSize(app_theme.button_size)
        self.btn_repeat.setIconSize(app_theme.icon_size)
        self.btn_repeat.value_changed.connect(self.on_repeat_mode_changed)

        self.repeat_mode_changed = self.btn_repeat.value_changed

        self.slider_vol = VolumeSlider(AppSettings.value(SettingKeys.VOLUME, 70, type=int), shortcut="Ctrl+M")
        self.slider_vol.set_button_size(app_theme.button_size_small)
        self.slider_vol.set_icon_size(app_theme.icon_size_small)
        self.slider_vol.slider_vol.setMinimumWidth(200)

        self.slider_vol.volume_changed.connect(self.adjust_volume)
        self.volume_changed = self.slider_vol.volume_changed

        self.controls_layout.addWidget(self.btn_play)
        self.controls_layout.addWidget(self.btn_prev, alignment=Qt.AlignmentFlag.AlignBottom)
        self.controls_layout.addWidget(self.btn_next, alignment=Qt.AlignmentFlag.AlignBottom)
        self.controls_layout.addSpacing(8)

        self.visualizer = Visualizer.get_visualizer(self.engine)
        if isinstance(self.visualizer, EmptyVisualizerWidget):
            self.controls_layout.addLayout(self.seeker_layout, 2)
        else:
            self.player_layout.insertLayout(0, self.seeker_layout)
            self.controls_layout.addWidget(self.visualizer, 2)

        # controls_layout.addWidget(self.visualizer, 1)
        self.controls_layout.addSpacing(8)
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
            for btn in [self.btn_prev, self.btn_play, self.btn_next, self.slider_vol.btn_volume, self.btn_repeat]:
                btn.setFixedSize(app_theme.button_size)
                btn.setIconSize(app_theme.icon_size)

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
        self.directory_tree = DirectoryTree(self.player, self.media_player)

        self.directory_layout = QVBoxLayout(self)
        self.directory_layout.setContentsMargins(0, 0, 0, 0)
        self.directory_layout.setSpacing(0)

        self.headerLabel = IconLabel(QIcon.fromTheme("files"), _("Files"))
        self.headerLabel.set_alignment(Qt.AlignmentFlag.AlignCenter)
        self.headerLabel.text_label.setStyleSheet(f"font-size: {app_theme.font_size}pt; font-weight: bold;")
        self.headerLabel.setFixedHeight(app_theme.button_height_small)

        up_view_button = QToolButton()
        up_view_button.setDefaultAction(self.directory_tree.go_parent_action)
        self.headerLabel.insert_widget(0, up_view_button)

        open_button = QToolButton()
        open_button.setDefaultAction(self.directory_tree.open_action)
        self.headerLabel.insert_widget(1, open_button)

        set_home_button = QToolButton()
        set_home_button.setDefaultAction(self.directory_tree.set_home_action)

        clear_home_button = QToolButton()
        clear_home_button.setDefaultAction(self.directory_tree.clear_home_action)

        self.headerLabel.add_widget(set_home_button)
        self.headerLabel.add_widget(clear_home_button)

        self.directory_layout.addWidget(self.headerLabel)
        self.directory_layout.addWidget(self.directory_tree)


class DirectoryTree(QTreeView):
    open = Signal(QModelIndex)

    def __init__(self, player: Player, media_player: MediaPlayer, parent=None):
        super().__init__(parent)
        self.player = player
        self.media_player = media_player
        self.setMinimumWidth(150)

        self.open_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen), _("Open"), self)
        self.open_action.triggered.connect(self.do_open_action)

        self.edit_song_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.EditPaste), _("Edit Song"), self)
        self.edit_song_action.triggered.connect(self.edit_song)

        self.analyze_file_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.Scanner), _("Analyze"))
        self.analyze_file_action.triggered.connect(self.do_analyze_file)

        self.go_parent_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.GoUp), _("Go to parent"), self)
        self.go_parent_action.triggered.connect(self.do_parent_action)

        self.set_home_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.GoHome), _("Set As Home"), self)
        self.set_home_action.triggered.connect(self.do_set_home_action)

        self.clear_home_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.EditDelete), _("Clear Home"), self)
        self.clear_home_action.triggered.connect(self.do_clear_home_action)
        self.clear_home_action.setVisible(False)

        self._source_root_index = QPersistentModelIndex()

        self.directory_model = QFileSystemModel()
        self.directory_model.setReadOnly(True)
        self.directory_model.setIconProvider(QFileIconProvider())
        self.directory_model.setRootPath("C:/")
        self.directory_model.setNameFilters(["*.mp3", "*.m3u"])
        self.directory_model.setNameFilterDisables(False)

        self.proxy_model = FileFilterProxyModel()
        self.proxy_model.setSourceModel(self.directory_model)

        self.directory_model.directoryLoaded.connect(self.on_directories_loaded)
        self.setModel(self.proxy_model)
        self.setIndentation(8)
        self.setSortingEnabled(True)
        self.setHeaderHidden(True)
        self.setColumnHidden(1, True)
        self.setColumnHidden(2, True)
        self.setColumnHidden(3, True)
        self.setAnimated(True)
        self.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.setExpandsOnDoubleClick(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.autoSearchHelper = AutoSearchHelper(self.proxy_model, self)

        # Restore expanded state
        expanded_dirs = AppSettings.value(SettingKeys.EXPANDED_DIRS, [], type=list)
        for path in expanded_dirs:
            index = self.directory_model.index(path)
            if index is not None and index.isValid():
                self.setExpanded(self.proxy_model.mapFromSource(index), True)

        self.expanded.connect(self.on_tree_expanded)
        self.collapsed.connect(self.on_tree_collapsed)
        self.doubleClicked.connect(self.double_clicked_action)

        if AppSettings.value(SettingKeys.ROOT_DIRECTORY) is not None:
            index = self.directory_model.index(AppSettings.value(SettingKeys.ROOT_DIRECTORY))
            self.setRootIndexInSource(index)
            self.clear_home_action.setVisible(True)

        self.open.connect(self.tree_load_file)

    def on_directories_loaded(self):
        self.proxy_model.beginFilterChange()

        self.proxy_model.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def selectionChanged(self, selected, deselected, /):
        if len(self.selectedIndexes()) > 0:
            self.set_home_action.setEnabled(True)
            self.open_action.setEnabled(True)
        else:
            self.set_home_action.setEnabled(False)
            self.open_action.setEnabled(False)

    def keyPressEvent(self, event):
        if self.autoSearchHelper.keyPressEvent(event):
            self._apply_proxy_root()
            self.viewport().update()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        self.autoSearchHelper.paintEvent(event)

    def setRootIndexInSource(self, source_index: QModelIndex):
        """Use this instead of setRootIndex to set your 'Home' folder."""
        self._source_root_index = QPersistentModelIndex(source_index)
        self._apply_proxy_root()

    def _apply_proxy_root(self):
        """Maps the saved source index to the current proxy state."""
        if self._source_root_index.isValid():
            proxy_idx = self.proxy_model.mapFromSource(self._source_root_index)
            self.setRootIndex(proxy_idx)
        else:
            self.setRootIndex(QModelIndex())

    def tree_load_file(self, index: QModelIndex):
        data = self.model().itemData(index)
        file_info: QFileInfo = data[QFileSystemModel.Roles.FileInfoRole]
        if file_info.isDir():
            self.media_player.load_directory(file_info.filePath())
        elif file_info.suffix() in ("m3u", "M3U"):
            self.media_player.load_playlist(file_info.filePath())
        else:
            entry = parse_mp3(Path(file_info.filePath()))
            self.player.play_track(entry, -1)

    def mp3_data(self, index: QModelIndex):
        data = self.model().itemData(index)
        file_info: QFileInfo = data[QFileSystemModel.Roles.FileInfoRole]
        if file_info.isDir() or file_info.suffix() in ("m3u", "M3U"):
            return None
        else:
            return parse_mp3(Path(file_info.filePath()))

    def edit_song(self):
        data: Mp3Entry = self.mp3_data(self.selectionModel().currentIndex())
        dialog = EditSongDialog(data, self)
        if dialog.exec():
            if self.selectionModel().currentIndex().row() >= 0:
                self.update()

    def show_context_menu(self, point):
        # model_index = self.indexAt(point)

        menu = QMenu(self)

        menu.addAction(self.open_action)

        #
        datas = [self.mp3_data(model_index) for model_index in self.selectionModel().selectedRows()]
        datas = [data for data in datas if data is not None]
        if len(datas) > 0:
            menu.addAction(self.edit_song_action)
            if AppSettings.value(SettingKeys.VOXALYZER_URL,"",type=str) !="":
                menu.addAction(self.analyze_file_action)

            add_to_playlist = QMenu(_("Add to playlist"), icon=QIcon.fromTheme(QIcon.ThemeIcon.ListAdd))

            add_new_action = add_to_playlist.addAction(_("<New Playlist>"))
            add_new_action.setIcon(QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical))
            add_new_action.triggered.connect(functools.partial(self.media_player.pick_new_playlist, datas))
            add_to_playlist.addAction(add_new_action)

            for playlist in self.media_player.get_playlists():
                add_action = add_to_playlist.addAction(Path(playlist).name.removesuffix(".m3u").removesuffix(".M3U"))
                add_action.setIcon(QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical))
                add_action.triggered.connect(functools.partial(self.media_player.add_to_playlist, playlist, datas))

            menu.addMenu(add_to_playlist)

        menu.addSeparator()

        #
        menu.addAction(self.go_parent_action)
        menu.addAction(self.set_home_action)
        menu.addAction(self.clear_home_action)

        #
        menu.show()
        menu.exec(self.mapToGlobal(point))

    def do_parent_action(self):
        if self.rootIndex().isValid() and self.rootIndex().parent() is not None:
            index = self.rootIndex().parent()
            self._set_root_index(index)

    def do_open_action(self):
        index = self.selectedIndexes()[0]
        self.open.emit(index)

    def do_analyze_file(self):
        for index in self.selectedIndexes():
            source_index = self.proxy_model.mapToSource(index)
            file_path = self.directory_model.filePath(source_index)
            self.media_player.analyze_file(file_path)

    def double_clicked_action(self, index):
        source_index = self.proxy_model.mapToSource(index)
        file_info = self.directory_model.fileInfo(source_index)
        if file_info.isFile():
            self.open.emit(index)

    def _set_root_index(self, root_index: QModelIndex):
        if root_index.isValid():
            source_index = self.proxy_model.mapToSource(root_index)
            AppSettings.setValue(SettingKeys.ROOT_DIRECTORY, self.directory_model.filePath(source_index))
            self.setRootIndexInSource(source_index)
            self.clear_home_action.setVisible(True)
            self.go_parent_action.setVisible(True)
        else:
            AppSettings.setValue(SettingKeys.ROOT_DIRECTORY, None)
            self.setRootIndexInSource(QModelIndex())
            self.clear_home_action.setVisible(False)
            self.go_parent_action.setVisible(False)

    def do_set_home_action(self):
        if len(self.selectedIndexes()) == 0:
            return

        index = self.selectedIndexes()[0]
        source_index = self.proxy_model.mapToSource(index)
        file_info = self.directory_model.fileInfo(source_index)

        if file_info.isDir():
            root_index = index
        else:
            root_index = index.parent()

        self._set_root_index(root_index)

    def do_clear_home_action(self):
        AppSettings.setValue(SettingKeys.ROOT_DIRECTORY, None)
        self._set_root_index(QModelIndex())

    def on_tree_expanded(self, index: QModelIndex):
        source_index = self.proxy_model.mapToSource(index)
        path = self.directory_model.filePath(source_index)
        expanded_dirs = AppSettings.value(SettingKeys.EXPANDED_DIRS, [], type=list)
        if path not in expanded_dirs:
            expanded_dirs.append(path)
            AppSettings.setValue(SettingKeys.EXPANDED_DIRS, expanded_dirs)

    def on_tree_collapsed(self, index: QModelIndex):
        source_index = self.proxy_model.mapToSource(index)
        path = self.directory_model.filePath(source_index)
        expanded_dirs = AppSettings.value(SettingKeys.EXPANDED_DIRS, [], type=list)
        if path in expanded_dirs:
            expanded_dirs.remove(path)
            AppSettings.setValue(SettingKeys.EXPANDED_DIRS, expanded_dirs)


class SongTableModel(QAbstractTableModel):
    FAV_COL = 0
    FILE_COL = 1
    TITLE_COL = 2
    ARTIST_COL = 3
    ALBUM_COL = 4
    GENRE_COL = 5
    BPM_COL = 6
    SCORE_COL = 7
    CAT_COL = 8

    filter_config: FilterConfig = FilterConfig()

    def __init__(self, data: list[Mp3Entry] = []):
        super(SongTableModel, self).__init__()
        self._data = [song for song in data if song is not None]

    def get_category(self, index: QModelIndex | int):
        if isinstance(index, int):
            return available_categories[index - SongTableModel.CAT_COL].name
        else:
            return available_categories[index.column() - SongTableModel.CAT_COL].name

    def set_filter_values(self, _config: FilterConfig):
        self.beginResetModel()
        self.filter_config = _config
        self.endResetModel()

    def setData(self, index: QModelIndex | QPersistentModelIndex, value, /, role: int = ...) -> bool:
        if role == Qt.ItemDataRole.UserRole:
            self._data[index.row()] = value
        elif role == Qt.ItemDataRole.EditRole:
            if index.column() == SongTableModel.FAV_COL:
                data = index.data(Qt.ItemDataRole.UserRole)
                data.favorite = value
                update_mp3_favorite(data.path, bool(value))
                return True
            elif index.column() == SongTableModel.TITLE_COL:
                data = index.data(Qt.ItemDataRole.UserRole)
                data.title = value
                update_mp3_title(data.path, value)
                return True
            elif index.column() == SongTableModel.ALBUM_COL:
                data = index.data(Qt.ItemDataRole.UserRole)
                data.album = value
                update_mp3_album(data.path, value)
            elif index.column() == SongTableModel.ARTIST_COL:
                data = index.data(Qt.ItemDataRole.UserRole)
                data.album = value
                update_mp3_artist(data.path, value)
            elif index.column() == SongTableModel.GENRE_COL:
                data = index.data(Qt.ItemDataRole.UserRole)
                data.genres = list(map(str.strip, value.split(",")))
                update_mp3_genre(data.path, data.genres)
            elif index.column() == SongTableModel.BPM_COL:
                data = index.data(Qt.ItemDataRole.UserRole)
                if value == "" or value is None:
                    data.bpm = None
                else:
                    data.bpm = int(value)
                update_mp3_bpm(data.path, data.bpm)
            elif index.column() >= SongTableModel.CAT_COL:
                data = index.data(Qt.ItemDataRole.UserRole)

                category = self.get_category(index)

                new_value: int | float | None
                try:
                    if value == "" or value is None:
                        new_value = None
                    else:
                        if category == _(CAT_VALENCE) or category == _(CAT_AROUSAL):
                            new_value = float(value)
                        else:
                            new_value = int(value)
                except ValueError:
                    logger.error("Invalid value for category {0}: {1}", category, value)
                    return False

                # Update file_data_list
                has_changes = False

                if new_value is None:
                    if data.categories is not None and category in data.categories:
                        data.categories[category] = None
                        has_changes = True
                elif new_value != data.get_category_value(category):
                    data.categories[category] = new_value
                    has_changes = True
                else:
                    return False

                # Update MP3 tags

                try:
                    if has_changes:
                        update_mp3_category(data.path, category, new_value)
                except Exception as e:
                    traceback.print_exc()
                    logger.error("Failed to update tags: {0}", e)
                    QMessageBox.warning(self, _("Update Error"), _("Failed to update tags: {0}").format(e))

                return has_changes

        return False

    def addRow(self, data: Mp3Entry):
        row_position = self.rowCount()

        # 2. Notify the view that rows are about to be inserted
        self.beginInsertRows(QModelIndex(), row_position, row_position)
        self._data.append(data)
        self.endInsertRows()

    def addRows(self, data: list[Mp3Entry]):
        row_position = self.rowCount()

        # 2. Notify the view that rows are about to be inserted
        self.beginInsertRows(QModelIndex(), row_position, row_position + len(data) - 1)
        self._data.extend(data)
        self.endInsertRows()

    def removeRow(self, row: int, /, parent: QModelIndex | QPersistentModelIndex = ...) -> bool:
        if 0 <= row < len(self._data):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._data[row]
            self.endRemoveRows()
            return True
        return False

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = ...):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.SizeHintRole:

            if AppSettings.value(SettingKeys.COLUMN_SUMMARY_VISIBLE, True, type=bool):
                height = 56
            else:
                height = 28

            if index.column() == SongTableModel.FAV_COL:
                return QSize(20, height)
            elif index.column() == SongTableModel.FILE_COL:
                return QSize(300, height)
            else:
                return QSize(40, height)

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() >= SongTableModel.SCORE_COL or index.column() == SongTableModel.BPM_COL:
                return Qt.AlignmentFlag.AlignCenter
        elif role == Qt.ItemDataRole.BackgroundRole:
            if index.column() == SongTableModel.SCORE_COL:
                score = index.data(Qt.ItemDataRole.DisplayRole)
                return _get_score_background_brush(score)
            elif index.column() >= SongTableModel.GENRE_COL:
                value = index.data(Qt.ItemDataRole.UserRole)
                return _get_genre_background_brush(self.filter_config.genres, value.genres)
            elif index.column() >= SongTableModel.CAT_COL:
                value = index.data(Qt.ItemDataRole.DisplayRole)
                category = self.get_category(index)
                return _get_category_background_brush(self.filter_config.get_category(category, None), value)
            elif index.column() >= SongTableModel.BPM_COL:
                value = index.data(Qt.ItemDataRole.DisplayRole)
                return _get_bpm_background_brush(self.filter_config.bpm, value)
        elif role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            data = index.data(Qt.ItemDataRole.UserRole)
            if data is None:
                return None

            if index.column() == SongTableModel.FAV_COL:
                return data.favorite
            elif index.column() == SongTableModel.FILE_COL:
                name = data.title if AppSettings.value(SettingKeys.TITLE_INSTEAD_OF_FILE_NAME, False,type=bool) else data.name
                if data.summary:
                    return name + " " + data.summary
                else:
                    return name
            elif index.column() == SongTableModel.TITLE_COL:
                return data.title
            elif index.column() == SongTableModel.ARTIST_COL:
                return data.artist
            elif index.column() == SongTableModel.ALBUM_COL:
                return data.album
            elif index.column() == SongTableModel.GENRE_COL:
                return ", ".join(data.genres) if data.genres else ""
            elif index.column() == SongTableModel.BPM_COL:
                return data.bpm
            elif index.column() == SongTableModel.SCORE_COL:
                data = index.data(Qt.ItemDataRole.UserRole)
                return _calculate_score(self.filter_config, data)
            elif index.column() >= SongTableModel.CAT_COL:
                category = self.get_category(index)
                return data.get_category_value(category)
            else:
                return None

        elif role == Qt.ItemDataRole.UserRole:
            return self._data[index.row()]
        return None

    def rowCount(self, /, parent: QModelIndex | QPersistentModelIndex = ...) -> int:
        return len(self._data)

    def columnCount(self, /, parent: QModelIndex | QPersistentModelIndex = ...) -> int:
        return SongTableModel.CAT_COL + len(available_categories)

    def headerData(self, section: int, orientation: Qt.Orientation, /, role: int = ...):
        if role == Qt.ItemDataRole.DisplayRole:
            if section == SongTableModel.FAV_COL:
                return ""
            elif section == SongTableModel.FILE_COL:
                return _("File")
            elif section == SongTableModel.TITLE_COL:
                return _("Title")
            elif section == SongTableModel.ARTIST_COL:
                return _("Artist")
            elif section == SongTableModel.ALBUM_COL:
                return _("Album")
            elif section == SongTableModel.GENRE_COL:
                return _("Genre")
            elif section == SongTableModel.BPM_COL:
                return _("BPM")
            elif section == SongTableModel.SCORE_COL:
                return _("Score")
            else:
                return self.get_category(section)

        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex, /) -> Qt.ItemFlag:
        if index.column() == SongTableModel.FAV_COL or index.column() == SongTableModel.SCORE_COL or index.column() == SongTableModel.FILE_COL:
            return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        else:
            return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable


class SongTable(QTableView):
    play_track = Signal(int, Mp3Entry)

    playlist: os.PathLike[str] = None
    directory: os.PathLike[str] = None

    table_model: SongTableModel
    proxy_model: QSortFilterProxyModel

    class CategoryDelegate(QStyledItemDelegate):

        def setModelData(self, editor, model, index):
            # Grab the text directly from the editor
            text = editor.text()
            if not text:
                # Explicitly set None/Null in the model if the field is empty
                model.setData(index, None, Qt.ItemDataRole.EditRole)
            else:
                # Otherwise, use the standard behavior
                super().setModelData(editor, model, index)

    class StarDelegate(QStyledItemDelegate):
        star_rating = StarRating()

        def __init__(self, parent: QObject = None):
            super().__init__(parent)

        def paint(self, painter, option, index):
            fav_icon_color = app_theme.get_green_brush()
            self.star_rating.paint(painter, index.data(), option.rect, option.palette, fav_icon_color)

        def sizeHint(self, option, index):
            return self.star_rating.size_hint()

    class LabelItemDelegate(QStyledItemDelegate):
        _size = QSize(300, 40)

        def __init__(self, parent: QObject = None):
            super().__init__(parent)

        def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
            return self._size

        def paint(self, painter, option: QStyleOptionViewItem, index, /):
            painter.setRenderHint(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
            data = index.model().data(index, Qt.ItemDataRole.UserRole)

            content_rect = option.rect.adjusted(6, 4, -6, -4)
            pen = painter.pen()

            # draw tags
            tags_font = QFont(option.font)
            tags_font.setBold(False)
            tags_font.setPointSizeF(app_theme.font_size_small)

            fm = QFontMetrics(tags_font)
            painter.setFont(tags_font)

            tag_left = content_rect.right()
            tag_top = content_rect.top() + 2

            green_tags = [x for x in data.all_tags if x in selected_tags]
            red_tags = [x for x in data.all_tags if x not in selected_tags]

            for tag in green_tags + red_tags:

                bounding_rect = fm.boundingRect(tag)

                tag_padding = 3

                tags_rect = QRect(tag_left - bounding_rect.width(), tag_top, bounding_rect.width(),
                                  bounding_rect.height())
                tags_rect.adjust(-tag_padding * 2, -tag_padding, tag_padding * 2, tag_padding)

                if tag in selected_tags:
                    painter.setBrush(app_theme.get_green_brush())
                else:
                    painter.setBrush(option.palette.highlight())

                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(tags_rect, 6.0, 6.0)

                pen.setColor(option.palette.color(QPalette.ColorRole.HighlightedText))

                painter.setPen(pen)
                tag_padding = 2
                tags_rect.adjust(tag_padding * 2, tag_padding, -tag_padding * 2, -tag_padding)
                painter.drawText(tags_rect, Qt.AlignmentFlag.AlignRight, tag)

                tag_left = tags_rect.left() - 12

                if tag_left < 200:
                    break

            # draw rest

            color = option.palette.color(
                QPalette.ColorRole.BrightText) if option.state & QStyle.StateFlag.State_Selected else option.palette.color(
                QPalette.ColorRole.WindowText)

            pen.setColor(color)
            painter.setPen(pen)

            title_font = QFont(option.font)
            if AppSettings.value(SettingKeys.COLUMN_SUMMARY_VISIBLE, True, type=bool):
                title_font.setBold(True)
            title_font.setPointSizeF(app_theme.font_size)

            fm = QFontMetrics(title_font)

            title_rect = QRect(content_rect)
            title_rect.setRight(tag_left)
            title_rect.setHeight(fm.height())

            painter.save()

            painter.setFont(title_font)

            title = data.title if AppSettings.value(SettingKeys.TITLE_INSTEAD_OF_FILE_NAME, False,
                                                    type=bool) and data.title is not None and data.title != "" else data.name
            painter.drawText(title_rect, title)

            if data.summary and AppSettings.value(SettingKeys.COLUMN_SUMMARY_VISIBLE, True, type=bool):
                summary_font = QFont(option.font)
                summary_font.setBold(False)
                summary_font.setPointSizeF(app_theme.font_size_small)
                painter.setFont(summary_font)

                summary_rect = QRect(content_rect)
                summary_rect.setTop(title_rect.bottom())
                summary_rect.setBottom(content_rect.bottom())

                painter.drawText(summary_rect, Qt.TextFlag.TextWordWrap, data.summary)

            painter.restore()

    def __init__(self,_analyzer: Analyzer, _media_player: MediaPlayer):
        super().__init__()
        self.setAcceptDrops(True)

        self.table_model = SongTableModel()
        self.media_player = _media_player
        self.analyzer = _analyzer

        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setDynamicSortFilter(True)
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.setFilterRole(Qt.ItemDataRole.DisplayRole)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(SongTableModel.FILE_COL)

        self.setModel(self.proxy_model)
        self.setColumnWidth(SongTableModel.FAV_COL, 48)
        self.setColumnWidth(SongTableModel.FILE_COL, 400)
        self.setColumnWidth(SongTableModel.SCORE_COL, 80)
        self.resizeColumnToContents(SongTableModel.TITLE_COL)
        self.resizeColumnToContents(SongTableModel.ALBUM_COL)
        self.resizeColumnToContents(SongTableModel.GENRE_COL)
        self.setColumnWidth(SongTableModel.BPM_COL, 64)
        self.resizeColumnToContents(SongTableModel.ARTIST_COL)

        self.auto_search_helper = AutoSearchHelper(self.proxy_model, self)

        self.setSortingEnabled(False)

        self.horizontalHeader().setSectionResizeMode(SongTableModel.FAV_COL, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(SongTableModel.SCORE_COL, QHeaderView.ResizeMode.ResizeToContents)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.setSortingEnabled(True)

        self.verticalHeader().setVisible(False)

        if AppSettings.value(SettingKeys.COLUMN_SUMMARY_VISIBLE, True, type=bool):
            self.verticalHeader().setDefaultSectionSize(56)
        else:
            self.verticalHeader().setDefaultSectionSize(28)

        self.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self.show_header_context_menu)
        self.horizontalHeader().setStretchLastSection(True)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.setItemDelegateForColumn(SongTableModel.FILE_COL, SongTable.LabelItemDelegate(self))
        self.setItemDelegateForColumn(SongTableModel.FAV_COL, SongTable.StarDelegate())

        self.setStyleSheet('QTableView::item {padding: 0px 5px;}')
        self.doubleClicked.connect(self.on_table_double_click)

    def show_header_context_menu(self, point):
        menu = QMenu(self)

        # Faviroite
        fav_action = QAction(_("Favorite"), self)
        fav_action.setCheckable(True)
        fav_action.setChecked(AppSettings.value(SettingKeys.COLUMN_FAVORITE_VISIBLE, True, type=bool))
        fav_action.triggered.connect(
            lambda checked: self.toggle_column_setting(SettingKeys.COLUMN_FAVORITE_VISIBLE, checked))
        menu.addAction(fav_action)

        # Title
        title_action = QAction(_("Title"), self)
        title_action.setCheckable(True)
        title_action.setChecked(AppSettings.value(SettingKeys.COLUMN_TITLE_VISIBLE, False, type=bool))
        title_action.triggered.connect(
            lambda checked: self.toggle_column_setting(SettingKeys.COLUMN_TITLE_VISIBLE, checked))
        menu.addAction(title_action)

        # Artist
        artist_action = QAction(_("Artist"), self)
        artist_action.setCheckable(True)
        artist_action.setChecked(AppSettings.value(SettingKeys.COLUMN_ARTIST_VISIBLE, False, type=bool))
        artist_action.triggered.connect(
            lambda checked: self.toggle_column_setting(SettingKeys.COLUMN_ARTIST_VISIBLE, checked))
        menu.addAction(artist_action)

        # Album
        album_action = QAction(_("Album"), self)
        album_action.setCheckable(True)
        album_action.setChecked(AppSettings.value(SettingKeys.COLUMN_ALBUM_VISIBLE, False, type=bool))
        album_action.triggered.connect(
            lambda checked: self.toggle_column_setting(SettingKeys.COLUMN_ALBUM_VISIBLE, checked))
        menu.addAction(album_action)

        # Genre
        genre_action = QAction(_("Genre"), self)
        genre_action.setCheckable(True)
        genre_action.setChecked(AppSettings.value(SettingKeys.COLUMN_GENRE_VISIBLE, False, type=bool))
        genre_action.triggered.connect(
            lambda checked: self.toggle_column_setting(SettingKeys.COLUMN_GENRE_VISIBLE, checked))
        menu.addAction(genre_action)

        bpm_action = QAction(_("BPM (Beats per Minute)"), self)
        bpm_action.setCheckable(True)
        bpm_action.setChecked(AppSettings.value(SettingKeys.COLUMN_BPM_VISIBLE, False, type=bool))
        bpm_action.triggered.connect(
            lambda checked: self.toggle_column_setting(SettingKeys.COLUMN_BPM_VISIBLE, checked))
        menu.addAction(bpm_action)

        score_action = QAction(_("Score"), self)
        score_action.setCheckable(True)
        score_action.setChecked(AppSettings.value(SettingKeys.COLUMN_SCORE_VISIBLE, True, type=bool))
        score_action.triggered.connect(
            lambda checked: self.toggle_column_setting(SettingKeys.COLUMN_SCORE_VISIBLE, checked))
        menu.addAction(score_action)

        menu.addSeparator()

        # Summary
        summary_action = QAction(_("Summary"), self)
        summary_action.setCheckable(True)
        summary_action.setChecked(AppSettings.value(SettingKeys.COLUMN_SUMMARY_VISIBLE, True, type=bool))
        summary_action.triggered.connect(
            lambda checked: self.toggle_column_setting(SettingKeys.COLUMN_SUMMARY_VISIBLE, checked))
        menu.addAction(summary_action)

        menu.addSeparator()

        # Dynamic Columns
        dynamic_action = QAction(_("Dynamic Columns"), self)
        dynamic_action.setCheckable(True)
        dynamic_action.setChecked(AppSettings.value(SettingKeys.DYNAMIC_TABLE_COLUMNS, False, type=bool))
        dynamic_action.triggered.connect(
            lambda checked: self.toggle_column_setting(SettingKeys.DYNAMIC_TABLE_COLUMNS, checked))
        menu.addAction(dynamic_action)

        menu.exec(self.horizontalHeader().mapToGlobal(point))

    def toggle_column_setting(self, key, checked):
        AppSettings.setValue(key, checked)
        self.update_category_column_visibility()
        if key == SettingKeys.COLUMN_SUMMARY_VISIBLE:
            self.viewport().update()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Enter:
            index = self.selectionModel().currentIndex()
            self.play_track.emit(index.row(), index.data(Qt.ItemDataRole.UserRole))
            return
        elif event.key() == Qt.Key.Key_Delete:
            self.remove_items()
            return
        elif not self.auto_search_helper.keyPressEvent(event):
            super().keyPressEvent(event)

    def paintEvent(self, event):
        # 1. Let the standard TreeView draw the folders/files first
        super().paintEvent(event)
        self.auto_search_helper.paintEvent(event)

    def on_table_double_click(self, index: QModelIndex):
        if index.column() == SongTableModel.FILE_COL:
            data = self.mp3_data(index.row())
            self.play_track.emit(index.row(), data)
        elif index.column() == SongTableModel.FAV_COL:
            data = self.mp3_data(index.row())
            data.favorite = not data.favorite
            update_mp3_favorite(data.path, data.favorite)
            self.repaint()

    def refresh_item(self, file_path: str | os.PathLike[str]):
        data = parse_mp3(Path(file_path))
        index = self.index_of(data)
        if index >= 0:
            self.model().setData(self.model().index(index, SongTableModel.FILE_COL), data, Qt.ItemDataRole.UserRole)

    def populate_table(self, table_data: list[Mp3Entry]):
        self.table_model = SongTableModel(table_data)
        self.proxy_model.setSourceModel(self.table_model)

        self.update_category_column_visibility()

    def is_column_visible(self, category: str):
        if AppSettings.value(SettingKeys.DYNAMIC_TABLE_COLUMNS, False, type=bool):
            value = self.table_model.filter_config.get_category(category, None)
            if AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool) and (category == _(CAT_VALENCE) or category == _(CAT_AROUSAL)):
                return value is not None and value >= 0 and value != 5
            else:
                return value is not None and value >= 0
        else:
            return True

    def update_category_column_visibility(self):
        self.setColumnHidden(SongTableModel.FAV_COL, not AppSettings.value(SettingKeys.COLUMN_FAVORITE_VISIBLE, True, type=bool))
        self.setColumnHidden(SongTableModel.TITLE_COL, not AppSettings.value(SettingKeys.COLUMN_TITLE_VISIBLE, False, type=bool))
        self.setColumnHidden(SongTableModel.SCORE_COL, not AppSettings.value(SettingKeys.COLUMN_SCORE_VISIBLE, True, type=bool))
        self.setColumnHidden(SongTableModel.ARTIST_COL, not AppSettings.value(SettingKeys.COLUMN_ARTIST_VISIBLE, False, type=bool))
        self.setColumnHidden(SongTableModel.ALBUM_COL, not AppSettings.value(SettingKeys.COLUMN_ALBUM_VISIBLE, False, type=bool))
        self.setColumnHidden(SongTableModel.GENRE_COL, not AppSettings.value(SettingKeys.COLUMN_GENRE_VISIBLE, False, type=bool))
        self.setColumnHidden(SongTableModel.BPM_COL, not AppSettings.value(SettingKeys.COLUMN_BPM_VISIBLE, False, type=bool))

        if AppSettings.value(SettingKeys.DYNAMIC_SCORE_COLUMN, True, type=bool) and (
                self.table_model.filter_config is None or self.table_model.filter_config.empty()):
            self.setColumnHidden(SongTableModel.SCORE_COL, True)

        for col, category in enumerate(available_categories):
            self.setColumnHidden(SongTableModel.CAT_COL + col, not self.is_column_visible(category.name))

        if AppSettings.value(SettingKeys.COLUMN_SUMMARY_VISIBLE, True, type=bool):
            self.verticalHeader().setDefaultSectionSize(56)
        else:
            self.verticalHeader().setDefaultSectionSize(28)

    def mp3_datas(self) -> list[Mp3Entry]:
        if self.model() is not None:
            return [self.mp3_data(row) for row in range(self.rowCount())]
        else:
            return []

    def index_of(self, entry: Mp3Entry) -> int:
        for row in range(self.rowCount()):
            if self.mp3_data(row).path == entry.path:
                return row
        return -1

    def mp3_data(self, row: int) -> Mp3Entry | None:
        index = self.model().index(row, SongTableModel.FILE_COL)
        return self.model().data(index, Qt.ItemDataRole.UserRole)

    def rowCount(self) -> int:
        return 0 if self.model() is None else self.model().rowCount()

    def columnCount(self) -> int:
        return 0 if self.model() is None else self.model().columnCount()

    def analyze_files(self):
        for model_index in self.selectionModel().selectedRows():
            data = self.mp3_data(model_index.row())
            self.analyzer.process(data.path)

    def edit_song(self):
        data: Mp3Entry = self.selectionModel().currentIndex().data(Qt.ItemDataRole.UserRole)
        dialog = EditSongDialog(data, self)
        if dialog.exec():
            row = self.index_of(data)
            if row >= 0:
                self.model().setData(self.model().index(row, 0), data, Qt.ItemDataRole.UserRole)
                self.update()

    def remove_items(self):
        datas = []
        for model_index in reversed(self.selectionModel().selectedRows()):
            datas.append(self.mp3_data(model_index.row()))

            # We must map the proxy index back to the source index
            source_index = self.proxy_model.mapToSource(model_index)
            # Now use the source row to remove from the source model

            self.table_model.removeRow(source_index.row())

        if self.playlist is not None:
            remove_m3u(datas, self.playlist)

    def show_context_menu(self, point):
        # index = self.indexAt(point)
        menu = QMenu(self)

        edit_name_action = menu.addAction(QIcon.fromTheme(QIcon.ThemeIcon.EditPaste), _("Edit Song"))
        edit_name_action.triggered.connect(self.edit_song)

        if AppSettings.value(SettingKeys.VOXALYZER_URL, "", type=str) != "":
            analyze_action = menu.addAction(QIcon.fromTheme(QIcon.ThemeIcon.Scanner), _("Analyze"))
            analyze_action.triggered.connect(self.analyze_files)

        menu.addSeparator()

        datas = [self.mp3_data(model_index.row()) for model_index in self.selectionModel().selectedRows()]
        add_to_playlist = QMenu(_("Add to playlist"), icon=QIcon.fromTheme(QIcon.ThemeIcon.ListAdd))

        add_new_action = add_to_playlist.addAction(_("<New Playlist>"))
        add_new_action.setIcon(QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical))
        add_new_action.triggered.connect(functools.partial(self.media_player.pick_new_playlist, datas))
        add_to_playlist.addAction(add_new_action)

        for playlist in self.media_player.get_playlists():
            if self.playlist == playlist:
                continue
            add_action = add_to_playlist.addAction(Path(playlist).name.removesuffix(".m3u").removesuffix(".M3U"))
            add_action.setIcon(QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical))
            add_action.triggered.connect(functools.partial(self.media_player.add_to_playlist, playlist, datas))

        menu.addMenu(add_to_playlist)

        remove_action = menu.addAction(QIcon.fromTheme(QIcon.ThemeIcon.EditDelete), _("Remove from playlist") if self.playlist else _("Remove"))
        remove_action.triggered.connect(self.remove_items)

        menu.show()
        menu.exec(self.mapToGlobal(point))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            if self.playlist:
                event.accept()
            else:
                event.ignore()
        elif event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            if self.playlist:
                event.accept()
            else:
                event.ignore()
        elif event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            if self.playlist:
                event.accept()
                songs = [parse_mp3(Path(url.toLocalFile())) for url in event.mimeData().urls()]
                songs = [song for song in songs if song is not None]
                append_m3u(songs, self.playlist)
                self.table_model.addRows(songs)
            else:
                event.ignore()
        elif event.mimeData().hasText():
            tag = event.mimeData().text()
            index = self.indexAt(event.position().toPoint())
            if index.isValid():
                data = index.data(Qt.ItemDataRole.UserRole)
                if data and tag not in data.tags:
                    data.add_tag(tag)
                    update_mp3_tags(data.path, data.tags)

                    file_col_index = index.siblingAtColumn(SongTableModel.FILE_COL)
                    self.model().dataChanged.emit(file_col_index, file_col_index, [Qt.ItemDataRole.DisplayRole])

            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class FilterWidget(QWidget):
    values_changed = Signal()

    sliders: dict[MusicCategory, CategoryWidget] = {}

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player

        self.russel_widget = RussellEmotionWidget()
        self.russel_widget.setMaximumSize(QSize(250, 250))
        self.russel_widget.setMinimumSize(QSize(160, 160))
        self.russel_widget.valueChanged.connect(self.on_russel_changed)
        self.russel_widget.mouseReleased.connect(self.on_russel_released)

        self.bpm_widget = BPMSlider()
        self.bpm_widget.value_changed.connect(self.on_bpm_changed)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)

        save_preset_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.DocumentSaveAs), _("Save as Preset"), self)
        save_preset_action.triggered.connect(self.save_preset_action)
        self.addAction(save_preset_action)

        clear_preset_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.EditClear), _("Clear Values"), self)
        clear_preset_action.triggered.connect(self.clear_sliders)
        self.addAction(clear_preset_action)

        reset_preset_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.ViewRestore), _("Reset Presets"), self)
        reset_preset_action.triggered.connect(self.reset_preset_action)
        self.addAction(reset_preset_action)

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
        tags_genres_layout.setContentsMargins(0,0,0,0)
        tags_genres_layout.setSpacing(4)

        self.tags_layout = FlowLayout()
        self.tags_layout.setObjectName("tags_layout")

        label_font =QFont()
        label_font.setBold(True)

        tags_label = QLabel(_("Tags"))
        tags_label.setFont(label_font)
        tags_label.setStyleSheet("font-size:7pt; text-transform:uppercase")
        tags_genres_layout.addWidget(tags_label)
        tags_genres_layout.addLayout(self.tags_layout)

        self.genres_layout = FlowLayout()
        self.genres_layout.setObjectName("genres_layout")

        genres_label = QLabel(_("Genres"))
        genres_label.setFont(label_font)
        genres_label.setStyleSheet("font-size:7pt; text-transform:uppercase")
        tags_genres_layout.addWidget(genres_label)
        tags_genres_layout.addLayout(self.genres_layout)

        self.update_sliders()
        self.update_tags()
        self.update_genres()
        self.update_presets()

    def build_sliders(self, categories: list[MusicCategory], group: str = None):
        sliders_widget = QWidget()
        russle_layout = QHBoxLayout(sliders_widget)

        sliders_layout = QVBoxLayout()
        sliders_layout.setObjectName("sliders_layout")
        sliders_layout.setContentsMargins(4, 0, 4, 0)

        if group is None or group == '':
            russle_layout.addWidget(self.russel_widget, 0)
            self.russel_widget.setVisible(AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool))

        russle_layout.addLayout(sliders_layout, 1)

        if group is None or group == '':
            russle_layout.addWidget(self.bpm_widget, 0)
            self.bpm_widget.setVisible(AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool))

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

        self.update_sliders()

    def toggle_category_widgets(self):
        AppSettings.setValue(SettingKeys.CATEGORY_WIDGETS, not AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool))
        self.update_sliders()

    def toggle_presets(self):
        AppSettings.setValue(SettingKeys.PRESET_WIDGETS, not AppSettings.value(SettingKeys.PRESET_WIDGETS, True, type=bool))
        self.update_presets()

    def toggle_bpm_widget(self):
        AppSettings.setValue(SettingKeys.BPM_WIDGET, not AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool))
        self.bpm_widget.setVisible(AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool))
        self.bpm_widget.set_value(0)
        # self.update_sliders()

    def toggle_tag(self, state):
        toggle = self.sender()
        tag = toggle.property("tag")
        if state == 0 and tag in selected_tags:
            selected_tags.remove(tag)
        elif tag not in selected_tags:
            selected_tags.append(tag)

        self.values_changed.emit()

    def toggle_genre(self, state):
        toggle = self.sender()
        tag = toggle.property("genre")
        if state == 0 and tag in selected_genres:
            selected_genres.remove(tag)
        elif tag not in selected_genres:
            selected_genres.append(tag)

        self.values_changed.emit()

    def update_tags(self):
        clear_layout(self.tags_layout)
        for tag in available_tags:
            toggle = ToggleSlider(checked_text=tag, unchecked_text=tag)
            toggle.setProperty("tag", tag)

            if tag in get_music_tags():
                toggle.setToolTip(get_music_tags()[tag])
            toggle.stateChanged.connect(self.toggle_tag)
            toggle.setChecked(tag in selected_tags)
            self.tags_layout.addWidget(toggle)

    def update_genres(self):
        clear_layout(self.genres_layout)

        genre_palette = QPalette(self.palette())
        genre_palette.setBrush(QPalette.ColorRole.Highlight, app_theme.get_green_brush(255))

        for genre in available_genres:
            toggle = ToggleSlider(checked_text=genre, unchecked_text=genre, draggable=False)
            toggle.setPalette(genre_palette)
            toggle.setProperty("genre", genre)
            toggle.stateChanged.connect(self.toggle_genre)
            toggle.setChecked(genre in selected_genres)
            self.genres_layout.addWidget(toggle)

    def update_tags_and_presets(self):
        self.update_tags()
        self.update_genres()
        self.update_presets()

    def update_sliders(self):
        self.russel_widget.setParent(None)
        self.bpm_widget.setParent(None)

        self.slider_tabs.clear()
        self.sliders = {}

        if not AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool) and not AppSettings.value(SettingKeys.RUSSEL_WIDGET, True,
                                                                                                          type=bool) and not AppSettings.value(
            SettingKeys.BPM_WIDGET, True, type=bool):
            self.slider_tabs.setVisible(False)
        else:
            self.slider_tabs.setVisible(True)

        if AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool):
            general_categories = [cat.key for cat in available_categories]
            categories_group = {}
            for cat in available_categories:
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
                button.setFixedHeight(app_theme.button_height_small)
                # button.setIconSize(app_theme.icon_size_small)
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
            save_preset.clicked.connect(self.save_preset_action)
            save_preset.setFixedSize(app_theme.button_size_small)
            # save_preset.setIconSize(app_theme.icon_size_small)
            self.presets_layout.addWidget(save_preset)

            clear_preset = QToolButton(icon=QIcon.fromTheme(QIcon.ThemeIcon.EditClear))
            clear_preset.clicked.connect(self.clear_sliders)
            clear_preset.setFixedSize(app_theme.button_size_small)
            # clear_preset.setIconSize(app_theme.icon_size_small)
            self.presets_layout.addWidget(clear_preset)
        else:
            self.presets_widget.setVisible(False)

    def clear_sliders(self):
        for slider in self.sliders.values():
            slider.reset(False)

        if self.russel_widget.isVisible():
            self.russel_widget.set_value(5, 5)

        selected_tags.clear()
        selected_genres.clear()
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
        global selected_tags, selected_genres
        for slider in self.sliders.values():
            slider.set_value(0, False)

        for cat, scale in preset.categories.items():
            category = get_music_category(cat)
            if category in self.sliders:
                self.sliders[category].set_value(scale, False)

        if preset.tags:
            selected_tags = preset.tags.copy()
        else:
            selected_tags = []
        self.update_tags()

        if preset.genres:
            selected_genres = preset.genres.copy()
        else:
            selected_genres = []
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
            preset = Preset(name_edit.text(), categories, selected_tags, selected_genres)
            add_preset(preset)
            self.update_presets()

    def update_russel_heatmap(self, table_data: list[Mp3Entry]):
        points = [(file.get_category_value(CAT_VALENCE), file.get_category_value(CAT_AROUSAL)) for file in table_data if file.get_category_value(CAT_VALENCE) is not None and file.get_category_value(CAT_AROUSAL) is not None]
        self.russel_widget.add_reference_points(points)

    def on_russel_changed(self, valence: float, arousal: float):
        cat_valence = get_music_category(_(CAT_VALENCE))
        cat_arousal = get_music_category(_(CAT_AROUSAL))
        self.set_category_value(cat_valence, valence, False)
        self.set_category_value(cat_arousal, arousal, False)

    def set_category_value(self, cat: str, value, notify: bool = True):
        if cat in self.sliders:
            self.sliders[cat].set_value(round(value), False)

        if notify:
            self.values_changed.emit()

    def config(self):
        config = FilterConfig(categories=self.categories(), tags=selected_tags, bpm=self.bpm_widget.value(), genres=selected_genres)
        return config

    def categories(self):
        _categories = {}
        for category, slider in self.sliders.items():
            _categories[category.name] = slider.value()

        if self.russel_widget.isVisible():
            valence, arousal = self.russel_widget.get_value()
            if valence == 5 and arousal == 5:
                _categories[_(CAT_VALENCE)] = None
                _categories[_(CAT_AROUSAL)] = None
            else:
                _categories[_(CAT_VALENCE)] = valence
                _categories[_(CAT_AROUSAL)] = arousal

        return _categories

    def on_russel_released(self):
        valence, arousal = self.russel_widget.get_value()

        cat_valence = get_music_category(_(CAT_VALENCE))
        cat_arousal = get_music_category(_(CAT_AROUSAL))
        self.set_category_value(cat_valence, valence, False)
        self.set_category_value(cat_arousal, arousal, True)

    def on_bpm_changed(self, value: int):
        self.values_changed.emit()


class MusicPlayer(QMainWindow):
    trackChanged = Signal(int)

    dir_tree_action: QAction
    light_theme_action: QAction
    dark_theme_action: QAction

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

            custom_tags = AppSettings.value(SettingKeys.TAGS)
            if custom_tags:
                set_music_tags(json.loads(custom_tags))

            custom_presets = AppSettings.value(SettingKeys.PRESETS)
            if custom_presets:
                list_of_custom_presets = json.loads(custom_categories)
                set_presets([Preset(**d) for d in list_of_custom_presets])

        except Exception as e:
            AppSettings.clear()
            logger.error("Failed to load custom settings: {0}", e)

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
            version_text = _("Newer version available {0}").format(f"<a href=\"{DOWNLOAD_LINK}\">{get_latest_version()}</a>")
            self.update_status_label(version_text, False, False)

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

        analyze_file_action = QAction(_("Analyze File"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.Scanner))
        analyze_file_action.triggered.connect(self.pick_analyze_file)
        file_menu.addAction(analyze_file_action)

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

        self.effects_tree_action = QAction(_("Effects Tree"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.AudioCard))
        self.effects_tree_action.setCheckable(True)
        self.effects_tree_action.setChecked(AppSettings.value(SettingKeys.EFFECTS_TREE, True, type=bool))
        self.effects_tree_action.triggered.connect(self.toggle_effects_tree)
        view_menu.addAction(self.effects_tree_action)

        font_size_small_action = QAction(_("Small"), self)
        font_size_small_action.setCheckable(True)
        font_size_small_action.triggered.connect(lambda: setattr(app_theme, 'font_size', 9))

        font_size_medium_action = QAction(_("Medium"), self)
        font_size_medium_action.setCheckable(True)
        font_size_medium_action.triggered.connect(lambda: setattr(app_theme, 'font_size', 10.5))

        font_size_large_action = QAction(_("Large"), self)
        font_size_large_action.setCheckable(True)
        font_size_large_action.triggered.connect(lambda: setattr(app_theme, 'font_size', 12))

        font_size_group = QActionGroup(self, exclusionPolicy=QActionGroup.ExclusionPolicy.Exclusive)
        font_size_group.addAction(font_size_small_action)
        font_size_group.addAction(font_size_medium_action)
        font_size_group.addAction(font_size_large_action)

        if app_theme.font_size == 9:
            font_size_small_action.setChecked(True)
        elif app_theme.font_size == 10.5:
            font_size_medium_action.setChecked(True)
        elif app_theme.font_size == 12:
            font_size_medium_action.setChecked(True)

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

        vis = AppSettings.value(SettingKeys.VISUALIZER, "FAKE", type=str)
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
            self.filter_widget.update_tags_and_presets()
            if self.current_table() is not None:
                self.current_table().update_category_column_visibility()

    def layout_splitter_moved(self, pos_x: int, index: int):
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
        self.central_splitter.splitterMoved.connect(self.layout_splitter_moved)
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
        self.filter_widget.values_changed.connect(self.update_category_values)
        main_layout.addWidget(self.filter_widget)
        self.filter_widget.setVisible(AppSettings.value(SettingKeys.FILTER_VISIBLE, True, type=bool))

        main_layout.addWidget(self.player, 0)

        self.toggle_directory_tree(AppSettings.value(SettingKeys.DIRECTORY_TREE, True, type=bool))
        self.toggle_effects_tree(AppSettings.value(SettingKeys.EFFECTS_TREE, True, type=bool))
        # -------------------------------------

        # Table Widget for Playlist

        self.table_tabs = QTabWidget()
        self.table_tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_tabs.tabBar().customContextMenuRequested.connect(self.show_tabs_context_menu)
        self.table_tabs.tabBar().setAutoHide(True)
        self.table_tabs.setMovable(False)
        self.table_tabs.setTabsClosable(True)
        self.table_tabs.currentChanged.connect(self.table_tab_changed)
        self.table_tabs.tabCloseRequested.connect(self.table_tab_close)

        main_layout.addWidget(self.table_tabs, 2)

        self.setStatusBar(QStatusBar())
        self.status_label = IconLabel(None, "")
        self.status_label.setContentsMargins(8, 0, 8, 0)
        self.status_label.clicked.connect(lambda: self.statusBar().setVisible(False))
        self.statusBar().addWidget(self.status_label, 1)

        self.status_progress = QProgressBar()
        self.status_progress.setContentsMargins(0, 0, 0, 0)
        self.status_progress.setRange(0, 0)
        self.statusBar().addWidget(self.status_progress)

        # main_layout.addWidget(self.status_bar, 0)

        self.statusBar().setVisible(False)

        self.analyzer.progress.connect(self.update_status_label)
        self.analyzer.error.connect(self.update_status_label_error)
        self.analyzer.error.connect(self.result_status_label)
        self.analyzer.result.connect(self.result_status_label)

        self.init_main_menu()

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

        menu.exec(self.table_tabs.tabBar().mapToGlobal(position))

    def result_status_label(self):
        if self.analyzer.active_worker() <= 1:
            t = threading.Timer(2, function=self.hide_status_label)
            t.start()

    def hide_status_label(self):
        if self.analyzer.active_worker() == 0:
            self.statusBar().setVisible(False)

    def update_status_label_error(self, msg: str):
        self.update_status_label(msg, True)

    def update_status_label(self, msg: str, error: bool = False, progress: bool = True):
        if msg is not None:
            self.statusBar().setVisible(True)
            self.status_progress.setVisible(progress)
            self.status_label.set_text(str(msg))

            if error:
                self.status_label.set_icon(QIcon.fromTheme(QIcon.ThemeIcon.DialogError))
            else:
                self.status_label.set_icon(QIcon.fromTheme(QIcon.ThemeIcon.DialogInformation))

    def add_table_tab(self, name: str, icon: QIcon) -> SongTable:
        table = SongTable(self.analyzer, self)

        table.play_track.connect(self.play_track)

        index = self.table_tabs.addTab(table, icon, name)

        self.table_tabs.setCurrentIndex(index)
        return table

    def table_tab_changed(self, index: int):
        table = self.current_table()
        table.update_category_column_visibility()

        table_data = table.mp3_datas()
        self.update_available_tags_and_categories(table_data)
        self.filter_widget.update_russel_heatmap(table_data)

    def table_tab_close(self, index: int):
        self.table_tabs.removeTab(index)
        self.table_tabs.tabBar().setVisible(self.table_tabs.count() > 1)

        AppSettings.setValue(SettingKeys.OPEN_TABLES, self.get_open_tables())

    def update_category_values(self):
        global categories
        categories = self.filter_widget.config().categories
        self.sort_table_data()

    def pick_analyze_file(self):
        file_path, ignore = QFileDialog.getOpenFileName(self, _("Select File to Analyze"),
                                                        dir=AppSettings.value(SettingKeys.LAST_DIRECTORY),
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

    def pick_load_playlist(self):
        file_path, ignore = QFileDialog.getOpenFileName(self, _("Select Playlist to Load"),
                                                        dir=AppSettings.value(SettingKeys.LAST_DIRECTORY),
                                                        filter=_("Playlist (*.m3u *.M3U);;All (*)"))
        if file_path:
            self.load_playlist(file_path)

    def pick_new_playlist(self, entries: list[Mp3Entry] = None):
        new_play_list = self.pick_save_playlist(entries)

        if new_play_list is not None:
            self.load_playlist(new_play_list)

    def pick_save_playlist(self, entries: list[Mp3Entry] = None):
        file_path, ignore = QFileDialog.getSaveFileName(self, _("Select Playlist to Save"),
                                                        dir=AppSettings.value(SettingKeys.LAST_DIRECTORY),
                                                        filter=_("Playlist (*.m3u *M3U);;All (*)"))
        if file_path:
            try:
                if self.save_playlist(file_path, entries):
                    self.update_status_label(_("Save Complete") + ": " + _("File {0} processed.").format(Path(file_path).name), progress=False)
                    return file_path
                else:
                    QMessageBox.critical(self, _("Save Error"), _("No favorites found."))
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, _("Save Error"), _("Failed to save file: {0}").format(e))
        return None

    def pick_load_directory(self):
        directory = QFileDialog.getExistingDirectory(self, _("Select Music Directory"),
                                                     dir=AppSettings.value(SettingKeys.LAST_DIRECTORY))
        if directory:
            self.load_directory(directory)

    def load_playlist(self, playlist_path: str | os.PathLike[str]):
        try:
            mp3_files = parse_m3u(playlist_path)

            name = Path(playlist_path).name.removesuffix(".m3u").removesuffix(".M3U")
            table = self.add_table_tab(name, QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical))
            table.playlist = playlist_path
            self.load_files(table, mp3_files)

            AppSettings.setValue(SettingKeys.OPEN_TABLES, self.get_open_tables())
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, _("Open Error"), _("Failed to load playlist: {0}").format(e))

    def save_playlist(self, playlist_path, entries: list[Mp3Entry] = None) -> bool:
        if entries is None:
            table = self.current_table()
            if table is None:
                return False

            entries = [x for x in table.mp3_datas() if x.favorite]

        if len(entries) > 0:
            create_m3u(entries, playlist_path)
            return True
        else:
            return False

    def add_to_playlist(self, playlist: os.PathLike[str], song: list[Mp3Entry]):
        append_m3u(song, playlist)

        for i in range(self.table_tabs.count()):
            table = self.table_tabs.widget(i)
            if table.playlist == playlist:
                table.table_model.addRows(song)
                break

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

    def load_directory(self, directory: str | os.PathLike[str]):
        try:
            AppSettings.setValue(SettingKeys.LAST_DIRECTORY, directory)
            base_path = Path(directory)
            mp3_files = list(base_path.rglob("*.mp3"))

            table = self.add_table_tab(Path(directory).name, QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen))
            table.directory = directory
            self.load_files(table, mp3_files)

            AppSettings.setValue(SettingKeys.OPEN_TABLES, self.get_open_tables())
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, _("Error"), _("Failed to scan directory: {0}").format(e))

    def update_available_tags_and_categories(self, entries: list[Mp3Entry]):
        global available_tags,available_genres, available_categories

        tags_set = set(get_music_tags().keys())
        genre_set = set()
        available_categories = get_music_categories().copy()
        available_categories_keys = [cat.key for cat in available_categories]
        for entry in entries:
            if entry.tags is not None:
                tags_set.update(entry.all_tags)
            if entry.genres is not None:
                genre_set.update(entry.genres)
            if entry.categories is not None:
                for key in entry.categories.keys():
                    if not key in available_categories_keys:
                        available_categories.append(MusicCategory.from_key(key))
                        available_categories_keys.append(key)

        available_tags = sorted(list(tags_set))
        available_genres = sorted(list(genre_set))

        self.filter_widget.update_tags_and_presets()
        self.filter_widget.update_sliders()

    def load_files(self, table: SongTable, mp3_files: list[Path]):
        if not mp3_files:
            QMessageBox.information(self, _("Scan"), _("No MP3 files found."))
            return

        table_data_list = [parse_mp3(f) for f in mp3_files]
        table_data_list = [song for song in table_data_list if song is not None]

        table.populate_table(table_data_list)

        if table == self.current_table():
            self.player.track_count = len(table_data_list)
            self.update_available_tags_and_categories(table_data_list)
            self.filter_widget.update_russel_heatmap(table_data_list)

    def reload_table(self, index: int):
        table = self.table(index)

        if table.playlist:
            mp3_files = parse_m3u(table.playlist)
            self.load_files(table, mp3_files)
        else:
            base_path = Path(table.directory)
            mp3_files = list(base_path.rglob("*.mp3"))
            self.load_files(table, mp3_files)

    def table(self, index: int) -> SongTable | None:
        return self.table_tabs.widget(index)

    def current_table(self) -> SongTable | None:
        return self.table_tabs.currentWidget()
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
            for open_table in open_tables:
                self.load(open_table)
        else:
            last_dir = AppSettings.value(SettingKeys.LAST_DIRECTORY)
            if last_dir:
                self.load(last_dir)

    def load(self, path: str | os.PathLike[str]):
        if Path(path).is_dir():
            self.load_directory(path)
        elif Path(path).is_file():
            self.load_playlist(path)
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
