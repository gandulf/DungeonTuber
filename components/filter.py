import functools

from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QIcon, QAction, QPalette, QFont
from PySide6.QtWidgets import QDialogButtonBox, QFormLayout, QLineEdit, QDialog, QToolButton, QPushButton, QHBoxLayout, \
    QWidget, QVBoxLayout, QMenu, QLabel, QTabWidget

from components.charts import RussellEmotionWidget
from components.layouts import FlowLayout
from components.sliders import ToggleSlider, CategoryWidget, BPMSlider
from components.tables import SongTable

from config.settings import CAT_VALENCE, get_music_category, CAT_AROUSAL, Preset, add_preset, remove_preset, \
    reset_presets, SettingKeys, get_presets, AppSettings, MusicCategory, get_music_tags, CATEGORY_MIN, CATEGORY_MAX, \
    FilterConfig
from config.theme import app_theme
from config.utils import children_layout, clear_layout

from logic.mp3 import Mp3Entry

class FilterWidget(QWidget):
    values_changed = Signal(FilterConfig)

    sliders: dict[MusicCategory, CategoryWidget] = {}

    filter_config = FilterConfig()

    def __init__(self, parent=None):
        super().__init__(parent)

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

    def attach_song_table(self, song_table : SongTable | None):
        self.values_changed.disconnect()

        if song_table is not None:
            self.values_changed.connect(song_table.set_filter_config)

            self.update_sliders(song_table.get_available_categories())
            self.update_tags(song_table.get_available_tags())
            self.update_genres(song_table.get_available_genres())
            self.update_russel_heatmap(song_table.mp3_datas())
        else:
            self.update_sliders([])
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
            cat_slider.valueChanged.connect(self.on_slider_value_changed)

            if AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool) and cat.equals(CAT_VALENCE) and not cat.equals(CAT_AROUSAL):
                cat_slider.setVisible(False)

            self.sliders[cat] = cat_slider
            sliders_row.addWidget(cat_slider)

        return sliders_widget

    def on_slider_value_changed(self):
        category_widget: CategoryWidget = self.sender()
        self.filter_config.categories[category_widget.category.key] = category_widget.value()

        self.values_changed.emit(self.config())

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()

        AppSettings.setValue(SettingKeys.FILTER_VISIBLE, self.isVisible())

    def toggle_russel_widget(self):
        AppSettings.setValue(SettingKeys.RUSSEL_WIDGET, not AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool))

        if not AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool):
            self.russel_widget.reset()

        self.refresh_slider_tabs_visibility()

    def toggle_category_widgets(self):
        AppSettings.setValue(SettingKeys.CATEGORY_WIDGETS, not AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool))

        if not AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool):
            for category, slider in self.sliders.items():
                slider.reset()

        self.refresh_slider_tabs_visibility()

    def toggle_presets(self):
        AppSettings.setValue(SettingKeys.PRESET_WIDGETS, not AppSettings.value(SettingKeys.PRESET_WIDGETS, True, type=bool))
        self.update_presets()

    def toggle_bpm_widget(self):
        AppSettings.setValue(SettingKeys.BPM_WIDGET, not AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool))

        if not AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool):
            self.bpm_widget.reset()

        self.refresh_slider_tabs_visibility()

    def toggle_tags_widget(self):
        AppSettings.setValue(SettingKeys.TAGS_WIDGET, not AppSettings.value(SettingKeys.TAGS_WIDGET, True, type=bool))

        if not AppSettings.value(SettingKeys.TAGS_WIDGET, True, type=bool):
            self.filter_config.tags.clear()

            for toggle in children_layout(self.tags_layout):
                toggle.setChecked(False,True)

        self.refresh_slider_tabs_visibility()

    def toggle_genres_widget(self):
        AppSettings.setValue(SettingKeys.GENRES_WIDGET, not AppSettings.value(SettingKeys.GENRES_WIDGET, True, type=bool))

        if not AppSettings.value(SettingKeys.GENRES_WIDGET, True, type=bool):
            self.filter_config.genres.clear()

            for toggle in children_layout(self.genres_layout):
                toggle.setChecked(False,True)

        self.refresh_slider_tabs_visibility()

    def toggle_tag(self, state: int):
        toggle = self.sender()
        self.filter_config.toggle_tag(toggle.property("tag"), state)
        self.values_changed.emit(self.config())

    def toggle_genre(self, state: int):
        toggle = self.sender()
        self.filter_config.toggle_genre(toggle.property("genre"), state)
        self.values_changed.emit(self.config())

    def update_tags(self , available_tags: list[str]):
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

            if tag in get_music_tags():
                toggle.setToolTip(get_music_tags()[tag])
            toggle.stateChanged.connect(self.toggle_tag)
            toggle.setChecked(tag in self.filter_config.tags)
            self.tags_layout.addWidget(toggle)

    def update_genres(self, available_genres : list[str]):
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
            self.russel_widget.set_value(5, 5)

        self.filter_config.tags.clear()
        self.filter_config.genres.clear()

        for toggle in children_layout(self.tags_layout):
            if isinstance(toggle, ToggleSlider):
                toggle.setChecked(False, True)

        for toggle in children_layout(self.genres_layout):
            if isinstance(toggle, ToggleSlider):
                toggle.setChecked(False,True)

        self.bpm_widget.reset(False)

        self.values_changed.emit(self.config())

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

        for toggle in children_layout(self.tags_layout):
            tag = toggle.property("tag")
            toggle.setChecked(tag in self.filter_config.tags, block_signals = True)

        if preset.genres:
            self.filter_config.genres = preset.genres.copy()
        else:
            self.filter_config.genres.clear()

        for toggle in children_layout(self.genres_layout):
            genre = toggle.property("genre")
            toggle.setChecked(genre in self.filter_config.genres, block_signals = True)

        if CAT_VALENCE in preset.categories and CAT_AROUSAL in preset.categories:
            self.russel_widget.set_value(preset.categories[CAT_VALENCE], preset.categories[CAT_AROUSAL], False)
        if _(CAT_VALENCE) in preset.categories and _(CAT_AROUSAL) in preset.categories:
            self.russel_widget.set_value(preset.categories[_(CAT_VALENCE)], preset.categories[_(CAT_AROUSAL)], False)

        if preset.bpm is not None:
            self.bpm_widget.set_value(preset.bpm)

        self.values_changed.emit(self.config())

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

    def on_russel_changed(self, valence: float, arousal: float):
        cat_valence = get_music_category(CAT_VALENCE)
        cat_arousal = get_music_category(CAT_AROUSAL)
        self.set_category_value(cat_valence, valence, False)
        self.set_category_value(cat_arousal, arousal, False)

    def set_category_value(self, cat: str, value: float | int, notify: bool = True):
        if cat in self.sliders:
            self.sliders[cat].set_value(round(value), False)

        if notify:
            self.values_changed.emit(self.config())

    def config(self):
        self.filter_config.categories = self.categories()
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
        self.filter_config.bpm = value
        self.values_changed.emit(self.config())
