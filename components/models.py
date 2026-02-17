import logging
import numbers
import traceback

from sortedcontainers import SortedSet

from PySide6.QtCore import QSortFilterProxyModel, Signal, Qt, QModelIndex, QMimeData, QByteArray, QDataStream, QIODevice, QPersistentModelIndex, \
    QAbstractTableModel, QSize, QObject
from PySide6.QtGui import QColor, QBrush, QIcon
from PySide6.QtWidgets import QMessageBox

from logic.mp3 import Mp3Entry, update_mp3_favorite, update_mp3_title, update_mp3_album, update_mp3_artist, update_mp3_genre, update_mp3_bpm, \
    update_mp3_category

from config.theme import app_theme
from config.settings import AppSettings, SettingKeys, MusicCategory, get_music_tags, get_music_categories, CAT_VALENCE, \
    CAT_AROUSAL, FilterConfig

logger = logging.getLogger("main")

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
                    if not key in available_categories_keys and key in available_categories_keys:
                        self.available_categories.append(MusicCategory.from_key(key))
                        available_categories_keys.append(key)

    def _update_available_tags_and_categories(self, entries: list[Mp3Entry]):
        self.available_tags = SortedSet(get_music_tags().keys())
        self.available_genres.clear()
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
                except ValueError:
                    logger.error("Invalid value for category {0}: {1}", category_key, value)
                    return False

                # Update file_data_list
                has_changes = False

                if new_value is None:
                    if data.selected_categories is not None and category_key in data.selected_categories:
                        data.selected_categories[category_key] = None
                        has_changes = True
                elif new_value != data.selected_categories.get(category_key, None):
                    data.selected_categories[category_key] = new_value
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
                return self._get_score_background_brush(score)
            elif index.column() == SongTableModel.GENRE_COL:
                value = index.data(Qt.ItemDataRole.UserRole)
                return self._get_genre_background_brush(self.filter_config.genres, value.genres)
            elif index.column() == SongTableModel.BPM_COL:
                value = index.data(Qt.ItemDataRole.DisplayRole)
                return self._get_bpm_background_brush(self.filter_config.bpm, value)
            elif index.column() >= SongTableModel.CAT_COL:
                value = index.data(Qt.ItemDataRole.DisplayRole)
                category_key = self.get_category_key(index)
                return self._get_category_background_brush(self.filter_config.get_category(category_key, None), value)
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
                name = data.title if AppSettings.value(SettingKeys.TITLE_INSTEAD_OF_FILE_NAME, False, type=bool) else data.name
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

    def _get_genre_background_brush(self, desired_values: list[str] | None, values: list[str]) -> QBrush | Qt.GlobalColor | None:
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

    def _get_category_background_brush(self, desired_value: int | None, value: int) -> QBrush | Qt.GlobalColor | None:
        if value is None or desired_value is None:
            return Qt.GlobalColor.transparent

        value_diff = abs(desired_value - value)

        if value_diff < 4:
            return app_theme.get_green(51)
        elif value_diff < 7:
            return app_theme.get_orange(51)
        else:
            return app_theme.get_red(51)

    def _get_bpm_background_brush(self, desired_value: int | None, value: int) -> QBrush | Qt.GlobalColor | None:
        if value is None or desired_value is None or desired_value == 0:
            return Qt.GlobalColor.transparent

        value_diff = abs(desired_value - value)

        if value_diff <= 40:
            return app_theme.get_green(51)
        elif value_diff <= 80:
            return app_theme.get_orange(51)
        else:
            return app_theme.get_red(51)

    def _get_score_foreground_brush(self, score: int | None) -> QColor | Qt.GlobalColor| None:
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

    def _get_score_background_brush(self, score: int | None) -> QBrush | Qt.GlobalColor | None:
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


class EffectTableModel(QAbstractTableModel):
    _checked: QPersistentModelIndex = QPersistentModelIndex()

    def __init__(self, data: list[Mp3Entry]):
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

