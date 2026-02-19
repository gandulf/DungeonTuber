import json
import logging
from dataclasses import dataclass, asdict
from enum import StrEnum
from functools import total_ordering

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QCompleter, QTextEdit, QVBoxLayout, QTabWidget, QWidget, \
    QDialogButtonBox, QFormLayout, QCheckBox, QHBoxLayout, QTableWidget, QHeaderView, QPushButton, QTableWidgetItem, \
    QGroupBox, QComboBox, QStyledItemDelegate, QMessageBox, QLabel

from config.utils import get_available_locales, restart_application

logger = logging.getLogger("main")

# --- Configuration ---
CATEGORY_MIN = 0
CATEGORY_MAX = 10

CAT_VALENCE = "Valence"
CAT_AROUSAL = "Arousal"

CAT_ENGAGEMENT = "Engagement"
CAT_DARKNESS = "Darkness"

CAT_AGGRESSIVE = "Aggressive"
CAT_HAPPY = "Happy"
CAT_PARTY = "Party"
CAT_RELAXED = "Relaxed"
CAT_SAD = "Sad"


@total_ordering
@dataclass
class MusicCategory:
    key: str
    name: str
    description: str
    levels: dict[int, str]
    group: str = None

    def __init__(self, name: str, description: str, levels: dict[int, str], group: str = '', key: str = None):
        if key is None:
            self.key = name
        else:
            self.key = key
        self.name = name
        self.description = description
        self.levels = levels
        self.group = group

    def __hash__(self):
        return hash(self.key)

    def __lt__(self, other):
        return self.key < other.key

    def __eq__(self, other):
        if not isinstance(other, MusicCategory):
            return False
        return self.key == other.key or self.name == other.name
    
    def json_dump(self):
        return json.dumps(asdict(self))

    @classmethod
    def json_dump_list(cls, categories: list):
        return json.dumps([asdict(mc) for mc in categories])

    @classmethod
    def json_load(cls, json_string: str):
        data = json.loads(json_string)
        return MusicCategory(**data)

    @classmethod
    def from_key(cls, key: str):
        name = _(key)
        description = _(key + " Description")
        levels = {1: _(key + " Low"),
                  5: _(key + " Medium"),
                  10: _(key + " High")
                  }

        group = "Mood" if key in [CAT_SAD, CAT_AGGRESSIVE, CAT_RELAXED, CAT_HAPPY, CAT_PARTY] else ""

        return MusicCategory(name, description, levels, key=key, group=group)

    def equals(self, name_or_key: str):
        return self.name == name_or_key or self.key == name_or_key or self.name == _(name_or_key)

    def get_detailed_description(self):
        tooltip = self.description + "\n"

        for level, descr in self.levels.items():
            tooltip += str(level) + ": " + descr + "\n"

        return tooltip.removesuffix("\n")


@dataclass
class Preset:
    name: str
    categories: dict[str, int] | None
    tags: list[str]
    genres: list[str]
    bpm: int

    def __init__(self, name: str, categories: dict[str, int], tags: list[str] = None, genres: list[str] = None, bpm: int =None):
        self.name = name
        self.categories = categories.copy() if categories is not None else {}
        self.tags = tags.copy() if tags is not None else []
        self.genres = genres.copy() if genres is not None else []
        self.bpm = bpm

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        # Equality must match the hash logic
        if not isinstance(other, Preset):
            return False
        return self.name == other.name

    @classmethod
    def json_dump_list(cls, presets: list):
        return json.dumps([asdict(mc) for mc in presets])

    def json_dump(self):
        return json.dumps(asdict(self))

    @classmethod
    def json_load(cls, json_string: str):
        data = json.loads(json_string)
        return Preset(**data)


_PRESETS: list[Preset] = []

_DEFAULT_CATEGORIES = [CAT_VALENCE, CAT_AROUSAL, CAT_ENGAGEMENT, CAT_DARKNESS, CAT_AGGRESSIVE, CAT_HAPPY, CAT_PARTY, CAT_RELAXED, CAT_SAD]
_MUSIC_CATEGORIES = None
_CATEGORIES = None

def remove_preset(preset: Preset):
    _PRESETS.remove(preset)
    AppSettings.setValue(SettingKeys.PRESETS, Preset.json_dump_list(_PRESETS))

def add_preset(preset: Preset):
    _PRESETS.append(preset)
    AppSettings.setValue(SettingKeys.PRESETS, Preset.json_dump_list(_PRESETS))

def get_presets():
    return _PRESETS

def set_presets(presets: list[Preset]):
    global _PRESETS
    if presets is None:
        _PRESETS = []
        AppSettings.remove(SettingKeys.PRESETS)
    else:
        presets = [preset for preset in presets if preset.name is not None]
        _PRESETS = presets
        AppSettings.setValue(SettingKeys.PRESETS, Preset.json_dump_list(_PRESETS))

def get_music_category(key: str) -> MusicCategory:
    cats = [cat for cat in get_music_categories() if cat.key == key]
    return cats[0] if cats and len(cats) > 0 else None


def get_category_keys() -> list[str]:
    global _CATEGORIES

    if _CATEGORIES is None:
        _CATEGORIES = [cat.key for cat in get_music_categories()]

    return _CATEGORIES


def get_music_categories() -> list[MusicCategory]:
    global _MUSIC_CATEGORIES
    if _MUSIC_CATEGORIES is None:
        _MUSIC_CATEGORIES = [MusicCategory.from_key(key) for key in _DEFAULT_CATEGORIES]
    return _MUSIC_CATEGORIES


def set_music_categories(categories: list[MusicCategory] | None):
    global _MUSIC_CATEGORIES
    if categories is None:
        AppSettings.remove(SettingKeys.CATEGORIES)
        _CATEGORIES = None
    else:
        AppSettings.setValue(SettingKeys.CATEGORIES, MusicCategory.json_dump_list(categories))
        _CATEGORIES = [cat.name for cat in categories]

    _MUSIC_CATEGORIES = categories


AppSettings: QSettings = QSettings("Gandulf", "DungeonTuber")


def reset_presets():
    global _PRESETS
    _PRESETS = None
    AppSettings.remove(SettingKeys.PRESETS)


class SettingKeys(StrEnum):
    WINDOW_SIZE="windowSize"
    REPEAT_MODE = "repeatMode"
    VOLUME = "volume"
    NORMALIZE_VOLUME = "normalizeVolume"
    EFFECTS_DIRECTORY = "effectsDirectory"
    EFFECTS_TREE = "effectsTree"
    LAST_DIRECTORY = "lastDirectory"
    FILTER_VISIBLE = "filterVisible"
    SKIP_ANALYZED_MUSIC = "skipAnalyzedMusic"
    EXPANDED_DIRS = "expandedDirs"
    ROOT_DIRECTORY = "rootDirectory"
    DIRECTORY_TREE = "directoryTree"
    RUSSEL_WIDGET = "russelWidget"
    CATEGORY_WIDGETS = "categoryWidgets"
    PRESET_WIDGETS = "presetWidgets"
    BPM_WIDGET = "bpmWidget"
    TAGS_WIDGET ="tagsWidget"
    GENRES_WIDGET = "genresWidget"
    FONT_SIZE = "fontSize"
    VISUALIZER = "visualizer"
    THEME = "theme"
    LOCALE = "locale"
    START_TOUR = "startTour"
    OPEN_TABLES = "openTables"

    DYNAMIC_TABLE_COLUMNS = "dynamicTableColumns"
    DYNAMIC_SCORE_COLUMN = "dynamicScoreColumn"
    COLUMN_INDEX_VISIBLE = "columnIndexVisible"
    COLUMN_FAVORITE_VISIBLE = "columnFavoriteVisible"
    COLUMN_SCORE_VISIBLE = "columnScoreVisible"
    COLUMN_TITLE_VISIBLE = "columnTitleVisible"
    COLUMN_ALBUM_VISIBLE = "columnAlbumVisible"
    COLUMN_GENRE_VISIBLE = "columnGenreVisible"
    COLUMN_ARTIST_VISIBLE = "columnArtistVisible"
    COLUMN_BPM_VISIBLE = "columnBPMVisible"
    COLUMN_SUMMARY_VISIBLE = "columnSummaryVisible"
    COLUMN_TAGS_VISIBLE = "columnTagsVisible"

    TITLE_INSTEAD_OF_FILE_NAME = "titleInsteadOfFilename"

    CATEGORIES = "categories"
    PRESETS = "presets"

    VOXALYZER_URL ="voxalyzerUrl"


class SettingsDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Settings"))
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West)
        layout.addWidget(self.tabs)

        # General Tab
        self.general_tab = QWidget()
        self.init_general_tab()
        self.tabs.addTab(self.general_tab, _("General"))

        # Categories Tab
        self.categories_tab = QWidget()
        self.init_categories_tab()
        self.tabs.addTab(self.categories_tab, _("Categories"))

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def init_general_tab(self):
        layout = QVBoxLayout(self.general_tab)

        analyzer_group = QGroupBox(_("System"))
        self.analyzer_layout = QFormLayout(analyzer_group)
        layout.addWidget(analyzer_group, 0)

        self.locale_combo = QComboBox(editable=False)
        self.locale_combo.setToolTip(_("Requires restart"))
        self.locale_combo.addItem(_("System Default"), "")
        self.locale_combo.setCurrentIndex(0)
        current_language = AppSettings.value(SettingKeys.LOCALE, type=str)

        for i, locale in enumerate(get_available_locales()):
            self.locale_combo.addItem(_(locale), locale)
            if current_language == locale:
                self.locale_combo.setCurrentIndex(i + 1)

        self.analyzer_layout.addRow(_("Language") + " *", self.locale_combo)

        self.voxalyzerUrl = QLineEdit()
        self.voxalyzerUrl.setPlaceholderText("http://localhost:8000/analyze")
        self.voxalyzerUrl.setText(AppSettings.value(SettingKeys.VOXALYZER_URL, type=str))
        self.analyzer_layout.addRow(_("Voxalyzer BaseUrl") , self.voxalyzerUrl)

        #
        player_group = QGroupBox(_("Player"))
        self.player_layout = QFormLayout(player_group)

        self.normalize_volume = QCheckBox(_("Normalize Volume")+"*")
        self.normalize_volume.setToolTip(_("Requires restart"))
        self.normalize_volume.setChecked(AppSettings.value(SettingKeys.NORMALIZE_VOLUME, True, type=bool))
        self.player_layout.addRow("", self.normalize_volume)
        normalize_volume_description = QLabel(_("All songs will be played at a normalized volume."))
        normalize_volume_description.setProperty("cssClass","small")
        normalize_volume_description.setContentsMargins(28, 0, 0, 0)
        self.player_layout.addRow("", normalize_volume_description)

        layout.addWidget(player_group, 0)
        #
        table_group = QGroupBox(_("Song Table"))
        table_layout = QFormLayout(table_group)

        layout.addWidget(table_group, 0)

        self.title_file_name_columns = QCheckBox(_("Use mp3 title instead of file name"))
        self.title_file_name_columns.setChecked(AppSettings.value(SettingKeys.TITLE_INSTEAD_OF_FILE_NAME, False, type=bool))
        table_layout.addRow("", self.title_file_name_columns)

        self.dynamic_score_column = QCheckBox(_("Dynamic Score Column"))
        self.dynamic_score_column.setChecked(AppSettings.value(SettingKeys.DYNAMIC_SCORE_COLUMN, False, type=bool))
        table_layout.addRow("", self.dynamic_score_column)
        dynamic_score_description = QLabel(_("Only show score column if any filters are active."))
        dynamic_score_description.setProperty("cssClass", "small")
        dynamic_score_description.setContentsMargins(28, 0, 0, 0)
        table_layout.addRow("", dynamic_score_description)

        self.dynamic_table_columns = QCheckBox(_("Dynamic Category Columns"))
        self.dynamic_table_columns.setChecked(AppSettings.value(SettingKeys.DYNAMIC_TABLE_COLUMNS, False, type=bool))
        table_layout.addRow("", self.dynamic_table_columns)
        dynamic_colomns_description = QLabel(_("Only category columns with an active filter value are display else they are hidden automatically."))
        dynamic_colomns_description.setProperty("cssClass", "small")
        dynamic_colomns_description.setContentsMargins(28, 0, 0, 0)
        table_layout.addRow("", dynamic_colomns_description)

        self.summary_column = QCheckBox(_("Summary Visible"))
        self.summary_column.setChecked(AppSettings.value(SettingKeys.COLUMN_SUMMARY_VISIBLE, True, type=bool))
        table_layout.addRow("", self.summary_column)

        layout.addStretch()

    def init_categories_tab(self):

        groups = set()
        for cat in get_music_categories():
            if cat.group is not None and cat.group != "":
                groups.add(cat.group)

        layout = QVBoxLayout(self.categories_tab)
        self.categories_table = QTableWidget()
        self.categories_table.setItemDelegate(SettingsTableDelegate(groups))
        self.categories_table.setColumnCount(5)
        self.categories_table.setHorizontalHeaderLabels([_("Key"),_("Name"), _("Group"), _("Description"), _("Levels (json)")])
        self.categories_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.fill_categories()

        layout.addWidget(self.categories_table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton(_("Add"))
        add_btn.clicked.connect(self.add_category)
        btn_layout.addWidget(add_btn)
        remove_btn = QPushButton(_("Remove"))
        remove_btn.clicked.connect(self.remove_category)
        btn_layout.addWidget(remove_btn)

        reset_cat_btn = QPushButton(_("Reset All"))
        reset_cat_btn.clicked.connect(self.reset_categories)
        btn_layout.addWidget(reset_cat_btn)
        layout.addLayout(btn_layout)

    def fill_categories(self):
        self.categories_table.setRowCount(len(get_music_categories()))
        for row, cat in enumerate(get_music_categories()):
            self.categories_table.setItem(row, 0, QTableWidgetItem(cat.key))
            self.categories_table.setItem(row, 1, QTableWidgetItem(cat.name))
            self.categories_table.setItem(row, 2, QTableWidgetItem(cat.group))
            self.categories_table.setItem(row, 3, QTableWidgetItem(cat.description))
            self.categories_table.setItem(row, 4, QTableWidgetItem(json.dumps(cat.levels, ensure_ascii=False, indent=2)))

        self.categories_table.resizeRowsToContents()

    def add_category(self):
        row = self.categories_table.rowCount()
        self.categories_table.insertRow(row)
        self.categories_table.setItem(row, 0, QTableWidgetItem(_("Key")))
        self.categories_table.setItem(row, 1, QTableWidgetItem(_("New Category")))
        self.categories_table.setItem(row, 2, QTableWidgetItem(""))
        self.categories_table.setItem(row, 3, QTableWidgetItem(_("Description")))
        self.categories_table.setItem(row, 4, QTableWidgetItem("""{
  "1":"",
  "5":"",
  "10":""
}"""))
        self.categories_table.resizeRowsToContents()

    def reset_categories(self):
        set_music_categories(None)

        self.fill_categories()

    def remove_category(self):
        row = self.categories_table.currentRow()
        if row >= 0:
            self.categories_table.removeRow(row)

    def requires_restart(self):
        result = False
        current_locale = AppSettings.value(SettingKeys.LOCALE, type=str)
        result = result or current_locale != self.locale_combo.currentData()
        result = result or self.normalize_volume.isChecked() != AppSettings.value(SettingKeys.NORMALIZE_VOLUME, True, type=bool)

        return result

    def accept(self):
        requires_restart = self.requires_restart()

        AppSettings.setValue(SettingKeys.TITLE_INSTEAD_OF_FILE_NAME, self.title_file_name_columns.isChecked())
        AppSettings.setValue(SettingKeys.DYNAMIC_TABLE_COLUMNS, self.dynamic_table_columns.isChecked())
        AppSettings.setValue(SettingKeys.DYNAMIC_SCORE_COLUMN, self.dynamic_score_column.isChecked())
        AppSettings.setValue(SettingKeys.COLUMN_SUMMARY_VISIBLE, self.summary_column.isChecked())
        AppSettings.setValue(SettingKeys.LOCALE, self.locale_combo.currentData())
        if self.voxalyzerUrl.text() == '' or self.voxalyzerUrl.text() is None:
            AppSettings.remove(SettingKeys.VOXALYZER_URL)
        else:
            AppSettings.setValue(SettingKeys.VOXALYZER_URL, self.voxalyzerUrl.text())

        AppSettings.setValue(SettingKeys.NORMALIZE_VOLUME, self.normalize_volume.isChecked())

        _categories = []
        for row in range(self.categories_table.rowCount()):
            key_item = self.categories_table.item(row, 0)
            cat_item = self.categories_table.item(row, 1)
            group_item = self.categories_table.item(row, 2)
            desc_item = self.categories_table.item(row, 3)
            level_item = self.categories_table.item(row, 4)
            if cat_item and desc_item and group_item:
                cat_key = key_item.text()
                cat_name = cat_item.text()
                cat_group = group_item.text()
                cat_desc = desc_item.text()
                cat_levels = json.loads(level_item.text())
                if cat_name:
                    _categories.append(MusicCategory(cat_name, cat_desc, cat_levels, group=cat_group, key = cat_key))
        set_music_categories(_categories)

        if requires_restart:

            reply = QMessageBox.question(self, _("Restart Required"),
                                         _("Changing the language requires a restart. Do you want to restart now?"),
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

            if reply == QMessageBox.StandardButton.Yes:
                restart_application()

        super().accept()

class SettingsTableDelegate(QStyledItemDelegate):

    def __init__(self, groups: set[str]):
        super().__init__()
        self.groups = groups

    def createEditor(self, parent, option, index):
        if index.column() == 1:
            line_edit = QLineEdit(parent)
            completer = QCompleter(sorted(list(self.groups)))
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
            line_edit.setCompleter(completer)
            return line_edit
        if index.column() == 2 or index.column() == 3:
            text_edit = QTextEdit(parent)
            return text_edit

        return super(SettingsDialog.SettingsTableDelegate, self).createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if index.column() == 1:
            editor.setText(index.data())
            return None
        if index.column() == 2 or index.column() == 3:
            editor.setPlainText(index.data())
            return None
        return super(SettingsDialog.SettingsTableDelegate, self).setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if index.column() == 1:
            model.setData(index, editor.text())
            self.groups.add(editor.text())
            return None
        if index.column() == 2 or index.column() == 3:
            model.setData(index, editor.toPlainText())
            return None
        return super(SettingsDialog.SettingsTableDelegate, self).setModelData(editor, model, index)

class FilterConfig:
    categories: dict[str, int] = {}
    tags: list[str] = []
    bpm: int | None = None
    genres: list[str] = []

    def __init__(self, categories={}, tags=[], bpm=None, genres=[]):
        self.categories = categories
        self.tags = tags
        self.bpm = bpm
        self.genres = genres

    def get_category(self, category_key: str, default: int = None) -> int:
        value = self.categories.get(category_key, default)
        return value if value is not None and value >=0 else None

    def toggle_tag(self, tag:str, state:int):
        if state == 0 and tag in self.tags:
            self.tags.remove(tag)
        elif tag not in self.tags:
            self.tags.append(tag)

    def toggle_genre(self, genre:str, state:int):
        if state == 0 and genre in self.genres:
            self.genres.remove(genre)
        elif genre not in self.genres:
            self.genres.append(genre)

    def clear(self):
        self.genres.clear()
        self.tags.clear()
        self.bpm = None
        self.categories.clear()

    def empty(self) -> bool:
        empty = True
        for value in self.categories.values():
            if value is not None:
                empty = False
                break

        empty = empty and (self.tags is None or len(self.tags) == 0) and self.bpm is None and (self.genres is None or len(self.genres) == 0)

        return empty