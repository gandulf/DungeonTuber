import os
from pathlib import Path

from PySide6.QtCore import QModelIndex, QFileInfo, QPersistentModelIndex, QEvent, QSortFilterProxyModel, Qt, QDir, \
    Signal, QObject, QPoint, QItemSelection, QSize
from PySide6.QtGui import QIcon, QAction, QKeyEvent, \
    QPaintEvent, QColor, QPalette
from PySide6.QtWidgets import QMenu, QFileSystemModel, QFileIconProvider, QTreeView, QWidget, \
    QVBoxLayout, QToolButton, QAbstractItemView, QFrame, QGraphicsDropShadowEffect

from components.dialogs import EditSongDialog
from components.widgets import IconLabel, AutoSearchHelper
from config.settings import AppSettings, SettingKeys
from config.theme import app_theme
from logic.mp3 import parse_mp3, Mp3Entry


class CustomIconProvider(QFileIconProvider):
    def __init__(self):
        super().__init__()
        # Pre-load icons to save memory/processing
        self.music_icon = QIcon.fromTheme("file-mp3")
        folder_open_icon = QIcon.fromTheme("folder-open")
        folder_icon = QIcon.fromTheme("folder-closed")

        self.folder_icon = QIcon()
        self.folder_icon.addPixmap(folder_icon.pixmap(app_theme.icon_size), QIcon.Normal, QIcon.Off)  # State: Off (Closed)
        self.folder_icon.addPixmap(folder_open_icon.pixmap(app_theme.icon_size), QIcon.Normal, QIcon.On)  # State: On (Open)

        self.playlist_icon = QIcon.fromTheme("list-music")

    def icon(self, info: QFileInfo):
        # 1. Check if it's a directory
        if info.isDir():
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

    def data(self, index, role=Qt.DisplayRole):
        # 1. Check if we are looking at the 'Name' column and the DisplayRole
        if role == Qt.DisplayRole and index.column() == 0:
            # Get the original text (the filename with extension)
            source_data = super().data(index, role)

            # Use QFileInfo to determine if it's a file
            # Note: index.data(QFileSystemModel.FilePathRole) is a handy way to get the path
            file_info = QFileInfo(source_data)

            # Only strip extension if it's a file, not a folder
            # .completeBaseName() returns everything before the LAST dot
            return file_info.completeBaseName()

        # 2. Fall back to default behavior for everything else
        return super().data(index, role)

    def lessThan(self, left: QModelIndex | QPersistentModelIndex, right: QModelIndex | QPersistentModelIndex):
        # 1. Get a reference to the source model (QFileSystemModel)
        source_model = self.sourceModel()

        # 2. Check if the items are directories
        is_left_dir = source_model.isDir(left)
        is_right_dir = source_model.isDir(right)

        # 3. Logic: If one is a directory and the other isn't,
        # the directory is always "less than" (appears first)
        if is_left_dir and not is_right_dir:
            return self.sortOrder() == Qt.SortOrder.AscendingOrder

        if not is_left_dir and is_right_dir:
            return self.sortOrder() == Qt.SortOrder.DescendingOrder

        # 4. If both are the same type (both dirs or both files),
        # fall back to standard sorting (alphabetical, size, etc.)
        return super().lessThan(left, right)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex):
        # This ensures that if a file matches, its parent folders remain visible
        # Otherwise, the file would be hidden because its parent is filtered out
        if super().filterAcceptsRow(source_row, source_parent):
            return True

        # Check if any children match the filter
        source_model = self.sourceModel()
        source_index = source_model.index(source_row, 0, source_parent)
        for i in range(source_model.rowCount(source_index)):
            if self.filterAcceptsRow(i, source_index):
                return True
        return False


class DirectoryTree(QTreeView):
    file_opened = Signal(QFileInfo)
    analyze_file = Signal(QFileInfo)
    open_context_menu = Signal(QMenu, list)

    def __init__(self, parent: QWidget | None):
        super().__init__(parent)

        self.setMinimumWidth(150)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.setDropIndicatorShown(True)
        self.setFont(app_theme.font())

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
        self.directory_model.setReadOnly(False)
        self.directory_model.setIconProvider(CustomIconProvider())
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
        self.setIconSize(app_theme.icon_size)
        self.setFont(app_theme.font())
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
            self.setFont(app_theme.font())
            self.setIconSize(app_theme.icon_size)

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
            file_info = self.directory_model.fileInfo(source_index)
            self.analyze_file.emit(file_info)

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


class DirectoryWidget(QFrame):

    def __init__(self, parent=None):
        super(DirectoryWidget, self).__init__(parent)

        self.setContentsMargins(app_theme.margin)

        self.directory_layout = QVBoxLayout(self)
        self.directory_layout.setContentsMargins(0, 0, 0, 0)

        self.headerLabel = IconLabel(QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen), _("Files"), parent=self)
        self.headerLabel.set_icon_size(app_theme.icon_size)
        self.headerLabel.set_alignment(Qt.AlignmentFlag.AlignCenter)
        self.headerLabel.text_label.setProperty("cssClass", "header")

        self.directory_tree = DirectoryTree(self)
        self.directory_tree.setContentsMargins(0, 0, 0, 0)

        up_view_button = QToolButton()
        up_view_button.setProperty("cssClass", "mini")
        up_view_button.setDefaultAction(self.directory_tree.go_parent_action)
        self.headerLabel.insert_widget(0, up_view_button)

        self.directory_layout.addWidget(self.headerLabel)
        self.directory_layout.addWidget(self.directory_tree)

    def changeEvent(self, event, /):
        if event.type() == QEvent.Type.PaletteChange:
            self.headerLabel.set_icon(QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen))
        elif event.type() == QEvent.Type.FontChange:
            self.headerLabel.set_icon_size(app_theme.icon_size)
            self.directory_tree.setFont(app_theme.font())
