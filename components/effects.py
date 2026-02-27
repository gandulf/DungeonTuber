import os

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QEvent, QSortFilterProxyModel, Qt, \
    Signal, QRect, QSize, QAbstractTableModel, QAbstractItemModel, QPoint, QSizeF
from PySide6.QtGui import QIcon, QAction, QColor, QPainter, QPalette, QPen, QKeyEvent, \
    QPaintEvent, QLinearGradient, QBrush, QGradient, QPainterStateGuard, QPixmap, QResizeEvent
from PySide6.QtWidgets import QMenu, QListView, QStyleOptionViewItem, QStyle, QWidget, \
    QStyledItemDelegate, QFileDialog, QToolButton, QPushButton, QVBoxLayout, QHBoxLayout, QAbstractItemView

from components.widgets import IconLabel, AutoSearchHelper, VolumeSlider
from config.settings import AppSettings, SettingKeys
from config.theme import app_theme
from logic.audioengine import AudioEngine
from logic.mp3 import EffectEntry, Mp3Entry


def _get_grid_width(total_width: int):
    if total_width < EffectList.grid_threshold:
        new_width = total_width -1
    elif total_width < EffectList.grid_threshold * 2:
        new_width = int(total_width / 2)
    else:
        new_width = int(total_width / 3)

    return new_width


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


class EffectTableModel(QAbstractTableModel):
    _checked: QPersistentModelIndex = QPersistentModelIndex()

    def __init__(self, data: list[EffectEntry]):
        super(EffectTableModel, self).__init__()
        self._data = data

    def index_of(self, song: EffectEntry):
        return self._data.index(song)

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return len(self._data)

    def columnCount(self, parent: QModelIndex = ...) -> int:
        return 1

    def get_checked_index(self):
        return self._checked

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        return super().flags(index) | Qt.ItemFlag.ItemIsUserCheckable

    def data(self, index, /, role=...):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.FontRole:
            return app_theme.font()
        if role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if self._checked == index else Qt.CheckState.Unchecked
        elif role == Qt.ItemDataRole.DecorationRole:
            data = index.data(Qt.ItemDataRole.UserRole)
            return data.cover if data.cover is not None else None
        elif role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            data = index.data(Qt.ItemDataRole.UserRole)
            return data.title if AppSettings.value(SettingKeys.EFFECTS_TITLE_INSTEAD_OF_FILE_NAME, False, type=bool) else data.name
        elif role == Qt.ItemDataRole.UserRole:
            return self._data[index.row()]
        elif role == Qt.ItemDataRole.BackgroundRole:
            data = index.data(Qt.ItemDataRole.UserRole)
            return _get_entry_background_brush(data.mp3_entry)
        else:
            return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):

        if role == Qt.ItemDataRole.CheckStateRole:
            if value == Qt.CheckState.Checked:
                self._checked = QPersistentModelIndex(index)

            # Notify the view that the data has changed so it repaints
            self.dataChanged.emit(index, index, [role])
            return True

        return super().setData(index, value, role)


class EffectList(QListView):
    grid_threshold = 200

    open_context_menu = Signal(QMenu, list)
    file_opened = Signal(Mp3Entry)

    def __init__(self, parent=None, list_mode: QListView.ViewMode = QListView.ViewMode.ListMode):
        super().__init__(parent)

        self.table_model = None
        self.setUniformItemSizes(True)
        self.setItemDelegate(EffectListItemDelegate(parent=self))
        self.setContentsMargins(0, 0, 0, 0)
        self.setViewportMargins(0, 0, 0, 0)
        self.setSpacing(0)
        self.verticalScrollBar().setSingleStep(30)
        self.verticalScrollBar().setBackgroundRole(QPalette.ColorRole.Accent)
        #self.verticalScrollBar().setMaximumWidth(app_theme.application.style().pixelMetric(QStyle.PM_ScrollBarExtent))
        self.setMouseTracking(True)
        self.setFont(app_theme.font())

        self.doubleClicked.connect(self.on_item_double_clicked)

        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setDynamicSortFilter(True)
        self.setModel(self.proxy_model)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.auto_search_helper = AutoSearchHelper(self.proxy_model, self)

        if list_mode == QListView.ViewMode.ListMode:
            self.set_list_view()
        else:
            self.set_grid_view()

    def get_raw_data(self) -> list[Mp3Entry]:
        return self.table_model._data

    def index_of(self, entry: Mp3Entry | EffectEntry) -> QModelIndex:
        try:
            if isinstance(entry, EffectEntry):
                sourceRow = self.get_raw_data().index(entry)
                sourceIndex = self.model().index(sourceRow, 0)
                return self.proxy_model.mapFromSource(sourceIndex)
            elif isinstance(entry, Mp3Entry):
                sourceRow = self.get_raw_data().index(entry)
                sourceIndex = self.model().index(sourceRow, 0)
                return self.proxy_model.mapFromSource(sourceIndex)

        except ValueError:
            return self.model().index(-1, 0)

    def show_context_menu(self, point):
        index = self.indexAt(self.mapFromGlobal(self.mapToGlobal(point)))
        menu = QMenu(self)

        datas = [model_index.data(Qt.ItemDataRole.UserRole).mp3_entry for model_index in self.selectionModel().selectedRows()]
        self.open_context_menu.emit(menu, datas)

        menu.addSeparator()

        menu.show()
        menu.exec(self.mapToGlobal(point))

    def setModel(self, model: QAbstractItemModel, /):
        if isinstance(model, QSortFilterProxyModel):
            super().setModel(model)
        else:
            self.table_model = model
            self.proxy_model.setSourceModel(model)

    def changeEvent(self, event, /):
        if event.type() == QEvent.Type.FontChange:
            self.setFont(app_theme.font())
            self.setIconSize(app_theme.icon_size)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.calculate_grid_size()

    def calculate_grid_size(self):
        if self.viewMode() == QListView.ViewMode.IconMode:
            new_width = _get_grid_width(self.viewport().width() - self.verticalScrollBar().width())
            new_height = int(new_width * (3 / 4))
            self.setGridSize(QSize(new_width, new_height))
            self.setIconSize(QSize())
        else:
            self.setGridSize(QSize())
            self.setIconSize(QSize(app_theme.font_size_px * 2, app_theme.font_size_px * 2))

    def set_list_view(self):
        AppSettings.setValue(SettingKeys.EFFECTS_LIST_VIEW_MODE, "ListMode")
        self.setViewMode(QListView.ViewMode.ListMode)
        self.setFlow(QListView.Flow.TopToBottom)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Fixed)
        self.verticalScrollBar().setSingleStep(15)

        self.calculate_grid_size()

        self.update()

    def set_grid_view(self):
        AppSettings.setValue(SettingKeys.EFFECTS_LIST_VIEW_MODE, "IconMode")
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.verticalScrollBar().setSingleStep(30)

        self.calculate_grid_size()

        self.update()

    def on_item_double_clicked(self, index: QModelIndex):
        data = index.data(Qt.ItemDataRole.UserRole).mp3_entry
        if isinstance(data, Mp3Entry):
            self.file_opened.emit(data)
            self.model().setData(index, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
            self.update()

    def on_item_intensity_changed(self, index: QModelIndex, intensity: int):
        effect_entry = index.data(Qt.ItemDataRole.UserRole)
        effect_entry.intensity = intensity

        checked_index = self.table_model.get_checked_index()
        proxy_index = self.proxy_model.mapFromSource(checked_index)
        if proxy_index.row() == index.row():
            self.file_opened.emit(effect_entry.mp3_entry)

        self.update()

    def keyPressEvent(self, event: QKeyEvent):
        if not self.auto_search_helper.keyPressEvent(event):
            super().keyPressEvent(event)

    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)
        self.auto_search_helper.paintEvent(event)


class EffectListItemDelegate(QStyledItemDelegate):
    MAX_BUTTONS = 5

    hover_intensity = None
    hover_index = None

    def __init__(self, parent: EffectList = None):
        super().__init__(parent)

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        super().initStyleOption(option, index)
        # Remove the 'HasCheckIndicator' feature so Qt doesn't draw the box
        option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator

    def is_list_mode(self):
        return self.parent().viewMode() == QListView.ViewMode.ListMode

    def is_grid_mode(self):
        return self.parent().viewMode() == QListView.ViewMode.IconMode

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease:
            mouse_pos = event.pos()
            effect_entry = index.data(Qt.ItemDataRole.UserRole)

            for idx in range(len(effect_entry.intensities)):
                if self.get_intensity_rect(option.rect, effect_entry, idx).contains(mouse_pos):
                    self.parent().on_item_intensity_changed(index, idx)
                    return True

        elif event.type() == QEvent.Type.MouseMove:
            mouse_pos = event.pos()
            effect_entry = index.data(Qt.ItemDataRole.UserRole)
            for idx in range(len(effect_entry.intensities)):
                if self.get_intensity_rect(option.rect, effect_entry, idx).contains(mouse_pos):
                    self.hover_intensity = idx
                    self.hover_index = index
                    return True

            self.hover_intensity = None
            self.hover_index = None

        return super().editorEvent(event, model, option, index)

    def get_intensity_rect(self, parent: QRect, effect_entry: EffectEntry, intensity: int = None):
        cnt = len(effect_entry.intensities)
        if intensity is None:
            intensity = effect_entry.intensity

        btn_padding_x = 4
        btn_size: QSize
        if self.is_grid_mode():
            btn_size = QSize(app_theme.font_size_px * 2, app_theme.font_size_px * 2)
            btn_padding_y = btn_padding_x
        else:
            btn_size = QSize(app_theme.font_size_px * 1.5, app_theme.font_size_px * 1.5)
            btn_padding_y = (parent.height() - btn_size.height()) // 2

        if (btn_size.width() + btn_padding_x) * self.MAX_BUTTONS + btn_padding_x > parent.width():
            new_size = (parent.width() - btn_padding_x * self.MAX_BUTTONS + 1) // self.MAX_BUTTONS
            btn_size.scale(new_size, new_size, Qt.AspectRatioMode.KeepAspectRatio)

        rect = QRect(parent.right() - (cnt - intensity) * (btn_size.width() + btn_padding_x), parent.top() + btn_padding_y, btn_size.width(), btn_size.height())
        return rect

    def _paint_list_item(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        selected_state = option.state & QStyle.State_Selected

        padding = app_theme.padding

        if check_state == Qt.CheckState.Checked:
            with QPainterStateGuard(painter):
                # Change background for checked items
                painter.setBrush(option.palette.brush(QPalette.ColorRole.Highlight))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(option.rect)

        rect: QRect = option.rect.adjusted(padding * 2, padding, -padding, -padding)

        if option.icon:
            pixmap = option.icon.pixmap(rect.size())
            if not pixmap.isNull():
                with QPainterStateGuard(painter):
                    # Logic: Calculate how to scale the pixmap to fill the target_rect
                    # while preserving aspect ratio (Aspect Ratio Fill/Crop)
                    pix_size = pixmap.size()
                    scaled_size: QSize = pix_size.scaled(rect.height(), rect.height(), Qt.AspectRatioMode.KeepAspectRatioByExpanding)

                    # Calculate the top-left to center the "crop"
                    x = rect.x()
                    y = rect.y() + (rect.height() - scaled_size.height()) // 2

                    icon_rect = QRect(x, y, scaled_size.width(), scaled_size.height())
                    painter.setClipRect(icon_rect)
                    # Draw the scaled and centered pixmap
                    # Painter's clipping (set at top of method) ensures the overflow is hidden
                    painter.drawPixmap(icon_rect, pixmap)

                    rect.setLeft(icon_rect.right() + padding)

        if option.text:
            with QPainterStateGuard(painter):
                label_rect = QRect(rect.left(), rect.top(), rect.width(), rect.height())


                if check_state == Qt.CheckState.Checked:
                    painter.setPen(option.palette.color(QPalette.ColorRole.HighlightedText))
                else:
                    painter.setPen(option.palette.color(QPalette.ColorRole.Text))

                painter.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, option.text)

        with QPainterStateGuard(painter):
            if selected_state:
                highlight_color = option.palette.color(QPalette.ColorRole.Accent)
                pen = QPen(highlight_color)
                pen.setWidth(2)
                painter.setPen(pen)

                p1: QPoint = option.rect.topLeft()
                p1.setX(p1.x() + padding)
                p1.setY(p1.y() + option.rect.height() * 0.25)
                p2: QPoint = option.rect.bottomLeft()
                p2.setX(p2.x() + padding)
                p2.setY(p2.y() - option.rect.height() * 0.25)
                painter.drawLine(p1, p2)

    def _paint_grid_item(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        selected_state = option.state & QStyle.State_Selected

        padding = 1
        # We use option.rect to get the full space for this item
        rect = option.rect.adjusted(padding, padding, -padding, -padding)

        # Draw the Icon
        icon = option.icon
        if icon:
            pixmap = icon.pixmap(rect.size())
            if not pixmap.isNull():
                with QPainterStateGuard(painter):
                    # Logic: Calculate how to scale the pixmap to fill the target_rect
                    # while preserving aspect ratio (Aspect Ratio Fill/Crop)
                    pix_size = pixmap.size()
                    scaled_size: QSize = pix_size.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding)

                    # Calculate the top-left to center the "crop"
                    x = rect.x() + (rect.width() - scaled_size.width()) // 2
                    y = rect.y() + (rect.height() - scaled_size.height()) // 2

                    painter.setClipRect(rect)
                    # Draw the scaled and centered pixmap
                    # Painter's clipping (set at top of method) ensures the overflow is hidden
                    painter.drawPixmap(x, y, scaled_size.width(), scaled_size.height(), pixmap)

        if option.text:
            with QPainterStateGuard(painter):
                label_height = painter.fontMetrics().height() + app_theme.padding
                label_rect = QRect(rect.left(), rect.bottom() - label_height, rect.width(), label_height + 1)

                if check_state == Qt.CheckState.Checked:
                    mask_color = option.palette.color(QPalette.ColorRole.Highlight)
                elif selected_state:
                    mask_color = option.palette.color(QPalette.ColorRole.Highlight)
                    mask_color.setAlphaF(0.5)
                else:
                    mask_color = option.palette.color(QPalette.ColorRole.Dark)
                    mask_color.setAlphaF(0.5)

                painter.setBrush(mask_color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(label_rect)

                painter.setPen(Qt.GlobalColor.white)  # Contrast color
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, option.text)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        self.initStyleOption(option, index)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)

        background = index.data(Qt.ItemDataRole.BackgroundRole)
        if background:
            painter.fillRect(option.rect, background)

        if self.is_grid_mode():
            self._paint_grid_item(painter, option, index)
        else:
            self._paint_list_item(painter, option, index)

        effect_entry = index.data(Qt.ItemDataRole.UserRole)
        cnt = len(effect_entry.intensities)
        if cnt > 1:
            with QPainterStateGuard(painter):
                for idx, entry in enumerate(effect_entry.intensities):
                    rect = self.get_intensity_rect(option.rect, effect_entry, intensity=idx)
                    if effect_entry.intensity == idx:
                        painter.setBrush(option.palette.color(QPalette.ColorRole.Highlight))
                    else:
                        painter.setBrush(option.palette.brush(QPalette.ColorRole.Base))
                    painter.setPen(Qt.GlobalColor.black)
                    painter.drawRoundedRect(rect, 2.0, 2.0)

                    if idx == self.hover_intensity and self.hover_index is not None and index.row() == self.hover_index.row():
                        painter.setPen(QPen(option.palette.color(QPalette.ColorRole.Text)))
                        painter.setBrush(option.palette.brush(QPalette.ColorGroup.Active, QPalette.ColorRole.AlternateBase))
                        painter.drawRoundedRect(rect, 2.0, 2.0)

                    if effect_entry.intensity == idx:
                        painter.setPen(QPen(option.palette.color(QPalette.ColorRole.HighlightedText)))
                    else:
                        painter.setPen(QPen(option.palette.color(QPalette.ColorRole.Text)))

                    rect.adjust(0, 0, -1, -1)
                    painter.drawText(rect, str(idx + 1), Qt.AlignmentFlag.AlignCenter)

        if option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, option.palette.brush(QPalette.ColorGroup.Active, QPalette.ColorRole.AlternateBase))

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        if self.is_grid_mode():
            return QSize(option.rect.width(), option.rect.height())
        else:
            return QSize(0, app_theme.font_size_px * 2)


class EffectWidget(QWidget):
    open_item: QPushButton = None

    def __init__(self, list_mode: QListView.ViewMode = QListView.ViewMode.ListMode):
        super().__init__()

        effects_dir = AppSettings.value(SettingKeys.EFFECTS_DIRECTORY, None, type=str)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.engine = AudioEngine(False)

        self.list_widget = EffectList(self, list_mode=list_mode)
        self.list_widget.file_opened.connect(self.on_file_opened)
        self.list_widget.open_context_menu.connect(self.populate_effects_menu)

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

        self.headerLabel = IconLabel(QIcon.fromTheme("effects"), _("Effects"))
        self.headerLabel.set_icon_size(app_theme.icon_size)
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

    def populate_effects_menu(self, menu: QMenu, datas: list[Mp3Entry]):
        open_dir = QAction(icon=QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen), text=_("Open Directory"), parent=self)
        open_dir.triggered.connect(self.pick_effects_directory)
        menu.addAction(open_dir)

        if AppSettings.value(SettingKeys.EFFECTS_DIRECTORY, None, type=str) is not None:
            self.refresh_dir_action = QAction(icon=QIcon.fromTheme(QIcon.ThemeIcon.ViewRefresh), text=_("Refresh"), parent=self)
            self.refresh_dir_action.triggered.connect(self.refresh_directory)
            menu.addAction(self.refresh_dir_action)

        file_name_action = QAction(_("Use mp3 title instead of file name"), self)
        file_name_action.setCheckable(True)
        file_name_action.setChecked(AppSettings.value(SettingKeys.EFFECTS_TITLE_INSTEAD_OF_FILE_NAME, True, type=bool))
        file_name_action.triggered.connect(
            lambda checked: self._toggle_column_setting(SettingKeys.EFFECTS_TITLE_INSTEAD_OF_FILE_NAME, checked))
        menu.addAction(file_name_action)

        menu.addSeparator()

    def _toggle_column_setting(self, key, checked):
        AppSettings.setValue(key, checked)
        self.list_widget.update()

    def changeEvent(self, event, /):
        if event.type() == QEvent.Type.PaletteChange:
            self.headerLabel.set_icon(QIcon.fromTheme("effects"))
            self.btn_play.setIcon(app_theme.create_play_pause_icon())
        elif event.type() == QEvent.Type.FontChange:
            self.headerLabel.set_icon_size(app_theme.icon_size)
            self.list_widget.setFont(app_theme.font())

    def toogle_play(self):
        if self.engine.pause_toggle():
            self.btn_play.setChecked(True)
        else:
            self.btn_play.setChecked(False)

    def on_volume_changed(self, volume: int = 70):
        self.engine.set_user_volume(volume)

    def on_file_opened(self, data: Mp3Entry):
        self.play_effect(data)

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

        with os.scandir(dir_path) as entries:
            effects: list[EffectEntry] = [EffectEntry.from_file(entry) for entry in entries if entry.is_dir() or entry.name.lower().endswith(".mp3")]

        effects = [effect for effect in effects if effect is not None]
        self.list_widget.setModel(EffectTableModel(effects))

    def pick_effects_directory(self):
        directory = QFileDialog.getExistingDirectory(self, _("Select Effects Directory"),
                                                     dir=AppSettings.value(SettingKeys.EFFECTS_DIRECTORY))
        if directory:
            AppSettings.setValue(SettingKeys.EFFECTS_DIRECTORY, directory)
            self.refresh_dir_action.setVisible(True)
            self.load_directory(directory)
