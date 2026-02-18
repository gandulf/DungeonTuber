import functools
import os
from pathlib import Path
from os import PathLike

from PySide6.QtCore import QModelIndex, QFileInfo, QPersistentModelIndex, QEvent, QSortFilterProxyModel, Qt, QDir, \
    Signal, QRect, QSize, QAbstractTableModel, \
    QObject, QPoint, QItemSelection, QAbstractItemModel
from PySide6.QtGui import QIcon, QAction, QColor, QPainter, QFont, QFontMetrics, QPalette, QPen, QDropEvent, QKeyEvent, \
    QDragEnterEvent, QDragMoveEvent, QPaintEvent
from PySide6.QtWidgets import QMenu, QFileSystemModel, QFileIconProvider, QTreeView, QAbstractScrollArea, QListView, QStyleOptionViewItem, QStyle, QWidget, \
    QStyledItemDelegate, QHeaderView, QAbstractItemView, QTableView, QApplication

from components.dialogs import EditSongDialog
from logic.analyzer import Analyzer
from logic.mp3 import parse_mp3, Mp3Entry, append_m3u, update_mp3_tags, remove_m3u, update_mp3_favorite, Mp3FileLoader, \
    save_playlist

from components.widgets import FileFilterProxyModel, StarRating
from components.models import SongTableModel, SongTableProxyModel

from config.settings import AppSettings, SettingKeys, CAT_VALENCE, CAT_AROUSAL, MusicCategory, FilterConfig
from config.theme import app_theme

class AutoSearchHelper():
    _ignore_keys = [Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right]

    def __init__(self, proxy_model: QSortFilterProxyModel, parent: QAbstractScrollArea = None):
        self.parent = parent
        self.proxy_model = proxy_model
        self.search_string = ""

    def keyPressEvent(self, event: QKeyEvent):
        # If user presses Backspace, remove last char
        if event.key() in self._ignore_keys:
            return False

        if event.key() == Qt.Key.Key_Backspace:
            self.search_string = self.search_string[:-1]
        # If it's a valid character (letter/number), append to search
        elif event.text().isalnum() or event.text() in " _-":
            self.search_string += event.text()
        # If Escape is pressed, clear filter
        elif event.key() == Qt.Key.Key_Escape:
            self.search_string = ""
        else:
            return False

        # Apply the filter to the proxy
        self.proxy_model.setFilterFixedString(self.search_string)

        self.parent.viewport().update()

        return True

    def paintEvent(self, event: QPaintEvent):
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


class SongTable(QTableView):
    item_double_clicked = Signal(QPersistentModelIndex, Mp3Entry)
    content_changed = Signal()

    playlist: PathLike[str] = None
    directory: PathLike[str] = None

    table_model: SongTableModel
    proxy_model: SongTableProxyModel

    def __init__(self, _analyzer: Analyzer, _music_player):
        super().__init__()

        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
        self.setSortingEnabled(True)

        self.table_model = SongTableModel([], self)
        self.media_player = _music_player
        self.filter_config = self.media_player.filter_widget.filter_config
        self.analyzer = _analyzer

        self.proxy_model = SongTableProxyModel(self)
        self.proxy_model.sort_changed.connect(self.on_sort_changed)
        self.proxy_model.setDynamicSortFilter(True)
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.setFilterRole(Qt.ItemDataRole.DisplayRole)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(SongTableModel.FILE_COL)

        self.setModel(self.proxy_model)

        self.auto_search_helper = AutoSearchHelper(self.proxy_model, self)

        self.update_column_widths()

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)

        self.verticalHeader().setVisible(False)
        self.update_font_sizes()

        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self.show_header_context_menu)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.setItemDelegateForColumn(SongTableModel.FILE_COL, SongTable.LabelItemDelegate(self))
        self.setItemDelegateForColumn(SongTableModel.FAV_COL, SongTable.StarDelegate(self))

        self.setStyleSheet('QTableView::item {padding: 0px 3px;}')
        self.doubleClicked.connect(self.on_table_double_click)

        self.source_files: list[Path] = []
        self.is_loaded = False
        self.loader = None


    def get_available_categories(self) -> list[MusicCategory]:
        return self.table_model.available_categories

    def get_available_tags(self) -> list[str]:
        return self.table_model.available_tags

    def get_available_genres(self) -> list[str]:
        return self.table_model.available_genres

    def set_filter_config(self,filter_config: FilterConfig):
        self.filter_config = filter_config
        self.table_model.set_filter_config(filter_config)

        self.update_category_column_visibility()

        self.selectRow(0)
        self.sortByColumn(SongTableModel.SCORE_COL, Qt.SortOrder.AscendingOrder)


    def calc_header_width(self, index:int):
        font_metrics = self.horizontalHeader().fontMetrics()
        self.horizontalHeader().contentsMargins().left()
        name = self.table_model.headerData(index, Qt.Orientation.Horizontal, role=Qt.ItemDataRole.DisplayRole)
        return 12 + self.horizontalHeader().contentsMargins().left() + self.horizontalHeader().contentsMargins().right()+ font_metrics.horizontalAdvance(name)

    def update_column_widths(self):
        self.setColumnWidth(SongTableModel.INDEX_COL, 28)
        self.setColumnWidth(SongTableModel.FAV_COL, 48)
        self.setColumnWidth(SongTableModel.FILE_COL, 400)
        self.resizeColumnToContents(SongTableModel.TITLE_COL)
        self.resizeColumnToContents(SongTableModel.ALBUM_COL)
        self.resizeColumnToContents(SongTableModel.GENRE_COL)
        self.resizeColumnToContents(SongTableModel.ARTIST_COL)
        for index in range(SongTableModel.CAT_COL, self.columnCount()):
            self.setColumnWidth(index, self.calc_header_width(index))

        for index in [SongTableModel.BPM_COL, SongTableModel.SCORE_COL]:
            self.setColumnWidth(index, self.calc_header_width(index))

        self.horizontalHeader().setSectionResizeMode(SongTableModel.FAV_COL, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(SongTableModel.FILE_COL, QHeaderView.ResizeMode.Stretch)
        # self.horizontalHeader().setStretchLastSection(True)

    def set_files(self, files: list[Path]):
        self.source_files = files
        self.is_loaded = False
        self.unload()

    def load(self):
        if self.is_loaded or self.loader is not None:
            return

        self.loader = Mp3FileLoader(self.source_files, self)
        self.loader.files_loaded.connect(self.on_load_progress)
        self.loader.finished.connect(self.on_load_finished)
        self.loader.start()

    def unload(self):
        if self.loader:
            self.loader.stop()
            self.loader = None

        self.populate_table([])
        self.is_loaded = False

    def on_load_progress(self, entries: list):
        self.table_model.addRows(entries)

    def on_load_finished(self):
        self.is_loaded = True
        self.loader = None
        self.content_changed.emit()

    def update_font_sizes(self):
        if AppSettings.value(SettingKeys.COLUMN_SUMMARY_VISIBLE, True, type=bool):
            self.verticalHeader().setDefaultSectionSize((app_theme.font_size * 4.0) + 2)
        else:
            self.verticalHeader().setDefaultSectionSize((app_theme.font_size * 2.0) + 2)

    def changeEvent(self, event: QEvent, /):
        if event.type() == QEvent.Type.FontChange:
            self.update_font_sizes()
            self.update_column_widths()

    def on_sort_changed(self, column, order_by):
        self.setDragEnabled(column == 0)

    def show_header_context_menu(self, point):
        menu = QMenu(self)

        # Index
        if self.playlist is not None:
            index_action = QAction(_("Index"), self)
            index_action.setCheckable(True)
            index_action.setChecked(AppSettings.value(SettingKeys.COLUMN_INDEX_VISIBLE, True, type=bool))
            index_action.triggered.connect(
                lambda checked: self.toggle_column_setting(SettingKeys.COLUMN_INDEX_VISIBLE, checked))
            menu.addAction(index_action)

        # Favorite
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

        toggle_tags_action = QAction(_("Tags"), self)
        toggle_tags_action.setCheckable(True)
        toggle_tags_action.setChecked(AppSettings.value(SettingKeys.COLUMN_TAGS_VISIBLE, True, type=bool))
        toggle_tags_action.triggered.connect(
            lambda checked: self.toggle_column_setting(SettingKeys.COLUMN_TAGS_VISIBLE, checked))
        menu.addAction(toggle_tags_action)

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
            data = self.mp3_data(index.row())
            self.item_double_clicked.emit(index, data)
        elif index.column() == SongTableModel.FAV_COL:
            data = self.mp3_data(index.row())
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

    def populate_table(self, table_data: list[Mp3Entry]):
        self.table_model = SongTableModel(table_data, self)
        self.table_model.on_mime_drop.connect(self.update_playlist)
        self.proxy_model.setSourceModel(self.table_model)

        self.update_category_column_visibility()

        self.is_loaded = True

    def update_playlist(self):
        if self.playlist is not None:
            save_playlist(self.playlist, self.mp3_datas())

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

        self.update_font_sizes()

    def get_raw_data(self)-> list[Mp3Entry]:
        return self.table_model._data

    def mp3_datas(self) -> list[Mp3Entry]:
        if self.model() is not None:
            return [self.mp3_data(row) for row in range(self.rowCount())]
        else:
            return []

    def index_of(self, entry: Mp3Entry) -> QModelIndex:
        for row in range(self.rowCount()):
            if self.mp3_data(row).path == entry.path:
                return self.model().index(row,0)

        return self.model().index(-1,0)

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
            index = self.index_of(data)
            if index.isValid():
                self.model().setData(index, data, Qt.ItemDataRole.UserRole)
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


    def show_context_menu(self, point: QPoint):
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
                for path in paths:
                    self.media_player.load_directory(path, activate=True)
            elif all(path.suffix.lower() == ".m3u" for path in paths):
                event.accept()
                for path in paths:
                    self.media_player.load_playlist(path, activate=True)
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

        def setModelData(self, editor : QWidget, model : QAbstractTableModel, index: QModelIndex | QPersistentModelIndex):
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

        def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
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
            painter.setRenderHint(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
            data = index.model().data(index, Qt.ItemDataRole.UserRole)

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



class DirectoryTree(QTreeView):
    file_opened = Signal(QFileInfo)


    def __init__(self, parent: QWidget | None, media_player):
        super().__init__(parent)

        self.media_player = media_player
        self.setMinimumWidth(150)
        self.setDragEnabled(True)

        self.open_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen), _("Open"), self)
        self.open_action.triggered.connect(self.do_open_action)

        self.edit_song_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.EditPaste), _("Edit Song"), self)
        self.edit_song_action.triggered.connect(self.edit_song)

        self.analyze_file_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.Scanner), _("Analyze"))
        self.analyze_file_action.triggered.connect(self.do_analyze_file)

        self.go_parent_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.GoUp), _("Go to parent"), self)
        self.go_parent_action.triggered.connect(self.do_parent_action)

        self.set_home_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.GoNext), _("Go Into"), self)
        self.set_home_action.triggered.connect(self.do_set_home_action)

        self._source_root_index = QPersistentModelIndex()

        self.directory_model = QFileSystemModel()
        self.directory_model.setReadOnly(True)
        self.directory_model.setIconProvider(QFileIconProvider())
        self.directory_model.setRootPath(QDir.rootPath())
        self.directory_model.setNameFilters(["*.mp3", "*.m3u"])
        self.directory_model.setNameFilterDisables(False)

        self.proxy_model = FileFilterProxyModel()
        self.proxy_model.setSourceModel(self.directory_model)

        self.directory_model.directoryLoaded.connect(self.on_directories_loaded)
        self.setModel(self.proxy_model)
        self.setIndentation(16)
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
            if index.isValid():
                self.set_root_index_in_source(index)
        else:
            music = os.path.join(Path.home(), "Music")
            if os.path.isdir(music):
                index = self.directory_model.index(music)
            else:
                index = self.directory_model.index(os.path.abspath(Path.home()))

            if index.isValid():
                self.set_root_index_in_source(index)

    def changeEvent(self, event: QEvent, /):
        if event.type() == QEvent.Type.FontChange:
            list_font = self.font()
            list_font.setPointSizeF(app_theme.font_size)
            self.setFont(list_font)

    def on_directories_loaded(self):
        self.proxy_model.beginFilterChange()

        self.proxy_model.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection, /):
        if len(self.selectedIndexes()) > 0:
            self.set_home_action.setEnabled(True)
            self.open_action.setEnabled(True)
        else:
            self.set_home_action.setEnabled(False)
            self.open_action.setEnabled(False)

    def keyPressEvent(self, event: QKeyEvent):
        if self.autoSearchHelper.keyPressEvent(event):
            self._apply_proxy_root()
            self.viewport().update()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)
        self.autoSearchHelper.paintEvent(event)

    def set_root_index_in_source(self, source_index: QModelIndex):
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

    def show_context_menu(self, point: QPoint):
        # model_index = self.indexAt(point)

        menu = QMenu(self)

        menu.addAction(self.open_action)

        #
        datas = [self.mp3_data(model_index) for model_index in self.selectionModel().selectedRows()]
        datas = [data for data in datas if data is not None]
        if len(datas) > 0:
            menu.addAction(self.edit_song_action)
            if AppSettings.value(SettingKeys.VOXALYZER_URL, "", type=str) != "":
                menu.addAction(self.analyze_file_action)

            add_to_playlist = QMenu(_("Add to playlist"), icon=QIcon.fromTheme(QIcon.ThemeIcon.ListAdd))

            add_new_action = add_to_playlist.addAction(_("<New Playlist>"))
            add_new_action.setIcon(QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical))
            add_new_action.triggered.connect(functools.partial(self.media_player.pick_new_playlist, datas))

            for playlist in self.media_player.get_playlists():
                add_action = add_to_playlist.addAction(Path(playlist).name.removesuffix(".m3u").removesuffix(".M3U"))
                add_action.setIcon(QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical))
                add_action.triggered.connect(functools.partial(self.media_player.add_to_playlist, playlist, datas))

            menu.addMenu(add_to_playlist)

        menu.addSeparator()

        #
        menu.addAction(self.go_parent_action)
        menu.addAction(self.set_home_action)

        #
        menu.show()
        menu.exec(self.mapToGlobal(point))

    def do_parent_action(self):
        if self.rootIndex().isValid() and self.rootIndex().parent() is not None:
            index = self.rootIndex().parent()
            self._set_root_index(index)

    def do_open_action(self):
        index = self.selectedIndexes()[0]
        self.file_opened.emit(index.data(QFileSystemModel.Roles.FileInfoRole))

    def do_analyze_file(self):
        for index in self.selectedIndexes():
            source_index = self.proxy_model.mapToSource(index)
            file_path = self.directory_model.filePath(source_index)
            self.media_player.analyzer.process(file_path)

    def double_clicked_action(self, index: QModelIndex | QPersistentModelIndex):
        file_info = index.data(QFileSystemModel.Roles.FileInfoRole)
        if file_info.isFile():
            self.file_opened.emit(file_info)

    def _set_root_index(self, root_index: QModelIndex | QPersistentModelIndex):
        if root_index.isValid():
            source_index = self.proxy_model.mapToSource(root_index)
            AppSettings.setValue(SettingKeys.ROOT_DIRECTORY, self.directory_model.filePath(source_index))
            self.set_root_index_in_source(source_index)
            self.go_parent_action.setVisible(True)
        else:
            AppSettings.setValue(SettingKeys.ROOT_DIRECTORY, None)
            self.set_root_index_in_source(QModelIndex())
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


class EffectList(QListView):
    grid_threshold = 200

    def __init__(self, parent=None, list_mode: QListView.ViewMode = QListView.ViewMode.ListMode):
        super().__init__(parent)

        self.setItemDelegate(EffectListItemDelegate(parent=self))

        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setDynamicSortFilter(True)
        self.setModel(self.proxy_model)

        self.auto_search_helper = AutoSearchHelper(self.proxy_model, self)

        if list_mode == QListView.ViewMode.ListMode:
            self.set_list_view()
        else:
            self.set_grid_view()

    def setModel(self, model: QAbstractItemModel, /):
        if isinstance(model, QSortFilterProxyModel):
            super().setModel(model)
        else:
            self.proxy_model.setSourceModel(model)

    def changeEvent(self, event, /):
        if event.type() == QEvent.Type.FontChange:
            list_font = self.font()
            list_font.setPointSizeF(app_theme.font_size)
            self.setFont(list_font)

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

    def keyPressEvent(self, event: QKeyEvent):
        if not self.auto_search_helper.keyPressEvent(event):
            super().keyPressEvent(event)

    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)
        self.auto_search_helper.paintEvent(event)


class EffectListItemDelegate(QStyledItemDelegate):
    padding = 2
    view_mode: QListView.ViewMode

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        super().initStyleOption(option, index)
        # Remove the 'HasCheckIndicator' feature so Qt doesn't draw the box
        option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator

    def is_list_mode(self):
        return self.parent().viewMode() == QListView.ViewMode.ListMode

    def is_grid_mode(self):
        return self.parent().viewMode() == QListView.ViewMode.IconMode

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        # 1. Initialize the style option
        self.initStyleOption(option, index)

        painter.setClipRect(option.rect)

        effect_mp3 = index.data(Qt.ItemDataRole.UserRole)

        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        selected_state = option.state & QStyle.State_Selected

        if self.is_list_mode() and check_state == Qt.CheckState.Checked:
            # Change background for checked items
            painter.save()
            painter.setBrush(app_theme.get_green_brush(50))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(option.rect.adjusted(1, 1, -1, -1))
            painter.restore()

            # Make text bold for checked items
            option.font.setBold(True)

        if self.is_grid_mode() and effect_mp3 is not None and effect_mp3.cover is not None:
            painter.save()

            # 2. Draw the selection highlight/background
            # option.widget.style().drawControl(
            #     option.widget.style().ControlElement.CE_ItemViewItem,
            #     option, painter, option.widget
            # )

            # 3. Define the drawing area (the icon rectangle)
            # We use option.rect to get the full space for this item
            rect = option.rect.adjusted(self.padding, self.padding, -self.padding, -self.padding)

            # 4. Draw the Icon
            icon = option.icon
            if icon:
                pixmap = icon.pixmap(rect.size())

                if not pixmap.isNull():
                    # Logic: Calculate how to scale the pixmap to fill the target_rect
                    # while preserving aspect ratio (Aspect Ratio Fill/Crop)
                    pix_size = pixmap.size()
                    scaled_size = pix_size.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding)

                    # Calculate the top-left to center the "crop"
                    x = rect.x() + (rect.width() - scaled_size.width()) // 2
                    y = rect.y() + (rect.height() - scaled_size.height()) // 2

                    painter.setClipRect(rect)
                    # Draw the scaled and centered pixmap
                    # Painter's clipping (set at top of method) ensures the overflow is hidden
                    painter.drawPixmap(x, y, scaled_size.width(), scaled_size.height(), pixmap)

                #icon.paint(painter, rect, Qt.AlignmentFlag.AlignCenter)

            # 5. Draw the Text on top
            text = index.data(Qt.ItemDataRole.DisplayRole)
            if text:
                # Optional: Add a subtle shadow or background for readability
                # painter.fillRect(rect, QColor(0, 0, 0, 100))

                label_height = painter.fontMetrics().height() + self.padding
                label_rect = QRect(rect.left(), rect.bottom() - label_height, rect.width(), label_height+1)

                mask_color = option.palette.color(QPalette.ColorRole.Highlight) if selected_state else option.palette.color(QPalette.ColorRole.Dark)
                mask_color.setAlphaF(0.5)

                painter.setBrush(mask_color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(label_rect)

                painter.setPen(Qt.GlobalColor.white)  # Contrast color
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)

            painter.restore()

            painter.save()
            if check_state == Qt.CheckState.Checked:
                pen = QPen(option.palette.color(QPalette.ColorRole.Accent))
                pen.setWidth(5)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)
            elif selected_state:
                highlight_color = option.palette.color(QPalette.ColorRole.Highlight)
                highlight_color.setAlphaF(0.5)
                pen = QPen(highlight_color)
                pen.setWidth(3)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)
            painter.restore()
        else:
            super().paint(painter, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
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
                size.setHeight(size.height() + self.padding)
            else:
                size.setHeight(48)
        return size


