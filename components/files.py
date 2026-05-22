import os
from pathlib import Path

from PySide6.QtCore import QModelIndex, QFileInfo, QPersistentModelIndex, QEvent, QSortFilterProxyModel, Qt, QDir, \
    Signal, QObject, QPoint, QItemSelection, QConcatenateTablesProxyModel
from PySide6.QtGui import QIcon, QAction, QKeyEvent, QPaintEvent, QAbstractFileIconProvider, QPalette, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QMenu, QFileSystemModel, QFileIconProvider, QTreeView, QWidget, \
    QVBoxLayout, QAbstractItemView, QFrame, QListWidget, QListView, QSizePolicy

from components.dialogs import EditSongDialog
from components.widgets import IconLabel, AutoSearchHelper, ToolButton
from config.settings import AppSettings, SettingKeys
from config.theme import app_theme, get_list_palette
from logic.mp3 import parse_mp3, Mp3Entry


class FavoritesList(QListView):
    favorite_opened = Signal(QFileInfo)
    favorite_removed = Signal(QFileInfo)

    def __init__(self, parent: QObject = None):
        super().__init__(parent)

        self.setUniformItemSizes(True)
        self.setWordWrap(False)
        self.setIconSize(app_theme.icon_size)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setPalette(get_list_palette(self.palette()))

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in [Qt.Key.Key_Enter, Qt.Key.Key_Return]:
            index = self.selectionModel().currentIndex()
            file_info = index.data(QFileSystemModel.Roles.FileInfoRole)
            self.favorite_opened.emit(file_info)
        elif event.key() in [Qt.Key.Key_Delete, Qt.Key.Key_Backspace]:
            index = self.selectionModel().currentIndex()
            file_info = index.data(QFileSystemModel.Roles.FileInfoRole)
            self.favorite_removed.emit(file_info)
        else:
            super().keyPressEvent(event)

class CustomIconProvider(QFileIconProvider):
    def __init__(self):
        super().__init__()
        # Pre-load icons to save memory/processing
        self.refresh_icons()

    def refresh_icons(self):
        self.music_icon = QIcon.fromTheme("file-mp3")
        folder_open_icon = QIcon.fromTheme("folder-open")
        folder_icon = QIcon.fromTheme("folder-closed")

        self.folder_icon = QIcon()
        self.folder_icon.addPixmap(folder_icon.pixmap(app_theme.icon_size), QIcon.Normal,
                                   QIcon.Off)  # State: Off (Closed)
        self.folder_icon.addPixmap(folder_open_icon.pixmap(app_theme.icon_size), QIcon.Normal,
                                   QIcon.On)  # State: On (Open)

        self.playlist_icon = QIcon.fromTheme("list-music")

    def is_drive(self, file_info: QFileInfo) -> bool:
        return file_info and file_info.absoluteFilePath().endswith(":/")

    def icon(self, info: QFileInfo | QAbstractFileIconProvider.IconType):
        # 1. Check if it's a directory
        if isinstance(info,QAbstractFileIconProvider.IconType):
            if info == QAbstractFileIconProvider.IconType.Folder:
                return self.folder_icon
            elif info == QAbstractFileIconProvider.IconType.Drive:
                return QIcon.fromTheme(QIcon.ThemeIcon.DriveHarddisk)
            elif info == QAbstractFileIconProvider.IconType.Network:
                return QIcon.fromTheme(QIcon.ThemeIcon.NetworkWired)
            elif info == QAbstractFileIconProvider.IconType.Computer:
                return QIcon.fromTheme(QIcon.ThemeIcon.Computer)
            else:
                return super().icon(info)

        elif isinstance(info, QFileInfo):
            if self.is_drive(info):
                return QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical)
            elif info.isDir():
                return self.folder_icon

            # 2. Check extension for specific files
            if info.suffix().lower() == "mp3":
                return self.music_icon
            elif info.suffix().lower() == "m3u":
                return self.playlist_icon

            # 3. Fallback to the system default icon for everything else
            return super().icon(info)


class FileFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # 0 is usually the 'Name' column in QFileSystemModel
        self.setFilterKeyColumn(0)

        self.extensions = ["mp3","m3u"]
        self.file_cache = {}
        self.smart_filter = False

    def set_smart_filter(self, value:bool):
        if self.smart_filter != value:
            self.smart_filter = value
            self.invalidate()

    def data(self, index, role= Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        # 1. Check if we are looking at the 'Name' column and the DisplayRole
        if role == Qt.ItemDataRole.DisplayRole and index.column() == 0:
            # Get the original text (the filename with extension)
            source_data = super().data(index, role)

            if source_data:
                # Use QFileInfo to determine if it's a file
                # Note: index.data(QFileSystemModel.FilePathRole) is a handy way to get the path
                file_info = QFileInfo(source_data)

                # Only strip extension if it's a file, not a folder
                # .completeBaseName() returns everything before the LAST dot
                if len(file_info.completeBaseName()) >0:
                    return file_info.completeBaseName()
                else:
                    return file_info.fileName()
        elif role == Qt.ItemDataRole.ToolTipRole and index.column() == 0:
            source_data = super().data(index, Qt.ItemDataRole.DisplayRole)
            if source_data:
                file_info = QFileInfo(source_data)
                return file_info.fileName()

        # 2. Fall back to default behavior for everything else
        return super().data(index, role)

    def invalidateFilter(self, /):
        self.file_cache.clear()
        super().invalidateFilter()

    def lessThan(self, left: QModelIndex | QPersistentModelIndex, right: QModelIndex | QPersistentModelIndex):
        # 2. Check if the items are directories
        is_left_dir = left.data(Qt.ItemDataRole.FileInfoRole).isDir()
        is_right_dir = right.data(Qt.ItemDataRole.FileInfoRole).isDir()

        # 3. Logic: If one is a directory and the other isn't,
        # the directory is always "less than" (appears first)
        if is_left_dir and not is_right_dir:
            return self.sortOrder() == Qt.SortOrder.AscendingOrder

        if not is_left_dir and is_right_dir:
            return self.sortOrder() == Qt.SortOrder.DescendingOrder

        # 4. If both are the same type (both dirs or both files),
        # fall back to standard sorting (alphabetical, size, etc.)
        return super().lessThan(left, right)

    def _dir_has_valid_contents(self, path: str) -> bool:
        """
        Recursively scans a directory using Python's native os.scandir.
        Returns True if it contains at least one allowed file or non-empty folder.
        """
        try:
            if path in self.file_cache:
                return self.file_cache[path]

            has_files = False

            with os.scandir(path) as it:
                for entry in it:
                    # Always skip hidden files/folders (e.g., .git, .DS_Store)
                    if entry.name.startswith('.'):
                        continue

                    if entry.is_file():
                        # Otherwise, check if the file matches our extensions
                        if any(entry.name.lower().endswith(ext) for ext in self.extensions):
                            has_files= True
                            break

                    elif entry.is_dir():
                        # Recursively check if the subfolder has valid contents
                        if self._dir_has_valid_contents(entry.path):
                            has_files= True
                            break
        except PermissionError:
            has_files = False  # Drop folders we don't have permission to read

        self.file_cache[path] = has_files
        return has_files

    def ignore(self, file_info: QFileInfo) -> bool:
        if file_info.isHidden() or file_info.fileName().startswith('.'):
            return True

        if file_info.isFile() and not file_info.suffix() in self.extensions:
            return True

        return False
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex):
        source_model = self.sourceModel()
        source_index = source_model.index(source_row, 0, source_parent)

        # This ensures that if a file matches, its parent folders remain visible
        # Otherwise, the file would be hidden because its parent is filtered out
        if super().filterAcceptsRow(source_row, source_parent):
            file_info: QFileInfo = source_index.data(Qt.ItemDataRole.FileInfoRole)
            if self.ignore(file_info):
                return False

            if self.smart_filter and file_info.isDir():
                # Only display this folder if it contains valid files/subfolders
                return self._dir_has_valid_contents(file_info.filePath())

            return True

        # Check if any children match the filter
        for i in range(source_model.rowCount(source_index)):
            if self.filterAcceptsRow(i, source_index):
                return True
        return False


class DirectoryTree(QTreeView):
    file_opened = Signal(QFileInfo)
    directory_opened = Signal(QFileInfo)
    analyze_file = Signal(QFileInfo)
    open_context_menu = Signal(QMenu, list)

    favorite_added = Signal(QFileInfo)

    history: list[QPersistentModelIndex] = []

    def __init__(self, parent: QWidget | None):
        super().__init__(parent)

        self.setMinimumWidth(150)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.setDropIndicatorShown(True)
        self.setFont(app_theme.font_medium)

        self.open_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen), _("Open"), self)
        self.open_action.triggered.connect(self.do_open_action)

        self.edit_song_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.EditPaste), _("Edit Song"), self)
        self.edit_song_action.triggered.connect(self.edit_song)

        self.analyze_file_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.Scanner), _("Analyze"))
        self.analyze_file_action.triggered.connect(self.do_analyze_file)

        self.go_back_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.GoPrevious), _("Go Back"), self)
        self.go_back_action.triggered.connect(self.do_back_action)
        self.go_back_action.setDisabled(len(self.history) ==0)

        self.go_parent_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.GoUp), _("Go to parent"), self)
        self.go_parent_action.triggered.connect(self.do_parent_action)

        self.go_into_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.GoNext), _("Go Into"), self)
        self.go_into_action.triggered.connect(self.do_into_action)

        self.smart_filter_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.Scanner), _("Smart Filter"), self)
        self.smart_filter_action.setCheckable(True)
        self.smart_filter_action.setChecked(AppSettings.value(SettingKeys.FILES_SMART_FILTER, False, type=bool))
        self.smart_filter_action.triggered.connect(self.do_smart_filter)

        self.refreh_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.ViewRefresh), _("Refresh"), self)
        self.refreh_action.triggered.connect(self.do_refresh)

        self.add_favorite_action = QAction(QIcon.fromTheme("star"), _("Add to favorites"), self)
        self.add_favorite_action.triggered.connect(self.do_add_favorite_action)

        self._source_root_index = QPersistentModelIndex()

        self.directory_model = QFileSystemModel()
        self.directory_model.setReadOnly(False)
        # self.directory_icon_provider = CustomIconProvider()
        #self.directory_model.setIconProvider(self.directory_icon_provider)
        self.directory_model.setRootPath(QDir.rootPath())

        self.proxy_model = FileFilterProxyModel()
        self.proxy_model.set_smart_filter(AppSettings.value(SettingKeys.FILES_SMART_FILTER, False, type=bool))
        self.proxy_model.setSourceModel(self.directory_model)

        self.directory_model.directoryLoaded.connect(self.on_directories_loaded)
        self.setModel(self.proxy_model)
        self.setIndentation(16)
        self.setSortingEnabled(True)
        self.setHeaderHidden(True)
        self.setColumnHidden(1, True)
        self.setColumnHidden(2, True)
        self.setColumnHidden(3, True)
        self.setIconSize(app_theme.icon_size)
        self.setFont(app_theme.font_medium)
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

        self._refresh_palette()

    def _refresh_palette(self):
        self.setPalette(get_list_palette(self.palette()))
        self.update()

    def changeEvent(self, event: QEvent, /):
        if event.type() == QEvent.Type.FontChange:
            self.setFont(app_theme.font_medium)
            self.setIconSize(app_theme.icon_size)
        elif event.type() == QEvent.Type.PaletteChange:
            #self.directory_icon_provider.refresh_icons()
            #self.directory_model.setIconProvider(self.directory_icon_provider)
            self._refresh_palette()

    def on_directories_loaded(self):
        self.proxy_model.beginFilterChange()

        self.proxy_model.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection, /):
        if len(self.selectedIndexes()) > 0:
            self.go_into_action.setEnabled(True)
            self.open_action.setEnabled(True)
        else:
            self.go_into_action.setEnabled(False)
            self.open_action.setEnabled(False)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in [Qt.Key.Key_Enter, Qt.Key.Key_Return]:
            index = self.selectionModel().currentIndex()
            file_info = index.data(QFileSystemModel.Roles.FileInfoRole)
            self._open(file_info)
        elif self.autoSearchHelper.keyPressEvent(event):
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
        if file_info.isDir() or file_info.suffix().lower() == "m3u":
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
        self.open_context_menu.emit(menu, datas)
        menu.addSeparator()
        #
        menu.addAction(self.go_parent_action)
        menu.addAction(self.go_into_action)
        #
        menu.addSeparator()
        menu.addAction(self.smart_filter_action)
        menu.addAction(self.refreh_action)
        menu.addAction(self.add_favorite_action)

        menu.show()
        menu.exec(self.mapToGlobal(point))

    def do_parent_action(self):
        if self.rootIndex().isValid() and self.rootIndex().parent() is not None:
            index = self.rootIndex().parent()
            self._set_root_index(index)

    def do_open_action(self):
        index = self.selectedIndexes()[0]
        self._open(index.data(QFileSystemModel.Roles.FileInfoRole))

    def do_analyze_file(self):
        for index in self.selectedIndexes():
            source_index = self.proxy_model.mapToSource(index)
            file_info = self.directory_model.fileInfo(source_index)
            self.analyze_file.emit(file_info)

    def _open(self, file_info:QFileInfo):
        self.file_opened.emit(file_info)

    def double_clicked_action(self, index: QModelIndex | QPersistentModelIndex):
        file_info = index.data(QFileSystemModel.Roles.FileInfoRole)
        if file_info.isFile():
            self._open(file_info)

    def _set_root_index(self, root_index: QModelIndex | QPersistentModelIndex):
        if root_index.isValid():
            source_index = self.proxy_model.mapToSource(root_index)
            AppSettings.setValue(SettingKeys.ROOT_DIRECTORY, self.directory_model.filePath(source_index))
            self.set_root_index_in_source(source_index)
            self.go_parent_action.setVisible(True)


            self.history.append(QPersistentModelIndex(root_index))
            self.go_back_action.setDisabled(len(self.history) <= 1)
        else:
            AppSettings.setValue(SettingKeys.ROOT_DIRECTORY, None)
            self.set_root_index_in_source(QModelIndex())
            self.go_parent_action.setVisible(False)

    def do_back_action(self):
        if len(self.history) > 1:
            self.history.pop()
            self._set_root_index(self.history.pop())
        elif len(self.history) == 1:
            self._set_root_index(self.history.pop())

        self.go_back_action.setDisabled(len(self.history) <= 1)

    def do_refresh(self):
        self.proxy_model.invalidateFilter()
    def do_smart_filter(self, checked:bool):
        self.proxy_model.set_smart_filter(checked)
        AppSettings.setValue(SettingKeys.FILES_SMART_FILTER, checked)

    def do_add_favorite_action(self):
        for index in self.selectedIndexes():
            source_index = self.proxy_model.mapToSource(index)
            file_info = self.directory_model.fileInfo(source_index)
            self.favorite_added.emit(file_info)


    def do_into_action(self):
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


class DirectoryWidget(QFrame):
    favorites_list: FavoritesList = None

    def __init__(self, parent=None):
        super(DirectoryWidget, self).__init__(parent)

        self.setAutoFillBackground(True)
        self.setBackgroundRole(QPalette.ColorRole.Window)
        self.setGraphicsEffect(app_theme.drop_shadow(self))
        self.setContentsMargins(app_theme.margin_large)

        self.directory_layout = QVBoxLayout(self)
        self.directory_layout.setContentsMargins(0, 0, 0, 0)

        self.favHeaderLabel = IconLabel(QIcon.fromTheme("star"), _("Favorites"), parent=self)
        self.favHeaderLabel.set_icon_size(app_theme.icon_size)
        self.favHeaderLabel.text_label.setProperty("cssClass", "header")

        self.favorites_model = QStandardItemModel()

        self.favorites_list = FavoritesList(self)
        self.favorites_list.setModel(self.favorites_model)
        self.favorites_list.doubleClicked.connect(self.on_favorites_open)
        self.favorites_list.favorite_opened.connect(self.on_favorite_open)
        self.favorites_list.favorite_removed.connect(self.on_favorite_remove)
        self.favorites_list.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)

        open_favorite_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen), _("Open"), self)
        open_favorite_action.triggered.connect(self.on_favorite_open)

        remove_favorite_action = QAction(QIcon.fromTheme(QIcon.ThemeIcon.ListRemove), _("Remove from favorites"), self)
        remove_favorite_action.triggered.connect(self.on_favorite_remove)
        self.favorites_list.addAction(open_favorite_action)
        self.favorites_list.addAction(remove_favorite_action)

        self.filesHeaderLabel = IconLabel(QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen), _("Files"), parent=self)
        self.filesHeaderLabel.set_icon_size(app_theme.icon_size)
        self.filesHeaderLabel.text_label.setProperty("cssClass", "header")

        self.directory_tree = DirectoryTree(self)
        self.directory_tree.setContentsMargins(0, 0, 0, 0)
        self.directory_tree.favorite_added.connect(self.on_favorite_added)

        back_view_button = ToolButton(style="mini")
        back_view_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        back_view_button.setDefaultAction(self.directory_tree.go_back_action)
        self.filesHeaderLabel.add_widget(back_view_button)

        into_view_button = ToolButton(style="mini")
        into_view_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        into_view_button.setDefaultAction(self.directory_tree.go_into_action)
        self.filesHeaderLabel.add_widget(into_view_button)

        up_view_button = ToolButton(style="mini")
        up_view_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        up_view_button.setDefaultAction(self.directory_tree.go_parent_action)
        self.filesHeaderLabel.add_widget(up_view_button)

        self.directory_layout.addWidget(self.favHeaderLabel, 0)
        self.directory_layout.addWidget(self.favorites_list,0)
        self.directory_layout.addWidget(self.filesHeaderLabel, 0)
        self.directory_layout.addWidget(self.directory_tree,2)

        self.load_favorites()

    def on_favorite_added(self, file_info:QFileInfo):
        if not file_info in self.favorites:
            self.favorites_model.appendRow(self.create_native_favorite_item(file_info))
            self.store_favorites()
            self.invalidate_favorites()

    def load_favorites(self):

        for f in AppSettings.value(SettingKeys.FAVORITES, [], type=list):
            file_info = QFileInfo(f)
            if file_info.isDir():
                item = self.create_native_favorite_item(file_info)
                self.favorites_model.appendRow(item)

        self.invalidate_favorites()

    def invalidate_favorites(self):
        self.favorites_list.setFixedHeight(min(200, self.favorites_model.rowCount() * 35))

        self.favorites_list.setVisible(self.favorites_model.rowCount()>0)
        self.favHeaderLabel.setVisible(self.favorites_model.rowCount()>0)

        self.favorites = []
        for i in range(self.favorites_model.rowCount()):
            item = self.favorites_model.item(i)
            file_info = item.data(Qt.ItemDataRole.FileInfoRole)
            self.favorites.append(file_info)

    def store_favorites(self):
        favorites_files = []

        for i in range(self.favorites_model.rowCount()):
            item = self.favorites_model.item(i)
            file_info = item.data(Qt.ItemDataRole.FileInfoRole)
            favorites_files.append(file_info.filePath())

        AppSettings.setValue(SettingKeys.FAVORITES, favorites_files)

    def on_favorites_open(self, index: QModelIndex):
        self.directory_tree.file_opened.emit(index.data(Qt.ItemDataRole.FileInfoRole))

    def on_favorite_open(self):
        for index in self.favorites_list.selectedIndexes():
            self.directory_tree.file_opened.emit(index.data(Qt.ItemDataRole.FileInfoRole))

    def on_favorite_remove(self):
        rows_to_remove = sorted([idx.row() for idx in self.favorites_list.selectedIndexes()], reverse=True)

        for row in rows_to_remove:
            self.favorites_model.removeRow(row)

        self.invalidate_favorites()
        self.store_favorites()

    def create_native_favorite_item(self, file: str| QFileInfo) -> QStandardItem:

        if isinstance(file, QFileInfo):
            file_info = file
        else:
            file_info = QFileInfo(file)

        icon_provider = QFileIconProvider()

        # 2. Extract properties safely using QFileInfo

        native_icon = icon_provider.icon(file_info)

        clean_name = file_info.fileName()
        if not clean_name:
            clean_name = file

        item = QStandardItem()
        item.setText(clean_name)
        item.setIcon(native_icon)
        item.setEditable(False)

        # Stash the full system path inside a custom data role
        # so clicking it can still find the folder on disk later
        item.setData(file, role=Qt.ItemDataRole.UserRole)
        item.setData(file_info, role=Qt.ItemDataRole.FileInfoRole)
        item.setData(clean_name, Qt.ItemDataRole.ToolTipRole)

        return item

    def changeEvent(self, event, /):
        if event.type() in [QEvent.Type.FontChange, QEvent.Type.ApplicationFontChange]:
            self.filesHeaderLabel.set_icon_size(app_theme.icon_size)
            self.directory_tree.setFont(app_theme.font_medium)
        elif event.type() in [QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange]:
            self.setGraphicsEffect(app_theme.drop_shadow(self))
            if self.favorites_list:
                self.favorites_list.setPalette(get_list_palette(self.palette()))

