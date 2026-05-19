import logging
import numbers
import os
import time
import traceback
from os import PathLike
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Signal, Qt, QModelIndex, QMimeData, QByteArray, QDataStream, QIODevice, QPersistentModelIndex, \
    QAbstractTableModel, QSize, QObject, QEvent, QPoint, QFileInfo, QRect, QPointF, QMargins
from PySide6.QtGui import QColor, QBrush, QIcon, QLinearGradient, QGradient, QAction, QKeyEvent, QDragMoveEvent, QDragEnterEvent, QPainter, QPalette, \
    QFontMetrics, QDropEvent, QPolygonF, QPainterStateGuard, QPen, QPixmap, QFont
from PySide6.QtWidgets import QMessageBox, QAbstractItemView, QWidget, QHeaderView, QMenu, QStyleOptionViewItem, QStyledItemDelegate, QStyle, QTableView
from sortedcontainers import SortedSet

from components.widgets import AutoSearchHelper
from components.dialogs import ImagePopup
from config.settings import AppSettings, SettingKeys, MusicCategory, get_music_categories, CAT_VALENCE, \
    CAT_AROUSAL, FilterConfig
from config.theme import app_theme, _alpha
from config.utils import tint_icon

from logic.mp3 import Mp3Entry, update_mp3_favorite, update_mp3_title, update_mp3_album, update_mp3_artist, update_mp3_genre, update_mp3_bpm, \
    update_mp3_category, Mp3FileLoader, save_playlist, remove_m3u, append_m3u, parse_mp3, update_mp3_tags, get_m3u_paths, update_mp3_summary


logger = logging.getLogger(__file__)

def _get_bpm_background_brush(desired_value: int | None, value: int, data: Mp3Entry) -> QBrush | Qt.GlobalColor | None:
    if value is None or desired_value is None or desired_value == 0:
        return _get_entry_background_brush(data)

    value_diff = abs(desired_value - value)

    if value_diff <= 40:
        return app_theme.get_green(51)
    elif value_diff <= 80:
        return app_theme.get_orange(51)
    else:
        return app_theme.get_red(51)

def _get_entry_background_brush(data: Mp3Entry):
    return None

def _get_score_foreground_brush(score: int | None) -> QColor | Qt.GlobalColor | None:
    return Qt.GlobalColor.black
    # if score is not None:
    #     if score < 50:
    #         return _black
    #     elif score < 100:
    #         return _black
    #     elif score < 150:
    #         return _black
    #     else:
    #         return _black
    # else:
    #     return _black


def _get_score_background_brush(score: int | None, data: Mp3Entry) -> QBrush | Qt.GlobalColor | None:
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
        return _get_entry_background_brush(data)


def _get_category_background_brush(desired_value: int | None, value: int, data:Mp3Entry) -> QBrush | Qt.GlobalColor | None:
    if value is None or desired_value is None:
        return _get_entry_background_brush(data)

    value_diff = abs(desired_value - value)

    if value_diff < 4:
        return app_theme.get_green(51)
    elif value_diff < 7:
        return app_theme.get_orange(51)
    else:
        return app_theme.get_red(51)


def _get_genre_background_brush(desired_values: list[str] | None, values: list[str], data: Mp3Entry) -> QBrush | Qt.GlobalColor | None:
    if values is None or desired_values is None or desired_values == []:
        return _get_entry_background_brush(data)

    if isinstance(values, str):
        values = ", ".split(values)

    found = 0
    for desired_value in desired_values:
        if desired_value in values:
            found = found + 1

    if found == len(desired_values):
        return app_theme.get_green(51)
    elif found > 0:
        return app_theme.get_orange(51)
    else:
        return app_theme.get_red(51)

class SongTableModel(QAbstractTableModel):
    INDEX_COL = 0
    FAV_COL = 1
    COVER_COL = 2
    FILE_COL = 3
    TITLE_COL = 4
    SUMMARY_COL = 5
    ARTIST_COL = 6
    ALBUM_COL = 7
    GENRE_COL = 8
    BPM_COL = 9
    SCORE_COL = 10
    CAT_COL = 11

    available_tags: SortedSet = SortedSet()
    available_genres: SortedSet = SortedSet()
    available_categories: list[MusicCategory] = []

    filter_config: FilterConfig = FilterConfig()

    on_mime_drop = Signal(str, int, int)

    def __init__(self, data: list[Mp3Entry], parent: QObject = None):
        super(SongTableModel, self).__init__(parent)
        self._data = [song for song in data if song is not None]

        self._update_available_tags_and_categories(self._data)

    def _add_available_tags_and_categories(self, entries: list[Mp3Entry]):
        available_categories_keys = [cat.key for cat in self.available_categories]
        for entry in entries:
            if entry.tags is not None:
                self.available_tags.update(entry.tags)
            if entry.genres is not None:
                self.available_genres.update(entry.genres)
            if entry.categories is not None:
                for key in entry.categories.keys():
                    if not key in available_categories_keys:
                        self.available_categories.append(MusicCategory.from_key(key))
                        available_categories_keys.append(key)

    def _update_available_tags_and_categories(self, entries: list[Mp3Entry]):
        self.available_genres = SortedSet()
        self.available_tags = SortedSet()
        self.available_categories = get_music_categories().copy()
        self._add_available_tags_and_categories(entries)

    def index_of(self, song: Mp3Entry):
        return self._data.index(song)

    def get_category_key(self, index: QModelIndex | int):
        if isinstance(index, int):
            cat_index = index - SongTableModel.CAT_COL
        else:
            cat_index = index.column() - SongTableModel.CAT_COL

        if 0 <= cat_index < len(self.available_categories):
            return self.available_categories[cat_index].key
        else:
            return None

    def get_category_name(self, index: QModelIndex | int):
        if isinstance(index, int):
            cat_index = index - SongTableModel.CAT_COL
        else:
            cat_index = index.column() - SongTableModel.CAT_COL

        if 0 <= cat_index < len(self.available_categories):
            return self.available_categories[cat_index].name
        else:
            return None

    def set_filter_config(self, _config: FilterConfig):
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
            elif index.column() == SongTableModel.SUMMARY_COL:
                data = index.data(Qt.ItemDataRole.UserRole)
                data.summary = value
                update_mp3_summary(data.path, value)
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

                category_key = self.get_category_key(index)

                new_value: int | float | None
                try:
                    if value == "" or value is None:
                        new_value = None
                    else:
                        if category_key == CAT_VALENCE or category_key == CAT_AROUSAL:
                            new_value = float(value)
                        else:
                            new_value = int(value)

                        new_value = min(max(0, new_value), 10)
                except ValueError:
                    logger.error("Invalid value for category {0}: {1}", category_key, value)
                    return False

                # Update file_data_list
                has_changes = False

                if new_value is None:
                    if data.categories is not None and category_key in data.categories:
                        data.categories[category_key] = None
                        has_changes = True
                elif new_value != data.categories.get(category_key, None):
                    data.categories[category_key] = new_value
                    has_changes = True
                else:
                    return False

                # Update MP3 tags

                try:
                    if has_changes:
                        update_mp3_category(data.path, category_key, new_value)
                except Exception as e:
                    traceback.print_exc()
                    logger.error("Failed to update tags: {0}", e)
                    QMessageBox.warning(self.parent(), _("Update Error"), _("Failed to update tags: {0}").format(e))

                return has_changes

        return False

    def clear(self):
        self.beginResetModel()
        self._data.clear()
        self.endResetModel()

        self._update_available_tags_and_categories(self._data)

    def addRows(self, data: list[Mp3Entry]):
        row_position = self.rowCount()

        data = [item for item in data if item not in self._data]

        # 2. Notify the view that rows are about to be inserted
        self.beginInsertRows(QModelIndex(), row_position, row_position + len(data) - 1)
        self._data.extend(data)
        self.endInsertRows()

        self._add_available_tags_and_categories(data)

    def insertRows(self, index: int, data: list[Mp3Entry]):
        if index < 0 or index > self.rowCount():
            row_position = self.rowCount()
        else:
            row_position = index

        data = [item for item in data if item not in self._data]

        # 2. Notify the view that rows are about to be inserted
        self.beginInsertRows(QModelIndex(), row_position, row_position + len(data) - 1)
        if row_position == self.rowCount():
            self._data.extend(data)
        else:
            for item in reversed(data):
                self._data.insert(row_position, item)

        self.endInsertRows()

        self._add_available_tags_and_categories(data)

    def removeRow(self, row: int, /, parent: QModelIndex | QPersistentModelIndex = ...) -> bool:
        if 0 <= row < len(self._data):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._data[row]
            self.endRemoveRows()

            self._update_available_tags_and_categories(self._data)

            return True
        return False

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = ...):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.FontRole:
            return app_theme.font_medium
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() >= SongTableModel.SCORE_COL or index.column() in [SongTableModel.BPM_COL, SongTableModel.INDEX_COL, SongTableModel.FAV_COL]:
                return Qt.AlignmentFlag.AlignCenter
        elif role == Qt.ItemDataRole.BackgroundRole:
            data = self._data[index.row()]
            if index.column() == SongTableModel.COVER_COL:
                return data.cover_preview
            if index.column() == SongTableModel.SCORE_COL:
                score = index.data(Qt.ItemDataRole.DisplayRole)
                return _get_score_background_brush(score, data)
            elif index.column() == SongTableModel.GENRE_COL:
                return _get_genre_background_brush(self.filter_config.genres, data.genres, data)
            elif index.column() == SongTableModel.BPM_COL:
                value = index.data(Qt.ItemDataRole.DisplayRole)
                return _get_bpm_background_brush(self.filter_config.bpm, value, data)
            elif index.column() >= SongTableModel.CAT_COL:
                value = index.data(Qt.ItemDataRole.DisplayRole)
                category_key = self.get_category_key(index)
                return _get_category_background_brush(self.filter_config.get_category(category_key, None), value, data)
            else:
                return _get_entry_background_brush(data)
        elif role in [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]:
            data = self._data[index.row()]
            if data is None:
                return None

            if index.column() == SongTableModel.INDEX_COL:
                return self._data.index(data)
            if index.column() == SongTableModel.FAV_COL:
                if role == Qt.ItemDataRole.EditRole:
                    return data.favorite
            elif index.column() == SongTableModel.FILE_COL:
                if role == Qt.ItemDataRole.EditRole:
                    if data.summary:
                        return data.name + " " + data.summary
                    else:
                        return data.name
            elif index.column() == SongTableModel.SUMMARY_COL:
                return data.summary
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
                return self._calculate_score(data)
            elif index.column() >= SongTableModel.CAT_COL:
                category_key = self.get_category_key(index)
                return data.get_category_value(category_key)
            else:
                return None

        elif role == Qt.ItemDataRole.UserRole:
            return self._data[index.row()]
        elif role == Qt.ItemDataRole.SizeHintRole:
            if index.column() == SongTableModel.FILE_COL:
                return QSize(400,0)
        return None

    def rowCount(self, /, parent: QModelIndex | QPersistentModelIndex = ...) -> int:
        return len(self._data)

    def columnCount(self, /, parent: QModelIndex | QPersistentModelIndex = ...) -> int:
        return SongTableModel.CAT_COL + len(self.available_categories)

    def headerData(self, section: int, orientation: Qt.Orientation, /, role: int = ...):
        if role == Qt.ItemDataRole.DisplayRole:
            if section == SongTableModel.INDEX_COL:
                return ""
            elif section == SongTableModel.FAV_COL:
                return ""
            elif section == SongTableModel.COVER_COL:
                return _("Cover")
            elif section == SongTableModel.FILE_COL:
                if AppSettings.value(SettingKeys.SONGS_TITLE_INSTEAD_OF_FILE_NAME, False, type=bool):
                    return _("Title")
                else:
                    return _("File")
            elif section == SongTableModel.TITLE_COL:
                return _("Title")
            elif section == SongTableModel.SUMMARY_COL:
                return _("Summary")
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
                return self.get_category_name(section)

        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex, /) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled

        default_flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled

        if index.column() == SongTableModel.INDEX_COL:
            return default_flags | Qt.ItemFlag.ItemIsDropEnabled
        elif index.column() in [SongTableModel.INDEX_COL, SongTableModel.FAV_COL, SongTableModel.SCORE_COL, SongTableModel.FILE_COL, SongTableModel.COVER_COL]:
            return default_flags
        else:
            return default_flags | Qt.ItemFlag.ItemIsEditable

    def supportedDropActions(self, /):
        return Qt.DropAction.MoveAction

    def mimeTypes(self):
        return ['application/x-dungeontuber-song']

    def mimeData(self, indexes):
        mime_data = QMimeData()
        encoded_data = QByteArray()
        stream = QDataStream(encoded_data, QIODevice.OpenModeFlag.WriteOnly)
        rows = sorted(list(set([index.row() for index in indexes])))

        for row in rows:
            stream.writeInt32(row)

        mime_data.setData('application/x-dungeontuber-song', encoded_data)
        return mime_data

    def dropMimeData(self, data, action, row, column, parent):
        if action == Qt.DropAction.IgnoreAction:
            return True

        if not data.hasFormat('application/x-dungeontuber-song'):
            return False

        encoded_data = data.data('application/x-dungeontuber-song')
        stream = QDataStream(encoded_data, QIODevice.OpenModeFlag.ReadOnly)

        rows = []
        while not stream.atEnd():
            rows.append(stream.readInt32())

        if not rows:
            return False

        begin_row = row
        if row == -1:
            if parent.isValid():
                begin_row = parent.row()
            else:
                begin_row = len(self._data)

        items = [self._data[r] for r in rows]

        for r in sorted(rows, reverse=True):
            self.beginRemoveRows(QModelIndex(), r, r)
            del self._data[r]
            self.endRemoveRows()
            if r < begin_row:
                begin_row -= 1

        self.beginInsertRows(QModelIndex(), begin_row, begin_row + len(items) - 1)
        for i, item in enumerate(items):
            self._data.insert(begin_row + i, item)
        self.endInsertRows()

        self.on_mime_drop.emit('application/x-dungeontuber-song', begin_row, begin_row + len(items) - 1)
        return True

    def _calculate_score(self, data: Mp3Entry):
        score = None
        for cat_key, desired_value in self.filter_config.categories.items():
            if desired_value is not None and desired_value >= 0:
                if score is None:
                    score = 0
                current_value = data.get_category_value(cat_key)
                if isinstance(current_value, numbers.Number):
                    score += (current_value - desired_value) ** 2
                else:
                    score += 10 ** 2

        for desired_tag in self.filter_config.tags:
            if score is None:
                score = 0

            if data.tags is not None:
                if desired_tag not in data.tags and desired_tag not in data.genres:
                    score += 100
            else:
                score += 100

        for desired_genres in self.filter_config.genres:
            if score is None:
                score = 0

            if data.genres is not None:
                if desired_genres not in data.genres:
                    score += 100
            else:
                score += 100

        if self.filter_config.bpm is not None:
            if score is None:
                score = 0

            if data.bpm is None:
                score += 100
            else:
                score += abs(self.filter_config.bpm - data.bpm)

        return round(score) if score is not None else None


class SongTableProxyModel(QSortFilterProxyModel):
    sort_changed = Signal(int, Qt.SortOrder)  # Custom signal

    def __init__(self, parent: QObject):
        super().__init__(parent)

        self.setSortRole(Qt.ItemDataRole.EditRole)
        self.setFilterRole(Qt.ItemDataRole.EditRole)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(SongTableModel.FILE_COL)

    def sort(self, column, /, order=...):
        self.sort_changed.emit(column, order)
        super().sort(column, order)

    def dropMimeData(self, data, action, row, column, parent):
        source_parent = self.mapToSource(parent)
        source_row = row

        if row != -1:
            proxy_index = self.index(row, 0, parent)
            if proxy_index.isValid():
                source_index = self.mapToSource(proxy_index)
                source_row = source_index.row()
            else:
                source_row = self.sourceModel().rowCount(source_parent)

        return self.sourceModel().dropMimeData(data, action, source_row, column, source_parent)

def _get_table_padding():
    rowStyle = AppSettings.value(SettingKeys.SONGS_ROW_STYLE, 'MEDIUM', type=str)
    if rowStyle == "SMALL":
        return 1
    else:
        return 3

class SongTable(QTableView):
    item_double_clicked = Signal(QPersistentModelIndex, Mp3Entry)
    content_changed = Signal()

    analyze_file = Signal(QFileInfo)
    open_files = Signal(list[QFileInfo])
    open_context_menu = Signal(QMenu, list)

    playlist: PathLike[str] = None
    directory: PathLike[str] = None

    table_model: SongTableModel
    proxy_model: SongTableProxyModel

    def __init__(self, parent: QWidget | None = None, source: PathLike[str] = None, mp3_files: list[Path | Mp3Entry] = [], lazy: bool = False):
        super().__init__(parent)

        self.category_delegate = CategoryDelegate(self)
        self.cover_delegate = CoverDelegate(self)
        self.label_item_delegate = LabelItemDelegate(self)
        self.star_delegate = StarDelegate(self)

        self._refresh_palette()

        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setGridStyle(Qt.PenStyle.NoPen)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        if os.path.isfile(source):
            self.playlist = source
        elif os.path.isdir(source):
            self.directory = source

        self.table_model = SongTableModel([], self)
        self.table_model.on_mime_drop.connect(self.update_playlist)
        self.filter_config = FilterConfig()

        self.proxy_model = SongTableProxyModel(self)
        self.proxy_model.sort_changed.connect(self.on_sort_changed)
        self.proxy_model.setDynamicSortFilter(True)
        self.proxy_model.setSourceModel(self.table_model)


        self.setModel(self.proxy_model)

        self.auto_search_helper = AutoSearchHelper(self.proxy_model, self)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)

        self.verticalHeader().setVisible(False)

        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._show_header_context_menu)
        self.horizontalHeader().setFont(app_theme.font_small)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.setItemDelegate(self.category_delegate)
        self.setItemDelegateForColumn(SongTableModel.COVER_COL, self.cover_delegate)
        self.setItemDelegateForColumn(SongTableModel.FILE_COL, self.label_item_delegate)
        self.setItemDelegateForColumn(SongTableModel.FAV_COL, self.star_delegate)

        self.doubleClicked.connect(self.on_table_double_click)

        self.source_files: list[Path] = []
        self.is_loaded = False
        self.loader = None

        self._load_files(mp3_files, lazy)

    def get_name(self) -> str:
        if self.directory:
            return Path(self.directory).name
        elif self.playlist:
            return Path(self.playlist).name.removesuffix(".m3u").removesuffix(".M3U")
        else:
            return None

    def get_icon(self) -> QIcon:
        if self.directory:
            return QIcon.fromTheme("folder")
        else:
            return QIcon.fromTheme("list-music")

    def _load_files(self, mp3_files: list[Path | Mp3Entry], lazy: bool = False):
        if not mp3_files:
            QMessageBox.information(self, _("Scan"), _("No MP3 files found."))
            return

        if isinstance(mp3_files[0], Path):
            self.table_model.clear()
            self.source_files = mp3_files
            self.is_loaded = False
            if not lazy:
                self.start_lazy_loading()
        else:
            self._populate_table(mp3_files)

    def reload_files(self):
        if self.playlist:
            mp3_files = get_m3u_paths(self.playlist)
            self._load_files(mp3_files)
        else:
            base_path = Path(self.directory)
            mp3_files = list(base_path.rglob("*.mp3", case_sensitive=False))
            self._load_files(mp3_files)

    def get_available_categories(self) -> list[MusicCategory]:
        return self.table_model.available_categories

    def get_available_tags(self) -> list[str]:
        return self.table_model.available_tags

    def get_available_genres(self) -> list[str]:
        return self.table_model.available_genres

    def set_filter_config(self, filter_config: FilterConfig):
        self.filter_config = filter_config
        self.table_model.set_filter_config(filter_config)

        self.update_category_column_visibility()

        self.selectRow(0)
        self.sortByColumn(SongTableModel.SCORE_COL, Qt.SortOrder.AscendingOrder)

    def _calc_header_width(self, index: int):
        font_metrics = self.horizontalHeader().fontMetrics()

        name = self.table_model.headerData(index, Qt.Orientation.Horizontal, role=Qt.ItemDataRole.DisplayRole)
        # padding + text width
        return (app_theme.font_size * 2 +
                + self.horizontalHeader().contentsMargins().left()
                + self.horizontalHeader().contentsMargins().right()
                + font_metrics.horizontalAdvance(name))

    def _update_table_sizes(self):
        # heights
        rowStyle = AppSettings.value(SettingKeys.SONGS_ROW_STYLE, 'MEDIUM', type=str)
        if rowStyle == "MEDIUM":
            scale_factor = 4.0 if AppSettings.value(SettingKeys.COLUMN_TITLE_SUMMARY_VISIBLE, True, type=bool) else 2.0
        elif rowStyle == "SMALL":
            scale_factor = 3.5 if AppSettings.value(SettingKeys.COLUMN_TITLE_SUMMARY_VISIBLE, True, type=bool) else 1.5
        else:
            scale_factor = 6.5 if AppSettings.value(SettingKeys.COLUMN_TITLE_SUMMARY_VISIBLE, True, type=bool) else 4.0

        self.verticalHeader().setDefaultSectionSize((app_theme.font_size * scale_factor) + 2)

        available_width = self.viewport().width()
        used_width =0

        # widths

        self.setColumnWidth(SongTableModel.FAV_COL, 48)
        self.setColumnWidth(SongTableModel.FILE_COL, 400)
        self.setColumnWidth(SongTableModel.COVER_COL, 120)
        self.resizeColumnToContents(SongTableModel.INDEX_COL)
        self.resizeColumnToContents(SongTableModel.TITLE_COL)
        self.resizeColumnToContents(SongTableModel.SUMMARY_COL)
        self.resizeColumnToContents(SongTableModel.ALBUM_COL)
        self.resizeColumnToContents(SongTableModel.GENRE_COL)
        self.resizeColumnToContents(SongTableModel.ARTIST_COL)
        for index in range(SongTableModel.CAT_COL, self.columnCount()):
            self.setColumnWidth(index, self._calc_header_width(index))

        for index in [SongTableModel.BPM_COL, SongTableModel.SCORE_COL]:
            self.setColumnWidth(index, self._calc_header_width(index))


        for index in range(self.columnCount()):
                if not self.isColumnHidden(index):
                    used_width  = used_width + self.columnWidth(index)

        self.horizontalHeader().setSectionResizeMode(SongTableModel.INDEX_COL, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(SongTableModel.FAV_COL, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setCascadingSectionResizes(True)
        #self.horizontalHeader().setSectionResizeMode(SongTableModel.FILE_COL, QHeaderView.ResizeMode.Interactive)
        # self.horizontalHeader().setStretchLastSection(True)

        if used_width < available_width:
            free_width = available_width - used_width
            self.setColumnWidth(SongTableModel.FILE_COL, self.columnWidth(SongTableModel.FILE_COL) +free_width)

    def start_lazy_loading(self):
        if self.is_loaded or self.loader is not None:
            return

        self.loader = Mp3FileLoader(self.source_files, self)
        self.loader.files_loaded.connect(self.on_load_progress)
        self.loader.finished.connect(self.on_load_finished)
        self.loader.start()

    def on_load_progress(self, entries: list):
        self.table_model.addRows(entries)

    def on_load_finished(self):
        self.is_loaded = True
        self.loader = None
        self.content_changed.emit()

    def _refresh_palette(self):
        self.setPalette(app_theme.get_list_palette())
        self.update()

    def _refresh_delegates(self):
        for delegate in [self.category_delegate, self.star_delegate, self.label_item_delegate,self.cover_delegate]:
            delegate.refresh_style()

    def showEvent(self, event, /):
        self.update_category_column_visibility()

    def changeEvent(self, event: QEvent, /):
        if event.type() == QEvent.Type.FontChange:
            self._update_table_sizes()
            self._refresh_delegates()
        elif event.type() == QEvent.Type.PaletteChange:
            self._refresh_palette()
            self._refresh_delegates()

    def on_sort_changed(self, column, order_by):
        self.setDragEnabled(column == 0)

    def _show_header_context_menu(self, point):
        menu = QMenu(self)

        # Index
        if self.playlist is not None:
            index_action = QAction(_("Index"), self)
            index_action.setCheckable(True)
            index_action.setChecked(AppSettings.value(SettingKeys.COLUMN_INDEX_VISIBLE, True, type=bool))
            index_action.triggered.connect(
                lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_INDEX_VISIBLE, checked))
            menu.addAction(index_action)

        # Favorite
        fav_action = QAction(_("Favorite"), self)
        fav_action.setCheckable(True)
        fav_action.setChecked(AppSettings.value(SettingKeys.COLUMN_FAVORITE_VISIBLE, True, type=bool))
        fav_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_FAVORITE_VISIBLE, checked))
        menu.addAction(fav_action)

        # Cover
        cover_action = QAction(_("Cover"), self)
        cover_action.setCheckable(True)
        cover_action.setChecked(AppSettings.value(SettingKeys.COLUMN_COVER_VISIBLE, False, type=bool))
        cover_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_COVER_VISIBLE, checked))
        menu.addAction(cover_action)

        # Title
        title_action = QAction(_("Title"), self)
        title_action.setCheckable(True)
        title_action.setChecked(AppSettings.value(SettingKeys.COLUMN_TITLE_VISIBLE, False, type=bool))
        title_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_TITLE_VISIBLE, checked))
        menu.addAction(title_action)

        #Summary
        summary_action = QAction(_("Summary"), self)
        summary_action.setCheckable(True)
        summary_action.setChecked(AppSettings.value(SettingKeys.COLUMN_SUMMARY_VISIBLE, True, type=bool))
        summary_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_SUMMARY_VISIBLE, checked))
        menu.addAction(summary_action)

        # Artist
        artist_action = QAction(_("Artist"), self)
        artist_action.setCheckable(True)
        artist_action.setChecked(AppSettings.value(SettingKeys.COLUMN_ARTIST_VISIBLE, False, type=bool))
        artist_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_ARTIST_VISIBLE, checked))
        menu.addAction(artist_action)

        # Album
        album_action = QAction(_("Album"), self)
        album_action.setCheckable(True)
        album_action.setChecked(AppSettings.value(SettingKeys.COLUMN_ALBUM_VISIBLE, False, type=bool))
        album_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_ALBUM_VISIBLE, checked))
        menu.addAction(album_action)

        # Genre
        genre_action = QAction(_("Genre"), self)
        genre_action.setCheckable(True)
        genre_action.setChecked(AppSettings.value(SettingKeys.COLUMN_GENRE_VISIBLE, False, type=bool))
        genre_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_GENRE_VISIBLE, checked))
        menu.addAction(genre_action)

        bpm_action = QAction(_("BPM (Beats per Minute)"), self)
        bpm_action.setCheckable(True)
        bpm_action.setChecked(AppSettings.value(SettingKeys.COLUMN_BPM_VISIBLE, False, type=bool))
        bpm_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_BPM_VISIBLE, checked))
        menu.addAction(bpm_action)

        score_action = QAction(_("Score"), self)
        score_action.setCheckable(True)
        score_action.setChecked(AppSettings.value(SettingKeys.COLUMN_SCORE_VISIBLE, True, type=bool))
        score_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_SCORE_VISIBLE, checked))
        menu.addAction(score_action)

        columns_menu = QMenu(_("Categories"))
        for category in self.table_model.available_categories:
            column_action = QAction(category.name, self)
            column_action.setCheckable(True)
            column_action.setChecked(AppSettings.value(SettingKeys.TABLE_COLUMNS + category.key, True, type=bool))
            column_action.triggered.connect(
                lambda checked, _cat=category: self._toggle_column_setting(SettingKeys.TABLE_COLUMNS + _cat.key, checked))
            columns_menu.addAction(column_action)
        menu.addMenu(columns_menu)
        # Dynamic Columns
        dynamic_action = QAction(_("Dynamic Columns"), self)
        dynamic_action.setCheckable(True)
        dynamic_action.setChecked(AppSettings.value(SettingKeys.DYNAMIC_TABLE_COLUMNS, False, type=bool))
        dynamic_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.DYNAMIC_TABLE_COLUMNS, checked))
        menu.addAction(dynamic_action)

        menu.addSeparator()

        file_name_action = QAction(_("Use mp3 title instead of file name"), self)
        file_name_action.setCheckable(True)
        file_name_action.setChecked(AppSettings.value(SettingKeys.SONGS_TITLE_INSTEAD_OF_FILE_NAME, False, type=bool))
        file_name_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.SONGS_TITLE_INSTEAD_OF_FILE_NAME, checked))
        menu.addAction(file_name_action)

        # Summary

        title_summary_action = QAction(_("Display summary next to title"), self)
        title_summary_action.setCheckable(True)
        title_summary_action.setChecked(AppSettings.value(SettingKeys.COLUMN_TITLE_SUMMARY_VISIBLE, True, type=bool))
        title_summary_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_TITLE_SUMMARY_VISIBLE, checked))
        menu.addAction(title_summary_action)

        toggle_tags_action = QAction(_("Tags"), self)
        toggle_tags_action.setCheckable(True)
        toggle_tags_action.setChecked(AppSettings.value(SettingKeys.COLUMN_TAGS_VISIBLE, True, type=bool))
        toggle_tags_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_TAGS_VISIBLE, checked))
        menu.addAction(toggle_tags_action)

        row_style = AppSettings.value(SettingKeys.SONGS_ROW_STYLE, "MEDIUM", type=str)
        row_style_menu = menu.addMenu(_("Row Style"))
        for style in ["SMALL", "MEDIUM", "LARGE"]:
            row_style_size_action = QAction(_(style), self)
            row_style_size_action.setCheckable(True)
            row_style_size_action.setChecked(row_style == style)
            row_style_size_action.triggered.connect(
                lambda checked, s=style: self._toggle_column_setting(SettingKeys.SONGS_ROW_STYLE, s))
            row_style_menu.addAction(row_style_size_action)


        menu.exec(self.horizontalHeader().mapToGlobal(point))

    def _toggle_column_setting(self, key, checked):
        AppSettings.setValue(key, checked)
        self._refresh_delegates()
        self.update_category_column_visibility()
        if key in [SettingKeys.COLUMN_TITLE_SUMMARY_VISIBLE, SettingKeys.COLUMN_TAGS_VISIBLE]:
            self.viewport().update()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in  [Qt.Key.Key_Enter, Qt.Key.Key_Return]:
            index = self.selectionModel().currentIndex()
            self.item_double_clicked.emit(index, index.data(Qt.ItemDataRole.UserRole))
            return
        elif event.key() == Qt.Key.Key_Delete:
            self.remove_items()
            return
        elif not self.auto_search_helper.keyPressEvent(event):
            super().keyPressEvent(event)

    def paintEvent(self, event):

        start = time.perf_counter_ns()
        # 1. Let the standard TreeView draw the folders/files first
        super().paintEvent(event)
        self.auto_search_helper.paintEvent(event)

        duration_ms = (time.perf_counter_ns() - start) / 1_000_000
        if duration_ms > 5.0:
            logger.debug(f"Warning: Paint took too long! {duration_ms:.2f} ms")



    def on_table_double_click(self, index: QModelIndex):
        if index.column() == SongTableModel.FILE_COL:
            data = index.data(Qt.ItemDataRole.UserRole)
            self.item_double_clicked.emit(index, data)
        elif index.column() == SongTableModel.FAV_COL:
            data = index.data(Qt.ItemDataRole.UserRole)
            data.favorite = not data.favorite
            update_mp3_favorite(data.path, data.favorite)
            self.repaint()
        elif index.column() == SongTableModel.COVER_COL:
            data = index.data(Qt.ItemDataRole.UserRole)
            if data.has_cover:
                self.image_popup = ImagePopup(data.title, data.cover)
                self.image_popup.show()


    def refresh_item(self, file_path: PathLike[str]):
        data = parse_mp3(Path(file_path))
        if data is not None:
            index = self.index_of(data)
            if index.isValid():
                self.model().setData(index, data, Qt.ItemDataRole.UserRole)

    def setModel(self, model: SongTableModel | SongTableProxyModel):
        if isinstance(model, SongTableProxyModel):
            super().setModel(model)
        else:
            self.table_model = model
            self.table_model.on_mime_drop.connect(self.update_playlist)
            self.proxy_model.setSourceModel(model)

            self.update_category_column_visibility()
            self.is_loaded = True

    def _populate_table(self, table_data: list[Mp3Entry]):
        self.table_model = SongTableModel(table_data, self)
        self.table_model.on_mime_drop.connect(self.update_playlist)
        self.proxy_model.setSourceModel(self.table_model)

        self.update_category_column_visibility()

        self.is_loaded = True
        self.content_changed.emit()

    def update_playlist(self):
        if self.playlist is not None:
            save_playlist(self.playlist, self.mp3_datas())

    def is_column_visible(self, category_key: str):
        if AppSettings.value(SettingKeys.DYNAMIC_TABLE_COLUMNS, False, type=bool):
            if category_key == "bpm":
                value = self.table_model.filter_config.bpm if self.table_model.filter_config.bpm else None
            else:
                value = self.table_model.filter_config.get_category(category_key, None)

            return value is not None
        else:
            if category_key == "bpm":
                return AppSettings.value(SettingKeys.COLUMN_BPM_VISIBLE, False, type=bool)
            else:
                return AppSettings.value(SettingKeys.TABLE_COLUMNS + category_key, True, type=bool)

    def update_category_column_visibility(self):
        self.setColumnHidden(SongTableModel.INDEX_COL, self.playlist is None or not AppSettings.value(SettingKeys.COLUMN_INDEX_VISIBLE, True, type=bool))
        self.setColumnHidden(SongTableModel.FAV_COL, not AppSettings.value(SettingKeys.COLUMN_FAVORITE_VISIBLE, True, type=bool))
        self.setColumnHidden(SongTableModel.COVER_COL, not AppSettings.value(SettingKeys.COLUMN_COVER_VISIBLE, False, type=bool))

        if AppSettings.value(SettingKeys.SONGS_TITLE_INSTEAD_OF_FILE_NAME, False, type=bool):
            self.setColumnHidden(SongTableModel.TITLE_COL, True)
        else:
            self.setColumnHidden(SongTableModel.TITLE_COL, not AppSettings.value(SettingKeys.COLUMN_TITLE_VISIBLE, False, type=bool))

        self.setColumnHidden(SongTableModel.SUMMARY_COL, not AppSettings.value(SettingKeys.COLUMN_SUMMARY_VISIBLE, False, type=bool))
        self.setColumnHidden(SongTableModel.SCORE_COL, not AppSettings.value(SettingKeys.COLUMN_SCORE_VISIBLE, True, type=bool))
        self.setColumnHidden(SongTableModel.ARTIST_COL, not AppSettings.value(SettingKeys.COLUMN_ARTIST_VISIBLE, False, type=bool))
        self.setColumnHidden(SongTableModel.ALBUM_COL, not AppSettings.value(SettingKeys.COLUMN_ALBUM_VISIBLE, False, type=bool))
        self.setColumnHidden(SongTableModel.GENRE_COL, not AppSettings.value(SettingKeys.COLUMN_GENRE_VISIBLE, False, type=bool))
        self.setColumnHidden(SongTableModel.BPM_COL, not self.is_column_visible('bpm'))

        if AppSettings.value(SettingKeys.DYNAMIC_SCORE_COLUMN, True, type=bool) and (
                self.table_model.filter_config is None or self.table_model.filter_config.empty()):
            self.setColumnHidden(SongTableModel.SCORE_COL, True)

        for col, category in enumerate(self.table_model.available_categories):
            self.setColumnHidden(SongTableModel.CAT_COL + col, not self.is_column_visible(category.key))

        self.first_visible_column = 0
        for i in range(self.model().columnCount()):
            if not self.isColumnHidden(i):
                self.first_visible_column = i
                break

        self._update_table_sizes()

    def get_raw_data(self) -> list[Mp3Entry]:
        return self.table_model._data

    def mp3_datas(self) -> list[Mp3Entry]:
        if self.model() is not None:
            return [self.mp3_data(row) for row in range(self.rowCount())]
        else:
            return []

    def index_of(self, entry: Mp3Entry) -> QModelIndex:
        try:
            sourceRow = self.get_raw_data().index(entry)
            sourceIndex = self.table_model.index(sourceRow, 0)
            return self.proxy_model.mapFromSource(sourceIndex)
        except ValueError:
            return self.model().index(-1, 0)

    def mp3_data(self, row: int) -> Mp3Entry | None:
        index = self.model().index(row, SongTableModel.FILE_COL)
        return self.model().data(index, Qt.ItemDataRole.UserRole)

    def rowCount(self) -> int:
        return 0 if self.model() is None else self.model().rowCount()

    def columnCount(self) -> int:
        return 0 if self.model() is None else self.model().columnCount()

    def remove_items(self):
        datas = []
        for model_index in reversed(self.selectionModel().selectedRows()):
            datas.append(model_index.data(Qt.ItemDataRole.UserRole))

            # We must map the proxy index back to the source index
            source_index = self.proxy_model.mapToSource(model_index)
            # Now use the source row to remove from the source model

            self.table_model.removeRow(source_index.row())

        if self.playlist is not None:
            remove_m3u(datas, self.playlist)

    def show_context_menu(self, point: QPoint):
        # index = self.indexAt(point)
        menu = QMenu(self)

        datas = [model_index.data(Qt.ItemDataRole.UserRole) for model_index in self.selectionModel().selectedRows()]
        self.open_context_menu.emit(menu, datas)

        if len(datas) > 0:
            remove_action = menu.addAction(QIcon.fromTheme(QIcon.ThemeIcon.EditDelete), _("Remove from playlist") if self.playlist else _("Remove"))
            remove_action.triggered.connect(self.remove_items)

        if not menu.isEmpty():
            menu.show()
            menu.exec(self.mapToGlobal(point))

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            if self.playlist:
                event.accept()
            else:
                paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
                if all(os.path.isdir(path) for path in paths):
                    event.accept()
                elif all(path.suffix.lower() == ".m3u" for path in paths):
                    event.accept()
                else:
                    event.ignore()
        elif event.mimeData().hasFormat("text/slider"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent):
        if event.mimeData().hasUrls():
            if self.playlist:
                event.accept()
            else:
                paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
                if all(os.path.isdir(path) for path in paths):
                    event.accept()
                elif all(path.suffix.lower() == ".m3u" for path in paths):
                    event.accept()
                else:
                    event.ignore()
        elif event.mimeData().hasFormat("text/slider"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]

            if all(os.path.isdir(path) for path in paths):
                event.accept()
                self.open_files.emit([QFileInfo(path) for path in paths])
            elif all(path.suffix.lower() == ".m3u" for path in paths):
                event.accept()
                self.open_files.emit([QFileInfo(path) for path in paths])
            elif self.playlist:
                index = self.indexAt(event.position().toPoint())

                event.accept()
                songs = [parse_mp3(path) for path in paths]
                songs = [song for song in songs if song is not None]

                if index.isValid():
                    append_m3u(songs, self.playlist, index.row())
                    self.table_model.insertRows(index.row(), songs)
                else:
                    append_m3u(songs, self.playlist)
                    self.table_model.addRows(songs)

            else:
                event.ignore()
        elif event.mimeData().hasFormat("text/slider"):
            tag = str(event.mimeData().data("text/slider").data(), encoding='utf-8')
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


def get_full_pixmap(icon_path):
    icon = QIcon(icon_path)

    # Get all sizes stored in the icon file
    sizes = icon.availableSizes()
    if not sizes:
        return None

    # Find the largest size (the "original" high-res version)
    largest_size = max(sizes, key=lambda s: s.width())

    # Convert to pixmap at that specific size
    pixmap = icon.pixmap(largest_size)
    return pixmap


class BaseStyledItemDelegate(QStyledItemDelegate):

    def __init__(self, parent =None):
        super().__init__(parent)
        self.refresh_style()


    def paint_selection(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        # Check if the item is currently selected
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
            song_table : SongTable = option.widget
            if index.column() == song_table.first_visible_column:
                with QPainterStateGuard(painter):
                    painter.setPen(self.pen_accent)

                    p1: QPoint = option.rect.topLeft()
                    p1.setX(p1.x() + self.padding)
                    p1.setY(round(p1.y() + option.rect.height() * 0.25))
                    p2: QPoint = option.rect.bottomLeft()
                    p2.setX(p2.x() + self.padding)
                    p2.setY(round(p2.y() - option.rect.height() * 0.25))
                    painter.drawLine(p1, p2)



        # 2. TRICK: Remove the selected state flag so Fusion doesn't
        # overwrite your background with its solid default color
        if option.state & QStyle.StateFlag.State_Selected:
            option.state &= ~QStyle.StateFlag.State_Selected

        if option.state & QStyle.StateFlag.State_HasFocus:
            option.state &= ~QStyle.StateFlag.State_HasFocus


    def refresh_style(self):
        self.cell_padding = _get_table_padding()
        self.cell_margin = QMargins(self.cell_padding * 2, self.cell_padding, self.cell_padding * 2, self.cell_padding)
        self.padding_small: int = app_theme.padding_small
        self.padding: int = app_theme.padding
        self.padding_large: int = app_theme.padding_large

        self.pen_accent = QPen(app_theme.get_palette().color(QPalette.ColorRole.Accent), 2.0)


    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):

        if option.state & QStyle.StateFlag.State_MouseOver:
            option.state &= ~QStyle.StateFlag.State_MouseOver

        self.paint_selection(painter, option, index)

class CoverDelegate(BaseStyledItemDelegate):

    def __init__(self, parent: QObject = None):
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        self.initStyleOption(option, index)

        data: Mp3Entry = index.data(Qt.ItemDataRole.UserRole)

        rect = option.rect
        if data.has_cover:
            with QPainterStateGuard(painter):
                pixmap = data.cover_preview
                if pixmap:
                    scaled_size = pixmap.size().scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding)
                    # Calculate the top-left to center the "crop"
                    x = rect.x() + (rect.width() - scaled_size.width()) // 2
                    y = rect.y() + (rect.height() - scaled_size.height()) // 2

                    painter.setClipRect(rect)
                    painter.drawPixmap(x, y, scaled_size.width(), scaled_size.height(), pixmap)

        super().paint(painter, option, index)

class CategoryDelegate(BaseStyledItemDelegate):

    fallback_bg:QColor = None

    def __init__(self, parent: QObject = None):
        super().__init__(parent)

        self.fallback_bg = _alpha(app_theme.get_palette().color(QPalette.ColorRole.Accent), 40)

    def setModelData(self, editor: QWidget, model: QAbstractTableModel, index: QModelIndex | QPersistentModelIndex):
        # Grab the text directly from the editor
        text = editor.text()
        if not text:
            # Explicitly set None/Null in the model if the field is empty
            model.setData(index, None, Qt.ItemDataRole.EditRole)
        else:
            # Otherwise, use the standard behavior
            super().setModelData(editor, model, index)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        if index.column() < SongTableModel.CAT_COL:
            super().paint(painter, option, index)
            return

        score = index.data(Qt.ItemDataRole.DisplayRole)
        if score is not None:
            self.initStyleOption(option, index)
            rect: QRect = option.rect.adjusted(4,10,-4,-10)
            bg = option.backgroundBrush if option.backgroundBrush and option.backgroundBrush.style() != Qt.BrushStyle.NoBrush else self.fallback_bg
            painter.fillRect(rect.x(), rect.y(), rect.width() * 0.1 * score, rect.height(), bg)

            # 6. Draw text/foreground ONLY (Avoids super().paint overdraw)
            # This draws the text nicely over your custom bar without wiping out your work.
            if option.features & QStyleOptionViewItem.ViewItemFeature.HasDisplay:
                text_rect = option.rect.adjusted(6, 0, -6, 0)  # Adjust text padding as needed

                # Draw text with proper palette state (selected vs normal)
                painter.setPen(option.palette.color(QPalette.ColorRole.HighlightedText) if (option.state & QStyle.StateFlag.State_Selected) else option.palette.color(QPalette.ColorRole.Text))
                painter.drawText(text_rect, option.displayAlignment, option.text)

        super().paint(painter, option, index)

class StarDelegate(BaseStyledItemDelegate):

    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self.star_off = QIcon.fromTheme("star").pixmap(self.size)
        self.star_on = QIcon.fromTheme("star-full").pixmap(self.size)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        painter.save()
        star_rect = option.rect.adjusted(self.padding,self.padding,-self.padding,-self.padding)

        # 2. Automatically calculate the centered rectangle for your Pixmap X
        centered_rect = QStyle.alignedRect(
            Qt.LayoutDirection.LeftToRight,
            Qt.AlignmentFlag.AlignCenter,
            self.size,
            star_rect
        )

        if index.data(Qt.ItemDataRole.EditRole):
            painter.drawPixmap(centered_rect, self.star_on)
        else:
            painter.drawPixmap(centered_rect, self.star_off)

        painter.restore()
        super().paint(painter,option,index)

    def refresh_style(self):
        super().refresh_style()
        self.padding = app_theme.padding
        self.size = app_theme.icon_size

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        return self.size


class LabelItemDelegate(BaseStyledItemDelegate):

    def __init__(self, parent: QObject = None):
        super().__init__(parent)

        self.bulb = QIcon.fromTheme("light")


    def refresh_style(self):
        super().refresh_style()

        self.font_small = app_theme.font_small
        self.font_small_metrics = QFontMetrics(self.font_small)

        self.font_medium = app_theme.font_medium
        self.font_medium_metrics = QFontMetrics(self.font_medium)

        self.font_medium_bold = QFont(app_theme.font_medium)
        self.font_medium_bold_metrics = QFontMetrics(self.font_medium_bold)

        self.tag_margins = QMargins(6,3,6,3)
        self.text_margins = QMargins(4,2,4,2)

        self.brush_green = app_theme.get_green_brush()

        self.settings_tags_visible = AppSettings.value(SettingKeys.COLUMN_TAGS_VISIBLE, True, type=bool)
        self.settings_title_summary_visible = AppSettings.value(SettingKeys.COLUMN_TITLE_SUMMARY_VISIBLE, True, type=bool)
        self.settings_row_style = AppSettings.value(SettingKeys.SONGS_ROW_STYLE, "MEDIUM", type=str)
        self.settings_title_instead_filename = AppSettings.value(SettingKeys.SONGS_TITLE_INSTEAD_OF_FILE_NAME, False, type=bool)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex, /):
        self.initStyleOption(option, index)

        painter.save()

        #painter.setRenderHint(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        data: Mp3Entry = index.data(Qt.ItemDataRole.UserRole)

        content_rect = option.rect.marginsRemoved(self.cell_margin)

        # draw tags
        tag_left = content_rect.right()
        tag_top = content_rect.top() + 2

        if self.settings_tags_visible:
            painter.setFont(self.font_small)

            selected_tags: list[str] = self.parent().filter_config.tags
            green_tags = [x for x in data.tags if x in selected_tags]
            red_tags = [x for x in data.tags if x not in selected_tags]

            tag_padding_x = 6
            tag_padding_y = 3
            painter.setRenderHint(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
            for tag in green_tags + red_tags:
                bounding_rect = self.font_small_metrics.boundingRect(tag)

                # check if enough space for tag is left
                if content_rect.left() > tag_left - bounding_rect.width() - tag_padding_x * 2:
                    break

                tags_rect = QRect(tag_left - bounding_rect.width() - tag_padding_x, tag_top + tag_padding_y, bounding_rect.width(), bounding_rect.height())
                tags_rect = tags_rect.marginsAdded(self.tag_margins)

                if tag in selected_tags:
                    painter.setBrush(self.brush_green)
                else:
                    painter.setBrush(option.palette.accent())

                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(tags_rect, 6.0, 6.0)
                painter.setPen(Qt.GlobalColor.white)

                tags_rect = tags_rect.marginsRemoved(self.text_margins)
                painter.drawText(tags_rect, Qt.AlignmentFlag.AlignRight, tag)

                tag_left = tags_rect.left() - tag_padding_x * 2


            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)

        if data.light:
            bulb_rect = QRect(tag_left - app_theme.icon_width, tag_top, app_theme.icon_width, app_theme.icon_height)

            if data.color:
                bulb_colored: QPixmap = tint_icon(self.bulb, bulb_rect.size(), data.color)
                painter.drawPixmap(bulb_rect, bulb_colored)
            else:
                self.bulb.paint(painter, bulb_rect, alignment=Qt.AlignmentFlag.AlignCenter)

        # draw Texts
        if data.summary and self.settings_title_summary_visible:
            summary_rect = self.font_small_metrics.boundingRect(0, 0, content_rect.width(), 10000, Qt.TextFlag.TextWordWrap, data.summary)
        else:
            summary_rect = QRect(0,0,0,0)

        if (self.settings_title_summary_visible and self.settings_row_style != "SMALL"):
            title_font = self.font_medium_bold
            title_font_metrics = self.font_medium_metrics
        else:
            title_font = self.font_medium
            title_font_metrics = self.font_medium_bold_metrics

        title_rect = title_font_metrics.boundingRect(0, 0, content_rect.width(), 10000, Qt.TextFlag.TextSingleLine, data.title)

        needed_text_height = summary_rect.height() + title_rect.height()
        free_height = content_rect.height() - needed_text_height
        free_height = max(0, free_height)

        # draw rest
        painter.setPen(option.palette.color(QPalette.ColorRole.Text) if option.state & QStyle.StateFlag.State_Selected else option.palette.color(QPalette.ColorRole.WindowText))

        title_rect = QRect(content_rect)
        title_rect.setRight(tag_left)
        title_rect.setTop(content_rect.top() + free_height // 2)
        title_rect.setHeight(title_font_metrics.height())

        painter.setFont(title_font)

        title = data.title if self.settings_title_instead_filename and data.title is not None and data.title != "" else data.name
        painter.drawText(title_rect, title)

        if data.summary and self.settings_title_summary_visible:
            painter.setFont(self.font_small)
            painter.setPen(option.palette.color(QPalette.ColorRole.BrightText))

            # 2. Calculate the bounding rectangle
            summary_rect = self.font_small_metrics.boundingRect(0, 0,  content_rect.width(), 10000, Qt.TextFlag.TextWordWrap, data.summary)

            summary_rect.moveLeft(content_rect.left())
            summary_rect.moveTop(title_rect.bottom())
            painter.setClipRect(content_rect)
            painter.drawText(summary_rect, Qt.TextFlag.TextWordWrap, data.summary)

        painter.restore()

        super().paint(painter, option, index)
