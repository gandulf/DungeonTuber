import logging
import math
import numbers
import os
import traceback
from os import PathLike
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Signal, Qt, QModelIndex, QMimeData, QByteArray, QDataStream, QIODevice, QPersistentModelIndex, \
    QAbstractTableModel, QSize, QObject, QEvent, QPoint, QFileInfo, QRect, QPointF
from PySide6.QtGui import QColor, QBrush, QIcon, QLinearGradient, QGradient, QAction, QKeyEvent, QDragMoveEvent, QDragEnterEvent, QPainter, QPalette, \
    QFontMetrics, QFont, QDropEvent, QPolygonF, QPainterStateGuard
from PySide6.QtWidgets import QMessageBox, QAbstractItemView, QWidget, QHeaderView, QMenu, QStyleOptionViewItem, QStyledItemDelegate, QStyle, QTableView
from sortedcontainers import SortedSet

from components.widgets import AutoSearchHelper
from config.settings import AppSettings, SettingKeys, MusicCategory, get_music_categories, CAT_VALENCE, \
    CAT_AROUSAL, FilterConfig
from config.theme import app_theme
from logic.mp3 import Mp3Entry, update_mp3_favorite, update_mp3_title, update_mp3_album, update_mp3_artist, update_mp3_genre, update_mp3_bpm, \
    update_mp3_category, Mp3FileLoader, save_playlist, remove_m3u, append_m3u, parse_mp3, update_mp3_tags, get_m3u_paths

logger = logging.getLogger(__file__)

def _get_bpm_background_brush(desired_value: int | None, value: int) -> QBrush | Qt.GlobalColor | None:
    if value is None or desired_value is None or desired_value == 0:
        return Qt.GlobalColor.transparent

    value_diff = abs(desired_value - value)

    if value_diff <= 40:
        return app_theme.get_green(51)
    elif value_diff <= 80:
        return app_theme.get_orange(51)
    else:
        return app_theme.get_red(51)

def _get_entry_background_brush(data: Mp3Entry):
    if data.color:
        background = QColor(data.color)
        background.setAlphaF(0.5)
        gradient = QLinearGradient(0, 0, 0, 1)
        gradient.setCoordinateMode(QGradient.CoordinateMode.ObjectBoundingMode);
        gradient.setColorAt(0.0, Qt.GlobalColor.transparent)
        gradient.setColorAt(0.3, Qt.GlobalColor.transparent)
        gradient.setColorAt(1.0, background)
        return QBrush(gradient)
    else:
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


def _get_score_background_brush(score: int | None) -> QBrush | Qt.GlobalColor | None:
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


def _get_category_background_brush(desired_value: int | None, value: int) -> QBrush | Qt.GlobalColor | None:
    if value is None or desired_value is None:
        return Qt.GlobalColor.transparent

    value_diff = abs(desired_value - value)

    if value_diff < 4:
        return app_theme.get_green(51)
    elif value_diff < 7:
        return app_theme.get_orange(51)
    else:
        return app_theme.get_red(51)


def _get_genre_background_brush(desired_values: list[str] | None, values: list[str]) -> QBrush | Qt.GlobalColor | None:
    if values is None or desired_values is None:
        return Qt.GlobalColor.transparent

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


PAINTING_SCALE_FACTOR = 20

class StarRating:
    """ Handle the actual painting of the stars themselves. """

    def __init__(self):

        # Create the star shape we'll be drawing.
        self._star_polygon = QPolygonF()
        self._star_polygon.append(QPointF(1.0, 0.5))
        for i in range(1, 5):
            self._star_polygon.append(QPointF(0.5 + 0.5 * math.cos(0.8 * i * math.pi),
                                              0.5 + 0.5 * math.sin(0.8 * i * math.pi)))

        # Create the diamond shape we'll show in the editor
        self._diamond_polygon = QPolygonF()
        diamond_points = [QPointF(0.4, 0.5), QPointF(0.5, 0.4),
                          QPointF(0.6, 0.5), QPointF(0.5, 0.6),
                          QPointF(0.4, 0.5)]
        self._diamond_polygon.append(diamond_points)

    def size_hint(self):
        return QSize(PAINTING_SCALE_FACTOR, PAINTING_SCALE_FACTOR)

    def paint(self, painter: QPainter, filled: bool, rect: QRect, palette: QPalette, brush: QBrush = None):
        """ Paint the stars (and/or diamonds if we're in editing mode). """
        with QPainterStateGuard(painter):
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            if brush is None:
                painter.setBrush(palette.windowText())
            else:
                painter.setBrush(brush)

            rect = rect.adjusted(5, 5, -5, -5)
            y_offset = (rect.height() - PAINTING_SCALE_FACTOR) / 2
            x_offset = (rect.width() - PAINTING_SCALE_FACTOR) / 2
            painter.translate(rect.x()+x_offset, rect.y() + y_offset)
            painter.scale(PAINTING_SCALE_FACTOR, PAINTING_SCALE_FACTOR)

            if filled:
                painter.drawPolygon(self._star_polygon, Qt.FillRule.WindingFill)
            else:
                painter.drawPolygon(self._star_polygon, Qt.FillRule.OddEvenFill)

class SongTableModel(QAbstractTableModel):
    INDEX_COL = 0
    FAV_COL = 1
    FILE_COL = 2
    TITLE_COL = 3
    ARTIST_COL = 4
    ALBUM_COL = 5
    GENRE_COL = 6
    BPM_COL = 7
    SCORE_COL = 8
    CAT_COL = 9

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
        self.available_categories = get_music_categories().copy()
        self._add_available_tags_and_categories(entries)

    def index_of(self, song: Mp3Entry):
        return self._data.index(song)

    def get_category_key(self, index: QModelIndex | int):
        if isinstance(index, int):
            return self.available_categories[index - SongTableModel.CAT_COL].key
        else:
            return self.available_categories[index.column() - SongTableModel.CAT_COL].key

    def get_category_name(self, index: QModelIndex | int):
        if isinstance(index, int):
            return self.available_categories[index - SongTableModel.CAT_COL].name
        else:
            return self.available_categories[index.column() - SongTableModel.CAT_COL].name

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

        if role == Qt.ItemDataRole.SizeHintRole:

            if AppSettings.value(SettingKeys.COLUMN_SUMMARY_VISIBLE, True, type=bool):
                height = 56
            else:
                height = 28

            if index.column() == SongTableModel.INDEX_COL:
                return QSize(20, height)
            elif index.column() == SongTableModel.FAV_COL:
                return QSize(20, height)
            elif index.column() == SongTableModel.FILE_COL:
                return QSize(300, height)
            else:
                return QSize(40, height)

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() >= SongTableModel.SCORE_COL or index.column() in [SongTableModel.BPM_COL, SongTableModel.INDEX_COL, SongTableModel.FAV_COL]:
                return Qt.AlignmentFlag.AlignCenter
        elif role == Qt.ItemDataRole.BackgroundRole:
            if index.column() == SongTableModel.SCORE_COL:
                score = index.data(Qt.ItemDataRole.DisplayRole)
                return _get_score_background_brush(score)
            elif index.column() == SongTableModel.GENRE_COL:
                value = index.data(Qt.ItemDataRole.UserRole)
                return _get_genre_background_brush(self.filter_config.genres, value.genres)
            elif index.column() == SongTableModel.BPM_COL:
                value = index.data(Qt.ItemDataRole.DisplayRole)
                return _get_bpm_background_brush(self.filter_config.bpm, value)
            elif index.column() >= SongTableModel.CAT_COL:
                value = index.data(Qt.ItemDataRole.DisplayRole)
                category_key = self.get_category_key(index)
                return _get_category_background_brush(self.filter_config.get_category(category_key, None), value)
            else:
                data = index.data(Qt.ItemDataRole.UserRole)
                return _get_entry_background_brush(data)

        elif role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            data = index.data(Qt.ItemDataRole.UserRole)
            if data is None:
                return None

            if index.column() == SongTableModel.INDEX_COL:
                data = index.data(Qt.ItemDataRole.UserRole)
                return self._data.index(data)
            if index.column() == SongTableModel.FAV_COL:
                return data.favorite
            elif index.column() == SongTableModel.FILE_COL:
                name = data.title if AppSettings.value(SettingKeys.SONGS_TITLE_INSTEAD_OF_FILE_NAME, False, type=bool) else data.name
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
                return self._calculate_score(data)
            elif index.column() >= SongTableModel.CAT_COL:
                category_key = self.get_category_key(index)
                return data.get_category_value(category_key)
            else:
                return None

        elif role == Qt.ItemDataRole.UserRole:
            return self._data[index.row()]
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
                return self.get_category_name(section)

        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex, /) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled

        default_flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled

        if index.column() in [SongTableModel.INDEX_COL, SongTableModel.FAV_COL, SongTableModel.SCORE_COL, SongTableModel.FILE_COL]:
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

class SongTable(QTableView):
    item_double_clicked = Signal(QPersistentModelIndex, Mp3Entry)
    content_changed = Signal()

    file_analyzed = Signal(QFileInfo)
    files_opened = Signal(list[QFileInfo])
    open_context_menu = Signal(QMenu, list)

    playlist: PathLike[str] = None
    directory: PathLike[str] = None

    table_model: SongTableModel
    proxy_model: SongTableProxyModel

    def __init__(self, parent: QWidget | None = None, source: PathLike[str] = None, mp3_files: list[Path | Mp3Entry] = [], lazy: bool = False):
        super().__init__(parent)

        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
        self.setSortingEnabled(True)

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
        self.proxy_model.setFilterRole(Qt.ItemDataRole.DisplayRole)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(SongTableModel.FILE_COL)

        self.setModel(self.proxy_model)

        self.auto_search_helper = AutoSearchHelper(self.proxy_model, self)

        self._update_column_widths()

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)

        self.verticalHeader().setVisible(False)
        self._update_font_sizes()

        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._show_header_context_menu)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.setItemDelegate(SongTable.CategoryDelegate(self))
        self.setItemDelegateForColumn(SongTableModel.FILE_COL, SongTable.LabelItemDelegate(self))
        self.setItemDelegateForColumn(SongTableModel.FAV_COL, SongTable.StarDelegate(self))

        self.setStyleSheet('QTableView::item {padding: 0px 3px;}')
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
            return QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen)
        else:
            return QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical)

    def _load_files(self, mp3_files: list[Path | Mp3Entry], lazy: bool = False):
        if not mp3_files:
            QMessageBox.information(self, _("Scan"), _("No MP3 files found."))
            return

        if isinstance(mp3_files[0], Path):
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
            mp3_files = list(base_path.rglob("*.mp3"))
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
        self.horizontalHeader().contentsMargins().left()
        name = self.table_model.headerData(index, Qt.Orientation.Horizontal, role=Qt.ItemDataRole.DisplayRole)
        # padding + space for sort icon + text width
        return 16 + 12 + self.horizontalHeader().contentsMargins().left() + self.horizontalHeader().contentsMargins().right() + font_metrics.horizontalAdvance(
            name)

    def _update_column_widths(self):
        self.setColumnWidth(SongTableModel.INDEX_COL, 28)
        self.setColumnWidth(SongTableModel.FAV_COL, 48)
        self.setColumnWidth(SongTableModel.FILE_COL, 400)
        self.resizeColumnToContents(SongTableModel.TITLE_COL)
        self.resizeColumnToContents(SongTableModel.ALBUM_COL)
        self.resizeColumnToContents(SongTableModel.GENRE_COL)
        self.resizeColumnToContents(SongTableModel.ARTIST_COL)
        for index in range(SongTableModel.CAT_COL, self.columnCount()):
            self.setColumnWidth(index, self._calc_header_width(index))

        for index in [SongTableModel.BPM_COL, SongTableModel.SCORE_COL]:
            self.setColumnWidth(index, self._calc_header_width(index))

        self.horizontalHeader().setSectionResizeMode(SongTableModel.FAV_COL, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(SongTableModel.FILE_COL, QHeaderView.ResizeMode.Stretch)
        # self.horizontalHeader().setStretchLastSection(True)

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

    def _update_font_sizes(self):
        if AppSettings.value(SettingKeys.COLUMN_SUMMARY_VISIBLE, True, type=bool):
            self.verticalHeader().setDefaultSectionSize((app_theme.font_size * 4.0) + 2)
        else:
            self.verticalHeader().setDefaultSectionSize((app_theme.font_size * 2.0) + 2)

    def changeEvent(self, event: QEvent, /):
        if event.type() == QEvent.Type.FontChange:
            self._update_font_sizes()
            self._update_column_widths()

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

        # Title
        title_action = QAction(_("Title"), self)
        title_action.setCheckable(True)
        title_action.setChecked(AppSettings.value(SettingKeys.COLUMN_TITLE_VISIBLE, False, type=bool))
        title_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_TITLE_VISIBLE, checked))
        menu.addAction(title_action)

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

        menu.addSeparator()

        file_name_action = QAction(_("Use mp3 title instead of file name"), self)
        file_name_action.setCheckable(True)
        file_name_action.setChecked(AppSettings.value(SettingKeys.SONGS_TITLE_INSTEAD_OF_FILE_NAME, True, type=bool))
        file_name_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.SONGS_TITLE_INSTEAD_OF_FILE_NAME, checked))
        menu.addAction(file_name_action)

        # Summary
        summary_action = QAction(_("Summary"), self)
        summary_action.setCheckable(True)
        summary_action.setChecked(AppSettings.value(SettingKeys.COLUMN_SUMMARY_VISIBLE, True, type=bool))
        summary_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_SUMMARY_VISIBLE, checked))
        menu.addAction(summary_action)

        toggle_tags_action = QAction(_("Tags"), self)
        toggle_tags_action.setCheckable(True)
        toggle_tags_action.setChecked(AppSettings.value(SettingKeys.COLUMN_TAGS_VISIBLE, True, type=bool))
        toggle_tags_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.COLUMN_TAGS_VISIBLE, checked))
        menu.addAction(toggle_tags_action)

        menu.addSeparator()

        # Dynamic Columns
        dynamic_action = QAction(_("Dynamic Columns"), self)
        dynamic_action.setCheckable(True)
        dynamic_action.setChecked(AppSettings.value(SettingKeys.DYNAMIC_TABLE_COLUMNS, False, type=bool))
        dynamic_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.DYNAMIC_TABLE_COLUMNS, checked))
        menu.addAction(dynamic_action)

        menu.exec(self.horizontalHeader().mapToGlobal(point))

    def _toggle_column_setting(self, key, checked):
        AppSettings.setValue(key, checked)
        self.update_category_column_visibility()
        if key in [SettingKeys.COLUMN_SUMMARY_VISIBLE, SettingKeys.COLUMN_TAGS_VISIBLE]:
            self.viewport().update()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Enter:
            index = self.selectionModel().currentIndex()
            self.item_double_clicked.emit(index, index.data(Qt.ItemDataRole.UserRole))
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
            data = index.data(Qt.ItemDataRole.UserRole)
            self.item_double_clicked.emit(index, data)
        elif index.column() == SongTableModel.FAV_COL:
            data = index.data(Qt.ItemDataRole.UserRole)
            data.favorite = not data.favorite
            update_mp3_favorite(data.path, data.favorite)
            self.repaint()

    def refresh_item(self, file_path: PathLike[str]):
        data = parse_mp3(Path(file_path))
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

    def is_column_visible(self, category: str):
        if AppSettings.value(SettingKeys.DYNAMIC_TABLE_COLUMNS, False, type=bool):
            value = self.table_model.filter_config.get_category(category, None)
            return value is not None
        else:
            return True

    def update_category_column_visibility(self):
        self.setColumnHidden(SongTableModel.INDEX_COL, self.playlist is None or not AppSettings.value(SettingKeys.COLUMN_INDEX_VISIBLE, True, type=bool))
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

        for col, category in enumerate(self.table_model.available_categories):
            self.setColumnHidden(SongTableModel.CAT_COL + col, not self.is_column_visible(category.key))

        self._update_font_sizes()

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
            sourceIndex = self.model().index(sourceRow, 0)
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
                self.file_opened.emit([QFileInfo(path) for path in paths])
            elif all(path.suffix.lower() == ".m3u" for path in paths):
                event.accept()
                self.file_opened.emit([QFileInfo(path) for path in paths])
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

    class CategoryDelegate(QStyledItemDelegate):

        def __init__(self, parent: QObject = None):
            super().__init__(parent)

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
            self.initStyleOption(option, index)
            padding = 3
            option.rect = option.rect.adjusted(0, 0, 0, padding)
            super().paint(painter, option, index)

    class StarDelegate(QStyledItemDelegate):
        star_rating = StarRating()

        def __init__(self, parent: QObject = None):
            super().__init__(parent)

        def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
            self.initStyleOption(option, index)

            background = index.data(Qt.ItemDataRole.BackgroundRole)
            if option.state & QStyle.StateFlag.State_MouseOver:
                painter.fillRect(option.rect, option.palette.brush(QPalette.ColorGroup.Active, QPalette.ColorRole.AlternateBase))
            elif background:
                painter.fillRect(option.rect, background)

            fav_icon_color = app_theme.get_green_brush()
            self.star_rating.paint(painter, index.data(), option.rect, option.palette, fav_icon_color)

        def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
            return self.star_rating.size_hint()

    class LabelItemDelegate(QStyledItemDelegate):
        _size = QSize(300, 40)

        def __init__(self, parent: QObject = None):
            super().__init__(parent)

        def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
            return self._size

        def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex, /):
            self.initStyleOption(option, index)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
            data = index.data(Qt.ItemDataRole.UserRole)

            background = index.data(Qt.ItemDataRole.BackgroundRole)
            if option.state & QStyle.StateFlag.State_MouseOver:
                painter.fillRect(option.rect, option.palette.brush(QPalette.ColorGroup.Active, QPalette.ColorRole.AlternateBase))
            elif background:
                painter.fillRect(option.rect, background)

            content_rect = option.rect.adjusted(6, 4, -6, -4)
            pen = painter.pen()

            # draw tags
            tag_left = content_rect.right()

            if AppSettings.value(SettingKeys.COLUMN_TAGS_VISIBLE, True, type=bool):
                tags_font = QFont(option.font)
                tags_font.setBold(False)
                tags_font.setPointSizeF(app_theme.font_size_small)

                fm = QFontMetrics(tags_font)
                painter.setFont(tags_font)

                tag_top = content_rect.top() + 2

                green_tags = [x for x in data.tags if x in self.parent().filter_config.tags]
                red_tags = [x for x in data.tags if x not in self.parent().filter_config.tags]

                for tag in green_tags + red_tags:

                    bounding_rect = fm.boundingRect(tag)

                    tag_padding = 3

                    tags_rect = QRect(tag_left - bounding_rect.width(), tag_top, bounding_rect.width(),
                                      bounding_rect.height())
                    tags_rect.adjust(-tag_padding * 2, -tag_padding, tag_padding * 2, tag_padding)

                    if tag in self.parent().filter_config.tags:
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

            title = data.title if AppSettings.value(SettingKeys.SONGS_TITLE_INSTEAD_OF_FILE_NAME, False,
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
