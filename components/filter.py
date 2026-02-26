import functools

from PySide6.QtCore import Qt, QPoint, Signal, QMetaMethod, QSize, QEvent, QPointF, QRectF, QRect
from PySide6.QtGui import QIcon, QAction, QPalette, QFont, QColor, QPaintEvent, QPainter, QPen, QBrush
from PySide6.QtWidgets import QDialogButtonBox, QFormLayout, QLineEdit, QDialog, QToolButton, QPushButton, QHBoxLayout, \
    QWidget, QVBoxLayout, QMenu, QLabel, QTabWidget

from components.widgets import FlowLayout, ToggleSlider, CategoryWidget, BPMSlider
from config.settings import CAT_VALENCE, get_music_category, CAT_AROUSAL, Preset, add_preset, remove_preset, \
    reset_presets, SettingKeys, get_presets, AppSettings, MusicCategory, CATEGORY_MIN, CATEGORY_MAX, \
    FilterConfig, get_music_categories
from config.theme import app_theme
from config.utils import children_layout, clear_layout
from logic.mp3 import Mp3Entry
from songs import SongTable


def _map_pt(plot_rect, val, aro):
    x_pos = plot_rect.left() + (val / 10.0) * plot_rect.width()
    y_pos = plot_rect.bottom() - (aro / 10.0) * plot_rect.height()
    return QPointF(x_pos, y_pos)

class RussellEmotionWidget(QWidget):
    """
    A widget that draws a Russell's Circumplex Model of Emotion diagram
    using PySide6 QPainter, allowing users to pick a valence/arousal point.
    """

    value_changed = Signal(float, float, bool)  # valence, arousal, in_progress

    def __init__(self, parent: QWidget | None=None):
        super().__init__(parent)
        self.valence = -1
        self.arousal = -1
        self.mouse_down = False
        self.reference_points = []

        self.setMinimumSize(20 * app_theme.font_size, 20 * app_theme.font_size)
        self.setMouseTracking(True)

        self.bg_color = QColor("#FFFFFF")
        self.fg_color = QColor("#000000")
        self.grid_color = QColor("#CCCCCC")
        self.point_color = QColor("#FF0000")
        self.ref_point_color = QColor("#0000FF")
        self.ref_point_border_color = QColor("#2b2b2b")

        self.update_theme()

    def sizeHint(self, /) -> QSize:
        return QSize(22 * app_theme.font_size, 22 * app_theme.font_size)

    def update_theme(self):
        is_dark = AppSettings.value(SettingKeys.THEME, "LIGHT", type=str) == "DARK"
        if is_dark:
            self.bg_color = QColor("#2b2b2b")
            self.fg_color = QColor("#dddddd")
            self.grid_color = QColor("#555555")
            self.point_color = QColor("#00FF00")  # Neon Green
            self.ref_point_color = QColor("#00FF00")
            self.ref_point_border_color = QColor("#FFFFFF")
        else:
            self.bg_color = QColor("#FFFFFF")
            self.fg_color = QColor("#555555")
            self.grid_color = QColor("#CCCCCC")
            self.point_color = QColor("#0000FF")  # Blue
            self.ref_point_color = QColor("#0000FF")
            self.ref_point_border_color = QColor("#2b2b2b")
        self.update()

    def changeEvent(self, event: QEvent):
        if event.type() == QEvent.Type.PaletteChange:
            self.update_theme()
        elif event.type() == QEvent.Type.FontChange:
            self.setMinimumSize(20 * app_theme.font_size, 20 * app_theme.font_size)

        super().changeEvent(event)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = painter.font()
        font.setPointSizeF(app_theme.font_size)
        painter.setFont(font)

        MARGIN_LEFT = self.contentsMargins().left() + painter.fontMetrics().height()
        MARGIN_BOTTOM = self.contentsMargins().bottom() + painter.fontMetrics().height()
        MARGIN_TOP = self.contentsMargins().top()
        MARGIN_RIGHT = self.contentsMargins().right()

        # Draw background
        painter.fillRect(event.rect(), self.bg_color)

        self.plot_rect = event.rect().adjusted(MARGIN_LEFT, MARGIN_TOP, -MARGIN_RIGHT,-MARGIN_BOTTOM)

        # Draw Grid (Center lines)
        painter.setPen(QPen(self.grid_color, 1))
        center_x = self.plot_rect.center().x()
        center_y = self.plot_rect.center().y()

        painter.drawLine(QPointF(self.plot_rect.left(), center_y), QPointF(self.plot_rect.right(), center_y))
        painter.drawLine(QPointF(center_x, self.plot_rect.top()), QPointF(center_x, self.plot_rect.bottom()))

        # Draw dashed grid border
        painter.setPen(QPen(self.grid_color, 1, Qt.PenStyle.DashLine))
        painter.drawRect(self.plot_rect)

        # Draw Labels inside
        painter.setPen(self.fg_color)

        if app_theme.font_size_small > 11:
            labels = [
                (7.5, 7.5, "Happy"),
                (7.5, 2.5, "Peaceful"),
                (2.5, 2.5, "Bored"),
                (2.5, 7.5, "Angry")
            ]
        else:
            labels = [
                (6.5, 8.5, "Excited"), (7.5, 7.5, "Happy"), (8.5, 6.5, "Pleased"),
                (8.5, 3.5, "Relaxed"), (7.5, 2.5, "Peaceful"), (6.5, 1.5, "Calm"),
                (3.5, 1.5, "Sleepy"), (2.5, 2.5, "Bored"), (1.5, 3.5, "Sad"),
                (1.5, 6.5, "Nervous"), (2.5, 7.5, "Angry"), (3.5, 8.5, "Annoying")
            ]

        for val, aro, text in labels:
            self.draw_text_centered(painter, _map_pt(self.plot_rect, val, aro), text)

        # Nuanced labels
        self.draw_text_centered(painter, _map_pt(self.plot_rect, 5, 9.8), "Hopeful",
                                align=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.draw_text_centered(painter, _map_pt(self.plot_rect, 0.1, 5), "Dark",
                                align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.draw_text_centered(painter, _map_pt(self.plot_rect, 9.9, 5), "Dreamy",
                                align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.draw_text_centered(painter, _map_pt(self.plot_rect, 5, 0.1), "Tired",
                                align=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)

        # Axis Labels
        x_label = _("unpleasant") + "→" + _("pleasant")
        y_label = _("calm") + "→" + _("excited")

        painter.drawText(QRectF(self.plot_rect.left(), self.plot_rect.bottom(), self.plot_rect.width(), MARGIN_BOTTOM),
                         Qt.AlignmentFlag.AlignCenter, x_label)

        bounding_rect = painter.fontMetrics().boundingRect(y_label).adjusted(-2, -2, 2, 2)
        h = bounding_rect.height()

        painter.save()
        painter.translate(MARGIN_LEFT - h/2, self.plot_rect.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-self.plot_rect.height() / 2, - h/2, self.plot_rect.height(), h),
                         Qt.AlignmentFlag.AlignCenter, y_label)
        painter.restore()

        # Draw Reference Points
        c = QColor(self.ref_point_color)
        c.setAlpha(50)
        painter.setBrush(QBrush(c))
        painter.setPen(QPen(self.ref_point_border_color, 0.5))

        for val, aro in self.reference_points:
            if val is not None and aro is not None:
                pt = _map_pt(self.plot_rect, val, aro)
                painter.drawEllipse(pt, 3, 3)

        # Draw Current Point
        if self.valence is not None and self.arousal is not None and self.valence>=0 and self.arousal>=0:
            pt = _map_pt(self.plot_rect, self.valence, self.arousal)
            painter.setBrush(QBrush(self.point_color))
            painter.setPen(QPen(self.ref_point_border_color, 1.5))
            painter.drawEllipse(pt, 6, 6)


        # draw clear X
        self.clear_rect : QRect = self.rect().marginsAdded(self.contentsMargins())
        self.clear_rect.setWidth(16)
        self.clear_rect.setY(self.clear_rect.bottom()-16)
        self.clear_rect.setHeight(16)
        QIcon.fromTheme(QIcon.ThemeIcon.EditClear).paint(painter, self.clear_rect, alignment=Qt.AlignmentFlag.AlignCenter)

    def draw_text_centered(self, painter, pt, text, align=Qt.AlignmentFlag.AlignCenter):
        bounding_rect = painter.fontMetrics().boundingRect(text).adjusted(-2, -2, 2, 2)
        w = bounding_rect.width()
        h = bounding_rect.height()

        if align & Qt.AlignmentFlag.AlignLeft:
            rect = QRectF(pt.x(), pt.y() - h / 2, w, h)
        elif align & Qt.AlignmentFlag.AlignRight:
            rect = QRectF(pt.x() - w, pt.y() - h / 2, w, h)
        elif align & Qt.AlignmentFlag.AlignTop:
            rect = QRectF(pt.x() - w / 2, pt.y(), w, h)
        elif align & Qt.AlignmentFlag.AlignBottom:
            rect = QRectF(pt.x() - w / 2, pt.y() - h, w, h)
        else:
            rect = QRectF(pt.x() - w / 2, pt.y() - h / 2, w, h)

        painter.drawText(rect, align, text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.clear_rect.contains(event.position().toPoint()):
                self.reset(True)
            else:
                self.mouse_down = True
                self.update_from_mouse(event.position())

    def mouseMoveEvent(self, event):
        if self.mouse_down:
            self.update_from_mouse(event.position())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_down = False
            self.value_changed.emit(self.valence, self.arousal, False)

    def update_from_mouse(self, pos):
        x = pos.x() - self.plot_rect.left()
        y = pos.y() - self.plot_rect.top()

        val = (x / self.plot_rect.width()) * 10.0
        aro = 10.0 - (y / self.plot_rect.height()) * 10.0

        self.valence = round(max(0.0, min(10.0, val)), 2)
        self.arousal = round(max(0.0, min(10.0, aro)), 2)

        self.value_changed.emit(self.valence, self.arousal, True)
        self.update()

    def get_value(self):
        return self.valence, self.arousal

    def set_value(self, valence, arousal, notify=True):
        self.valence = valence
        self.arousal = arousal
        if notify:
            self.value_changed.emit(self.valence, self.arousal, False)
        self.update()

    def reset(self, notify=True):
        self.set_value(-1, -1, notify)

    def set_reference_points(self, points):
        if isinstance(points,list):
            self.reference_points = points
        else:
            self.reference_points = list(points)
        self.update()

    def add_reference_points(self, points):
        self.reference_points.extend(points)
        self.update()

    def clear_scatter(self):
        self.reference_points = []
        self.update()

    def update_plot_theme(self, is_dark=True):
        # Kept for compatibility, though is_dark is ignored in favor of AppSettings
        self.update_theme()


class FilterWidget(QWidget):
    values_changed = Signal(FilterConfig)

    sliders: dict[MusicCategory, CategoryWidget] = {}

    filter_config = FilterConfig()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.russel_widget = RussellEmotionWidget()
        self.russel_widget.value_changed.connect(self.on_russel_changed)

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

    def attach_song_table(self, song_table: SongTable | None):
        meta_signal = QMetaMethod.fromSignal(self.values_changed)
        if self.isSignalConnected(meta_signal):
            self.values_changed.disconnect()

        if song_table is not None:
            song_table.set_filter_config(self.filter_config)
            self.values_changed.connect(song_table.set_filter_config)

            self.update_sliders(song_table.get_available_categories())
            self.update_tags(song_table.get_available_tags())
            self.update_genres(song_table.get_available_genres())
            self.update_russel_heatmap(song_table.get_raw_data())
        else:
            self.update_sliders(get_music_categories())
            self.update_tags([])
            self.update_genres([])
            self.update_russel_heatmap([])

        self.refresh_slider_tabs_visibility()

    def show_context_menu(self, point: QPoint):
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
        sliders_row = QHBoxLayout()
        sliders_row.setObjectName("slider_row")
        sliders_row.setContentsMargins(0, 0, 0, 0)
        sliders_row.setSpacing(0)

        sliders_layout.addLayout(sliders_row, 1)

        for i, cat in enumerate(categories):

            cat_slider = CategoryWidget(category=cat, min_value=CATEGORY_MIN, max_value=CATEGORY_MAX)
            cat_slider.set_value(self.filter_config.get_category(cat.key, -1))
            cat_slider.value_changed.connect(self.on_slider_value_changed)

            if AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool) and cat.equals(CAT_VALENCE) and not cat.equals(CAT_AROUSAL):
                cat_slider.setVisible(False)

            self.sliders[cat] = cat_slider
            sliders_row.addWidget(cat_slider)

        return sliders_widget

    def on_slider_value_changed(self, category: MusicCategory, value: int):
        if value is not None and value >= 0:
            self.filter_config.categories[category.key] = value
        else:
            self.filter_config.categories.pop(category.key, 0)
        self.values_changed.emit(self.filter_config)

    def toggle_russel_widget(self, visible: bool=None):
        if visible is None:
            visible = not AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool)

        AppSettings.setValue(SettingKeys.RUSSEL_WIDGET, visible)

        if not visible:
            self.russel_widget.reset()

        self.refresh_slider_tabs_visibility()

    def toggle_category_widgets(self, visible: bool=None):
        if visible is None:
            visible = not AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool)

        AppSettings.setValue(SettingKeys.CATEGORY_WIDGETS, visible)

        if not visible:
            for category, slider in self.sliders.items():
                slider.reset(False)

            self.values_changed.emit(self.filter_config)

        self.refresh_slider_tabs_visibility()

    def toggle_presets(self, visible: bool = None):
        if visible is None:
            visible = not AppSettings.value(SettingKeys.PRESET_WIDGETS, True, type=bool)

        AppSettings.setValue(SettingKeys.PRESET_WIDGETS, visible)
        self.update_presets()

    def toggle_bpm_widget(self, visible: bool = None):
        if visible is None:
            visible = not AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool)

        AppSettings.setValue(SettingKeys.BPM_WIDGET, visible)

        if not visible:
            self.bpm_widget.reset()

        self.refresh_slider_tabs_visibility()

    def toggle_tags_widget(self, visible: bool = None):
        if visible is None:
            visible = not AppSettings.value(SettingKeys.TAGS_WIDGET, True, type=bool)

        AppSettings.setValue(SettingKeys.TAGS_WIDGET, visible)

        if not visible:
            self.filter_config.tags.clear()
            for toggle in children_layout(self.tags_layout):
                toggle.setChecked(False, False)
            self.values_changed.emit(self.filter_config)
        self.refresh_slider_tabs_visibility()

    def toggle_genres_widget(self, visible: bool = None):
        if visible is None:
            visible = not AppSettings.value(SettingKeys.GENRES_WIDGET, True, type=bool)

        AppSettings.setValue(SettingKeys.GENRES_WIDGET, visible)

        if not visible:
            self.filter_config.genres.clear()
            for toggle in children_layout(self.genres_layout):
                toggle.setChecked(False, False)
            self.values_changed.emit(self.filter_config)

        self.refresh_slider_tabs_visibility()

    def toggle_tag(self, state: int):
        toggle = self.sender()
        self.filter_config.toggle_tag(toggle.property("tag"), state)
        self.values_changed.emit(self.filter_config)

    def toggle_genre(self, state: int):
        toggle = self.sender()
        self.filter_config.toggle_genre(toggle.property("genre"), state)
        self.values_changed.emit(self.filter_config)

    def update_tags(self, available_tags: list[str]):
        clear_layout(self.tags_layout)

        if AppSettings.value(SettingKeys.TAGS_WIDGET, True, type=bool):
            self.tags_genres_widget.setVisible(True)
            self.tags_widget.setVisible(True)
        else:
            self.tags_widget.setVisible(False)
            if not AppSettings.value(SettingKeys.GENRES_WIDGET, True, type=bool):
                self.tags_genres_widget.setVisible(False)

        for tag in available_tags:
            toggle = ToggleSlider(checked_text=tag, unchecked_text=tag)
            toggle.setProperty("tag", tag)
            toggle.stateChanged.connect(self.toggle_tag)
            toggle.setChecked(tag in self.filter_config.tags)
            self.tags_layout.addWidget(toggle)

    def update_genres(self, available_genres: list[str]):
        clear_layout(self.genres_layout)
        if AppSettings.value(SettingKeys.GENRES_WIDGET, True, type=bool):
            self.tags_genres_widget.setVisible(True)
            self.genres_widget.setVisible(True)
        else:
            self.genres_widget.setVisible(False)
            if not AppSettings.value(SettingKeys.TAGS_WIDGET, True, type=bool):
                self.tags_genres_widget.setVisible(False)

        genre_palette = QPalette(self.palette())
        genre_palette.setBrush(QPalette.ColorRole.Highlight, app_theme.get_green_brush(255))

        for genre in available_genres:
            toggle = ToggleSlider(checked_text=genre, unchecked_text=genre, draggable=False)
            toggle.setPalette(genre_palette)
            toggle.setProperty("genre", genre)
            toggle.stateChanged.connect(self.toggle_genre)
            toggle.setChecked(genre in self.filter_config.genres)
            self.genres_layout.addWidget(toggle)

    def refresh_slider_tabs_visibility(self):
        if (not AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool)
                and not AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool)
                and not AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool)):
            self.slider_tabs.setVisible(False)
        else:
            self.slider_tabs.setVisible(True)

        if AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool):
            self.slider_tabs.tabBar().setVisible(True)

            for slider in self.sliders.values():
                slider.setVisible(True)
        else:
            self.slider_tabs.tabBar().setVisible(False)
            self.slider_tabs.setCurrentIndex(0)

            for slider in self.sliders.values():
                slider.setVisible(False)

        self.russel_widget.setVisible(AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool))
        if AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool):
            self.sliders[get_music_category(CAT_AROUSAL)].setVisible(False)
            self.sliders[get_music_category(CAT_VALENCE)].setVisible(False)
        else:
            self.sliders[get_music_category(CAT_AROUSAL)].setVisible(AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool))
            self.sliders[get_music_category(CAT_VALENCE)].setVisible(AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool))

        if AppSettings.value(SettingKeys.TAGS_WIDGET, True, type=bool):
            self.tags_genres_widget.setVisible(True)
            self.tags_widget.setVisible(True)
        else:
            self.tags_widget.setVisible(False)
            if not AppSettings.value(SettingKeys.GENRES_WIDGET, True, type=bool):
                self.tags_genres_widget.setVisible(False)

        self.bpm_widget.setVisible(AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool))

    def update_sliders(self, available_categories: list[MusicCategory]):
        self.russel_widget.setParent(None)
        self.bpm_widget.setParent(None)

        self.slider_tabs.clear()
        self.sliders = {}

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

        self.refresh_slider_tabs_visibility()

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
            self.russel_widget.reset(False)

        for toggle in children_layout(self.tags_layout):
            if isinstance(toggle, ToggleSlider):
                toggle.setChecked(False, False)

        for toggle in children_layout(self.genres_layout):
            if isinstance(toggle, ToggleSlider):
                toggle.setChecked(False, False)

        self.bpm_widget.reset(False)

        self.filter_config.clear()
        self.values_changed.emit(self.filter_config)

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
            slider.reset(False)

        self.filter_config.categories.clear()
        for cat, scale in preset.categories.items():
            category = get_music_category(cat)
            self.filter_config.categories[cat] = scale
            if category in self.sliders:
                self.sliders[category].set_value(scale, False)

        if preset.tags:
            self.filter_config.tags = preset.tags.copy()
        else:
            self.filter_config.tags.clear()

        for toggle in children_layout(self.tags_layout):
            tag = toggle.property("tag")
            toggle.setChecked(tag in self.filter_config.tags, False)

        if preset.genres:
            self.filter_config.genres = preset.genres.copy()
        else:
            self.filter_config.genres.clear()

        for toggle in children_layout(self.genres_layout):
            genre = toggle.property("genre")
            toggle.setChecked(genre in self.filter_config.genres, False)

        if CAT_VALENCE in preset.categories and CAT_AROUSAL in preset.categories:
            self.russel_widget.set_value(preset.categories[CAT_VALENCE], preset.categories[CAT_AROUSAL], False)
        else:
            self.russel_widget.reset(False)

        if preset.bpm is not None:
            self.bpm_widget.set_value(preset.bpm)
            self.filter_config.bpm = preset.bpm
        else:
            self.bpm_widget.reset(False)
            self.filter_config.bpm = None

        self.values_changed.emit(self.filter_config)

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
            preset = Preset(name_edit.text(), self.filter_config.categories, self.filter_config.tags, self.filter_config.genres, self.filter_config.bpm)
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

    def on_russel_changed(self, valence: float, arousal: float, in_progress: bool):
        self.set_category_value(CAT_VALENCE, valence, False)
        self.set_category_value(CAT_AROUSAL, arousal, False)

        if not in_progress:
            self.values_changed.emit(self.filter_config)

    def set_category_value(self, cat: MusicCategory | str, value: float | int | None, notify: bool = True):
        if isinstance(cat, str):
            cat = get_music_category(cat)

        if cat in self.sliders:
            self.sliders[cat].set_value(round(value), False)

        if value is not None and value >= 0:
            self.filter_config.categories[cat.key] = value
        else:
            self.filter_config.categories.pop(cat.key, 0)

        if notify:
            self.values_changed.emit(self.filter_config)

    def on_bpm_changed(self, value: int):
        self.filter_config.bpm = value
        self.values_changed.emit(self.filter_config)
