import json
import logging
from collections import namedtuple
from enum import StrEnum

import jsonpickle
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QCompleter, QTextEdit, QVBoxLayout, QTabWidget, QWidget, \
    QDialogButtonBox, QFormLayout, QCheckBox, QHBoxLayout, QTableWidget, QHeaderView, QPushButton, QTableWidgetItem, \
    QGroupBox, QComboBox, QStyledItemDelegate
from google import genai
from google.genai.types import ListModelsConfig


logger = logging.getLogger("main")

# --- Configuration ---
CATEGORY_MIN = 1
CATEGORY_MAX = 10

CAT_TEMPO = "Tempo"
CAT_DARKNESS = "Darkness"
CAT_EMOTIONAL = "Emotional"
CAT_MYSTICISM = "Mysticism"
CAT_TENSION = "Tension"
CAT_HEROISM = "Heroism"

class MusicCategory():
    name: str
    description: str
    levels: dict[int, str]
    group: str = None

    def __init__(self, name: str, description: str, levels: dict[int, str], group: str = None):
        self.name = name
        self.description = description
        self.levels = levels
        self.group = group

    @classmethod
    def from_key(cls, key: str):
        name = _(key)
        description = _(key + " Description")
        levels = {1: _(key + " Low"),
                       5: _(key + " Medium"),
                       10: _(key + " High")
                       }

        return MusicCategory(name, description, levels)



    def get_detailed_description(self):
        tooltip = self.description + "\n"

        for level, descr in self.levels.items():
            tooltip += str(level) + ": " + descr + "\n"

        return tooltip.removesuffix("\n")


Preset = namedtuple("Preset", ["name", "categories"], defaults=[None, None])
_PRESETS = None

_TAGS =["Travel","Fight"]
_MUSIC_TAGS = None

_DEFAULT_CATEGORIES =[CAT_TEMPO, CAT_DARKNESS, CAT_EMOTIONAL, CAT_MYSTICISM, CAT_TENSION, CAT_HEROISM]
CATEGORIES = _DEFAULT_CATEGORIES.copy()
_MUSIC_CATEGORIES = None


def get_presets() -> list[Preset]:
    global _PRESETS
    if _PRESETS is None:
        _PRESETS =[
            Preset(_("Grim"),
                   {_(CAT_DARKNESS): 8, _(CAT_HEROISM): 4, _(CAT_EMOTIONAL): 3, _(CAT_MYSTICISM): 4, _(CAT_TENSION): 8}),
        ]

    return _PRESETS

def remove_preset(preset: Preset):
    global _PRESETS

    _PRESETS.remove(preset)
    AppSettings.setValue(SettingKeys.PRESETS, jsonpickle.encode(_PRESETS))

def add_preset(preset: Preset):
    global _PRESETS

    _PRESETS.append(preset)
    AppSettings.setValue(SettingKeys.PRESETS, jsonpickle.encode(_PRESETS))

def set_presets(presets: list[Preset]):
    global _PRESETS
    if presets is None:
        _PRESETS = None
        AppSettings.remove(SettingKeys.PRESETS)
    else:
        _PRESETS = presets
        AppSettings.setValue(SettingKeys.PRESETS, jsonpickle.encode(presets))

def get_music_tags() -> dict[str,str]:
    global _MUSIC_TAGS
    if _MUSIC_TAGS is None:
        _MUSIC_TAGS = {_("Tag " +key):_("Tag "+key +" Description") for key in _TAGS}

    return _MUSIC_TAGS

def set_music_tags(tags :dict[str,str] | None):
    global _MUSIC_TAGS
    if tags is None:
        _MUSIC_TAGS = None
        AppSettings.remove(SettingKeys.TAGS)
    else:
        _MUSIC_TAGS = tags
        AppSettings.setValue(SettingKeys.TAGS, jsonpickle.encode(tags))


def get_music_category(key: str) -> MusicCategory:
    return next(cat for cat in get_music_categories() if cat.name == key)

def get_music_categories() -> list[MusicCategory]:
    global _MUSIC_CATEGORIES
    if _MUSIC_CATEGORIES is None:
        _MUSIC_CATEGORIES = [MusicCategory.from_key(key) for key in CATEGORIES]
    return _MUSIC_CATEGORIES

def set_music_categories(categories: list[MusicCategory] | None):
    global _MUSIC_CATEGORIES, CATEGORIES
    if categories is None:
        AppSettings.remove(SettingKeys.CATEGORIES)
        CATEGORIES = _DEFAULT_CATEGORIES.copy()
    else:
        AppSettings.setValue(SettingKeys.CATEGORIES, jsonpickle.encode(categories))
        CATEGORIES = [cat.name for cat in categories]

    _MUSIC_CATEGORIES = categories

AppSettings: QSettings = QSettings("Gandulf", "DungeonTuber")


def default_gemini_api_key() -> str | None:
    try:
        return str(open("../apikey.txt", "r").readline())
    except FileNotFoundError:
        return None


DEFAULT_GEMINI_API_KEY = default_gemini_api_key()
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

def reset_presets():
    global _PRESETS
    _PRESETS = None
    AppSettings.remove(SettingKeys.PRESETS)


_GEMINI_MODLES = None
_DEFAUL_GEMINI_MODLES = [
                "gemini-2.0-flash",
                "gemini-2.5-flash",
                "gemini-3.0-flash",
                "gemini-2.5-pro",
                "gemini-3.0-pro",
                "mock"
            ]

def get_gemini_models():
    global _GEMINI_MODLES
    if _GEMINI_MODLES is None:
        try:
            audio_capable_families = ['gemini-4', 'gemini-3.5', 'gemini-3', 'gemini-2.5', 'gemini-1.5']
            client = genai.Client(api_key=AppSettings.value(SettingKeys.GEMINI_API_KEY, DEFAULT_GEMINI_API_KEY))
            _GEMINI_MODLES = []
            for model in client.models.list(config=ListModelsConfig(page_size=100, query_base=True)):
                # Filter for models that support multimodal input (Audio/Video/Images)
                if any(family in model.name for family in audio_capable_families):
                    # We look for 'multimodal' or specific audio support in the description
                    capabilities = "Audio/Multimodal" if "flash" in model.name or "pro" in model.name else "Text Only"

                    if capabilities == "Audio/Multimodal":
                        _GEMINI_MODLES.append(model.name.removeprefix("models/"))

        except Exception as e:
            logger.exception("Failed to list models: {0}",e)

        if _GEMINI_MODLES is None or len(_GEMINI_MODLES) ==0:
            _GEMINI_MODLES = _DEFAUL_GEMINI_MODLES
        else:
            _GEMINI_MODLES.append("mock")

    return _GEMINI_MODLES

class SettingKeys(StrEnum):
    GEMINI_API_KEY = "geminiApiKey"
    GEMINI_MODEL = "geminiModel"
    MOCK_MODE = "mockMode"
    REPEAT_MODE = "repeatMode"
    VOLUME = "volume"
    LAST_DIRECTORY = "lastDirectory"
    FILTER_VISIBLE = "filterVisible"
    SKIP_ANALYZED_MUSIC = "skipAnalyzedMusic"
    EXPANDED_DIRS = "expandedDirs"
    ROOT_DIRECTORY = "rootDirectory"
    DIRECTORY_TREE = "directoryTree"
    FONT_SIZE = "fontSize"
    VISUALIZER = "visualizer"
    THEME = "theme"
    LOCALE = "locale"

    DYNAMIC_TABLE_COLUMNS = "dynamicTableColumns"
    COLUMN_FAVORITE_VISIBLE = "columnFavoriteVisible"
    COLUMN_TITLE_VISIBLE = "columnTitleVisible"
    COLUMN_ALBUM_VISIBLE = "columnAlbumVisible"
    COLUMN_ARTIST_VISIBLE = "columnArtistVisible"
    COLUMN_SUMMARY_VISIBLE = "columnSummaryVisible"

    TITLE_INSTEAD_OF_FILE_NAME = "titleInsteadOfFilename"

    TAGS = "tags"
    CATEGORIES = "categories"
    PRESETS = "presets"


class SettingsDialog(QDialog):
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

        # Tags Tab
        self.tags_tab = QWidget()
        self.init_tags_tab()
        self.tabs.addTab(self.tags_tab, _("Tags"))

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)



    def init_general_tab(self):
        layout = QVBoxLayout(self.general_tab)

        analyzer_layout = QFormLayout()
        analyzer_group = QGroupBox(_("Analyzer"))
        analyzer_group.setLayout(analyzer_layout)

        layout.addWidget(analyzer_group, 0)

        self.api_key_input = QLineEdit()
        self.api_key_input.setText(AppSettings.value(SettingKeys.GEMINI_API_KEY, DEFAULT_GEMINI_API_KEY))
        analyzer_layout.addRow(_("Gemini API Key") + ":", self.api_key_input)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(False)
        self.model_combo.addItems(get_gemini_models())
        self.model_combo.setCurrentText(AppSettings.value(SettingKeys.GEMINI_MODEL, DEFAULT_GEMINI_MODEL))
        analyzer_layout.addRow(_("Gemini Model") + ":", self.model_combo)

        self.skip_analyzed_mp3 = QCheckBox(_("Skip Analyzed Music"))
        self.skip_analyzed_mp3.setChecked(AppSettings.value(SettingKeys.SKIP_ANALYZED_MUSIC, True, type=bool))
        analyzer_layout.addRow("", self.skip_analyzed_mp3)

        self.locale_combo = QComboBox(editable=False)
        self.locale_combo.setToolTip(_("Requires restart"))
        self.locale_combo.addItem(_("System Default"), "")
        self.locale_combo.addItem(_("English"), "en")
        self.locale_combo.addItem(_("German"), "de", )
        language = AppSettings.value(SettingKeys.LOCALE, type=str)
        if language is None or language == "":
            self.locale_combo.setCurrentIndex(0)
        elif language == "en":
            self.locale_combo.setCurrentIndex(1)
        elif language == "de":
            self.locale_combo.setCurrentIndex(2)

        analyzer_layout.addRow(_("Language") + " *", self.locale_combo)

        self.skip_analyzed_mp3.setChecked(AppSettings.value(SettingKeys.SKIP_ANALYZED_MUSIC, True, type=bool))
        analyzer_layout.addRow("", self.skip_analyzed_mp3)
        #

        table_layout = QFormLayout()
        table_group = QGroupBox(_("Song Table"))
        table_group.setLayout(table_layout)

        layout.addWidget(table_group, 0)

        self.title_file_name_columns = QCheckBox(_("Use mp3 title instead of file name"))
        self.title_file_name_columns.setChecked(AppSettings.value(SettingKeys.TITLE_INSTEAD_OF_FILE_NAME, False, type=bool))
        table_layout.addRow("", self.title_file_name_columns)

        self.dynamic_table_columns = QCheckBox(_("Dynamic Category Columns"))
        self.dynamic_table_columns.setChecked(AppSettings.value(SettingKeys.DYNAMIC_TABLE_COLUMNS, False, type=bool))
        table_layout.addRow("", self.dynamic_table_columns)

        self.fav_column = QCheckBox(_("Favorite Column Visible"))
        self.fav_column.setChecked(AppSettings.value(SettingKeys.COLUMN_FAVORITE_VISIBLE, True, type=bool))
        table_layout.addRow("", self.fav_column)

        self.title_column = QCheckBox(_("Title Column Visible"))
        self.title_column.setChecked(AppSettings.value(SettingKeys.COLUMN_TITLE_VISIBLE, False, type=bool))
        table_layout.addRow("", self.title_column)

        self.artist_column = QCheckBox(_("Artist Column Visible"))
        self.artist_column.setChecked(AppSettings.value(SettingKeys.COLUMN_ARTIST_VISIBLE, False, type=bool))
        table_layout.addRow("", self.artist_column)

        self.album_column = QCheckBox(_("Album Column Visible"))
        self.album_column.setChecked(AppSettings.value(SettingKeys.COLUMN_ALBUM_VISIBLE, False, type=bool))
        table_layout.addRow("", self.album_column)

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
        self.categories_table.setItemDelegate(SettingsDialog.SettingsTableDelegate(groups))
        self.categories_table.setColumnCount(4)
        self.categories_table.setHorizontalHeaderLabels([_("Category"), _("Group"), _("Description"), _("Levels (json)")])
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
        self.categories_table.setRowCount(len(CATEGORIES))
        for row, cat in enumerate(get_music_categories()):
            self.categories_table.setItem(row, 0, QTableWidgetItem(cat.name))
            self.categories_table.setItem(row, 1, QTableWidgetItem(cat.group))
            self.categories_table.setItem(row, 2, QTableWidgetItem(cat.description))
            self.categories_table.setItem(row, 3, QTableWidgetItem(json.dumps(cat.levels, ensure_ascii=False, indent=2)))

        self.categories_table.resizeRowsToContents()

    def init_tags_tab(self):
        layout = QVBoxLayout(self.tags_tab)
        self.tags_table = QTableWidget()
        self.tags_table.setColumnCount(2)
        self.tags_table.setHorizontalHeaderLabels([_("Tag"), _("Description")])
        self.tags_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.fill_tags()

        layout.addWidget(self.tags_table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton(_("Add"))
        add_btn.clicked.connect(self.add_tag)
        btn_layout.addWidget(add_btn)

        remove_btn = QPushButton(_("Remove"))
        remove_btn.clicked.connect(self.remove_tag)
        btn_layout.addWidget(remove_btn)

        reset_tags_btn = QPushButton(_("Reset All"))
        reset_tags_btn.clicked.connect(self.reset_tags)
        btn_layout.addWidget(reset_tags_btn)
        layout.addLayout(btn_layout)

    def fill_tags(self):
        self.tags_table.setRowCount(len(get_music_tags()))
        for row, (tag, desc) in enumerate(get_music_tags().items()):
            self.tags_table.setItem(row, 0, QTableWidgetItem(tag))
            self.tags_table.setItem(row, 1, QTableWidgetItem(desc))

        self.tags_table.resizeRowsToContents()

    def add_category(self):
        row = self.categories_table.rowCount()
        self.categories_table.insertRow(row)
        self.categories_table.setItem(row, 0, QTableWidgetItem(_("New Category")))
        self.categories_table.setItem(row, 1, QTableWidgetItem(_("Group")))
        self.categories_table.setItem(row, 2, QTableWidgetItem(_("Description")))
        self.categories_table.setItem(row, 3, QTableWidgetItem("""{
  "1":"",
  "5":"",
  "10":""
}"""))
        self.categories_table.resizeRowsToContents()

    def reset_categories(self):
        set_music_categories(None)

        self.fill_categories()

    def reset_tags(self):
        set_music_tags(None)
        self.fill_tags()

    def remove_category(self):
        row = self.categories_table.currentRow()
        if row >= 0:
            self.categories_table.removeRow(row)

    def add_tag(self):
        row = self.tags_table.rowCount()
        self.tags_table.insertRow(row)
        self.tags_table.setItem(row, 0, QTableWidgetItem(_("New Tag")))
        self.tags_table.setItem(row, 1, QTableWidgetItem(_("Description")))

    def remove_tag(self):
        row = self.tags_table.currentRow()
        if row >= 0:
            self.tags_table.removeRow(row)

    def accept(self):
        AppSettings.setValue(SettingKeys.GEMINI_API_KEY, self.api_key_input.text())
        AppSettings.setValue(SettingKeys.GEMINI_MODEL, self.model_combo.currentText())
        AppSettings.setValue(SettingKeys.TITLE_INSTEAD_OF_FILE_NAME, self.title_file_name_columns.isChecked())
        AppSettings.setValue(SettingKeys.DYNAMIC_TABLE_COLUMNS, self.dynamic_table_columns.isChecked())
        AppSettings.setValue(SettingKeys.SKIP_ANALYZED_MUSIC, self.skip_analyzed_mp3.isChecked())
        AppSettings.setValue(SettingKeys.COLUMN_FAVORITE_VISIBLE, self.fav_column.isChecked())
        AppSettings.setValue(SettingKeys.COLUMN_TITLE_VISIBLE, self.title_column.isChecked())
        AppSettings.setValue(SettingKeys.COLUMN_ARTIST_VISIBLE, self.artist_column.isChecked())
        AppSettings.setValue(SettingKeys.COLUMN_ALBUM_VISIBLE, self.album_column.isChecked())
        AppSettings.setValue(SettingKeys.COLUMN_SUMMARY_VISIBLE, self.summary_column.isChecked())
        AppSettings.setValue(SettingKeys.LOCALE, self.locale_combo.currentData())

        _categories= []
        for row in range(self.categories_table.rowCount()):
            cat_item = self.categories_table.item(row, 0)
            group_item = self.categories_table.item(row, 1)
            desc_item = self.categories_table.item(row, 2)
            level_item = self.categories_table.item(row, 3)
            if cat_item and desc_item and group_item:
                cat = cat_item.text()
                group = group_item.text()
                desc = desc_item.text()
                levels = json.loads(level_item.text())
                if cat:
                    _categories.append(MusicCategory(cat, desc, levels, group=group))
        set_music_categories(_categories)

        _tags = {}
        for row in range(self.tags_table.rowCount()):
            tag_item = self.tags_table.item(row, 0)
            desc_item = self.tags_table.item(row, 1)
            if tag_item and desc_item:
                tag = tag_item.text()
                desc = desc_item.text()
                if tag:
                    _tags[tag] = desc

        set_music_tags(_tags)

        super().accept()
