import json
import logging
from enum import StrEnum

import jsonpickle
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QCompleter, QTextEdit, QVBoxLayout, QTabWidget, QWidget, \
    QDialogButtonBox, QFormLayout, QCheckBox, QHBoxLayout, QTableWidget, QHeaderView, QPushButton, QTableWidgetItem, \
    QGroupBox, QComboBox, QStyledItemDelegate, QMessageBox, QLabel
from google import genai
from google.genai.types import ListModelsConfig

from config.utils import get_path, get_available_locales, restart_application

logger = logging.getLogger("main")

# --- Configuration ---
CATEGORY_MIN = 1
CATEGORY_MAX = 10

CAT_VALENCE = "Valence"
CAT_AROUSAL = "Arousal"

CAT_TEMPO = "Tempo"
CAT_DARKNESS = "Darkness"
CAT_EMOTIONAL = "Emotional"
CAT_MYSTICISM = "Mysticism"
CAT_TENSION = "Tension"
CAT_HEROISM = "Heroism"

class MusicCategory():
    key: str
    name: str
    description: str
    levels: dict[int, str]
    group: str = None

    def __init__(self, name: str, description: str, levels: dict[int, str], group: str = None, key :str = None):
        if key is None:
            self.key = name
        else:
            self.key = key
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

        return MusicCategory(name, description, levels, key = key)

    def equals(self, name_or_key:str ):
        return self.name == name_or_key or self.key == name_or_key or self.name == _(name_or_key)

    def get_detailed_description(self):
        tooltip = self.description + "\n"

        for level, descr in self.levels.items():
            tooltip += str(level) + ": " + descr + "\n"

        return tooltip.removesuffix("\n")

class Preset:

    name: str
    categories: dict[str,int] | None = None
    tags: list[str]

    def __init__(self, name: str, levels: dict[str, int],tags: list[str]= None):
        self.name = name
        self.categories = levels
        self.tags = tags

_PRESETS: list[Preset] |None = None

_TAGS =["Travel","Fight"]
_MUSIC_TAGS = None

_DEFAULT_CATEGORIES =[CAT_VALENCE, CAT_AROUSAL, CAT_TEMPO, CAT_EMOTIONAL, CAT_MYSTICISM, CAT_HEROISM]
_MUSIC_CATEGORIES = None
_CATEGORIES = None

def get_presets() -> list[Preset]:
    global _PRESETS
    if _PRESETS is None:
        _PRESETS =[
            Preset(_("Grim"),
                   {_(CAT_VALENCE): 1, _(CAT_AROUSAL):5, _(CAT_TEMPO): 0, _(CAT_HEROISM): 4, _(CAT_EMOTIONAL): 3, _(CAT_MYSTICISM): 4}),
        ]

    return _PRESETS

def remove_preset(preset: Preset):
    _PRESETS.remove(preset)
    AppSettings.setValue(SettingKeys.PRESETS, jsonpickle.encode(_PRESETS))

def add_preset(preset: Preset):
    _PRESETS.append(preset)
    AppSettings.setValue(SettingKeys.PRESETS, jsonpickle.encode(_PRESETS))

def set_presets(presets: list[Preset]):
    global _PRESETS
    if presets is None:
        _PRESETS = None
        AppSettings.remove(SettingKeys.PRESETS)
    else:
        presets = [preset for preset in presets if preset.name is not None]
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
    cats = [cat for cat in get_music_categories() if cat.name == key or cat.key == key]
    return  next(cats) if cats and len(cats)>0 else None

def get_categories() -> list[str]:
    global _CATEGORIES

    if _CATEGORIES is None:
        _CATEGORIES = [cat.name for cat in get_music_categories()]

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
        AppSettings.setValue(SettingKeys.CATEGORIES, jsonpickle.encode(categories))
        _CATEGORIES = [cat.name for cat in categories]

    _MUSIC_CATEGORIES = categories


AppSettings: QSettings = QSettings("Gandulf", "DungeonTuber")

def default_gemini_api_key() -> str | None:
    try:
        return str(open(get_path("apikey.txt"), "r").readline())
    except FileNotFoundError:
        return None


DEFAULT_GEMINI_API_KEY = default_gemini_api_key()
DEFAULT_OPEN_AI_API_KEY = ""
DEFAULT_OPEN_AI_MODEL = "gpt-4o-audio-preview"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

def reset_presets():
    global _PRESETS
    _PRESETS = None
    AppSettings.remove(SettingKeys.PRESETS)


_AI_MODLES = None
_DEFAUL_AI_MODLES = [
                "gemini-2.0-flash",
                "gemini-2.5-flash",
                "gemini-3.0-flash",
                "gemini-2.5-pro",
                "gemini-3.0-pro"
            ]

_FIXED_AI_MODLES = [
                "gpt-4o-audio-preview",
                "gpt-4o-mini-audio-preview",
                "mock"
            ]

def get_gemini_models():
    global _AI_MODLES
    if _AI_MODLES is None:
        try:
            audio_capable_families = ['gemini-4', 'gemini-3.5', 'gemini-3', 'gemini-2.5', 'gemini-1.5']
            api_key = AppSettings.value(SettingKeys.GEMINI_API_KEY, DEFAULT_GEMINI_API_KEY)
            if api_key is not None and api_key != "":
                client = genai.Client(api_key=AppSettings.value(SettingKeys.GEMINI_API_KEY, DEFAULT_GEMINI_API_KEY))
                _AI_MODLES = []
                for model in client.models.list(config=ListModelsConfig(page_size=100, query_base=True)):
                    # Filter for models that support multimodal input (Audio/Video/Images)
                    if any(family in model.name for family in audio_capable_families):
                        # We look for 'multimodal' or specific audio support in the description
                        capabilities = "Audio/Multimodal" if "flash" in model.name or "pro" in model.name else "Text Only"

                        if capabilities == "Audio/Multimodal":
                            _AI_MODLES.append(model.name.removeprefix("models/"))

        except Exception as e:
            logger.exception("Failed to list models: {0}",e)

        if _AI_MODLES is None or len(_AI_MODLES) ==0:
            _AI_MODLES = _DEFAUL_AI_MODLES

    return _AI_MODLES + _FIXED_AI_MODLES

class SettingKeys(StrEnum):
    GEMINI_API_KEY = "geminiApiKey"
    OPENAI_API_KEY = "openAiApiKey"
    AI_MODEL = "aiModel"

    REPEAT_MODE = "repeatMode"
    VOLUME = "volume"
    NORMALIZE_VOLUME = "normalizeVolume"
    EFFECTS_DIRECTORY ="effectsDirectory"
    EFFECTS_TREE = "effectsTree"
    LAST_DIRECTORY = "lastDirectory"
    FILTER_VISIBLE = "filterVisible"
    SKIP_ANALYZED_MUSIC = "skipAnalyzedMusic"
    EXPANDED_DIRS = "expandedDirs"
    ROOT_DIRECTORY = "rootDirectory"
    DIRECTORY_TREE = "directoryTree"
    RUSSEL_WIDGET ="russelWidget"
    CATEGORY_WIDGETS ="categoryWidgets"
    BPM_WIDGET = "bpmWidget"
    FONT_SIZE = "fontSize"
    VISUALIZER = "visualizer"
    THEME = "theme"
    LOCALE = "locale"
    START_TOUR = "startTour"
    OPEN_TABLES = "openTables"

    DYNAMIC_TABLE_COLUMNS = "dynamicTableColumns"
    DYNAMIC_SCORE_COLUMN = "dynamicScoreColumn"
    COLUMN_FAVORITE_VISIBLE = "columnFavoriteVisible"
    COLUMN_SCORE_VISIBLE = "columnScoreVisible"
    COLUMN_TITLE_VISIBLE = "columnTitleVisible"
    COLUMN_ALBUM_VISIBLE = "columnAlbumVisible"
    COLUMN_GENRE_VISIBLE = "columnGenreVisible"
    COLUMN_ARTIST_VISIBLE = "columnArtistVisible"
    COLUMN_BPM_VISIBLE = "columnBPMVisible"
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

    def ai_model_changed(self, text: str):
        if "gemini" in text:
            self.analyzer_layout.setRowVisible(self.gemini_api_key_input,True)
            self.analyzer_layout.setRowVisible(self.openai_api_key_input, False)
        elif "gpt" in text:
            self.analyzer_layout.setRowVisible(self.gemini_api_key_input, False)
            self.analyzer_layout.setRowVisible(self.openai_api_key_input, True)
        elif "mock" == text:
            self.analyzer_layout.setRowVisible(self.gemini_api_key_input, False)
            self.analyzer_layout.setRowVisible(self.openai_api_key_input, False)
        else:
            self.analyzer_layout.setRowVisible(self.gemini_api_key_input, True)
            self.analyzer_layout.setRowVisible(self.openai_api_key_input, True)


    def init_general_tab(self):
        layout = QVBoxLayout(self.general_tab)

        self.analyzer_layout = QFormLayout()
        analyzer_group = QGroupBox(_("Analyzer"))
        analyzer_group.setLayout(self.analyzer_layout)

        layout.addWidget(analyzer_group, 0)

        self.gemini_api_key_input = QLineEdit()
        self.gemini_api_key_input.setText(AppSettings.value(SettingKeys.GEMINI_API_KEY, DEFAULT_GEMINI_API_KEY))
        self.analyzer_layout.addRow(_("Gemini API Key") + ":", self.gemini_api_key_input)

        self.openai_api_key_input = QLineEdit()
        self.openai_api_key_input.setText(AppSettings.value(SettingKeys.OPENAI_API_KEY, DEFAULT_OPEN_AI_API_KEY))
        self.analyzer_layout.addRow(_("OpenAI API Key") + ":", self.openai_api_key_input)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(False)
        self.model_combo.addItems(get_gemini_models())
        self.model_combo.setCurrentText(AppSettings.value(SettingKeys.AI_MODEL, DEFAULT_GEMINI_MODEL))
        self.model_combo.currentTextChanged.connect(self.ai_model_changed)
        self.analyzer_layout.addRow(_("AI Model") + ":", self.model_combo)

        self.ai_model_changed(self.model_combo.currentText())

        self.skip_analyzed_mp3 = QCheckBox(_("Skip Analyzed Music"))
        self.skip_analyzed_mp3.setChecked(AppSettings.value(SettingKeys.SKIP_ANALYZED_MUSIC, True, type=bool))
        self.analyzer_layout.addRow("", self.skip_analyzed_mp3)

        self.locale_combo = QComboBox(editable=False)
        self.locale_combo.setToolTip(_("Requires restart"))
        self.locale_combo.addItem(_("System Default"), "")
        self.locale_combo.setCurrentIndex(0)
        current_language = AppSettings.value(SettingKeys.LOCALE, type=str)

        for i, locale in enumerate(get_available_locales()):
            self.locale_combo.addItem(_(locale), locale)
            if current_language == locale:
                self.locale_combo.setCurrentIndex(i+1)

        self.analyzer_layout.addRow(_("Language") + " *", self.locale_combo)

        self.skip_analyzed_mp3.setChecked(AppSettings.value(SettingKeys.SKIP_ANALYZED_MUSIC, True, type=bool))
        self.analyzer_layout.addRow("", self.skip_analyzed_mp3)

        #
        self.player_layout = QFormLayout()
        player_group = QGroupBox(_("Player"))
        player_group.setLayout(self.player_layout)

        self.normalize_volume = QCheckBox(_("Normalize Volume*"))
        self.normalize_volume.setToolTip(_("Requires restart"))
        self.normalize_volume.setChecked(AppSettings.value(SettingKeys.NORMALIZE_VOLUME, True, type=bool))
        self.player_layout.addRow("", self.normalize_volume)
        normalize_volume_description = QLabel(_("All songs will be played at a normalized volume."))
        normalize_volume_description.setStyleSheet(f"font-size:12px")
        normalize_volume_description.setContentsMargins(28, 0, 0, 0)
        self.player_layout.addRow("", normalize_volume_description)

        layout.addWidget(player_group, 0)
        #
        table_layout = QFormLayout()
        table_group = QGroupBox(_("Song Table"))
        table_group.setLayout(table_layout)

        layout.addWidget(table_group, 0)

        self.title_file_name_columns = QCheckBox(_("Use mp3 title instead of file name"))
        self.title_file_name_columns.setChecked(AppSettings.value(SettingKeys.TITLE_INSTEAD_OF_FILE_NAME, False, type=bool))
        table_layout.addRow("", self.title_file_name_columns)

        self.dynamic_score_column = QCheckBox(_("Dynamic Category Columns"))
        self.dynamic_score_column.setChecked(AppSettings.value(SettingKeys.DYNAMIC_SCORE_COLUMN, False, type=bool))
        table_layout.addRow("", self.dynamic_score_column)
        dynamic_score_description = QLabel(_("Only show score column if any filters are active."))
        dynamic_score_description.setStyleSheet(f"font-size:12px")
        dynamic_score_description.setContentsMargins(28, 0, 0, 0)
        table_layout.addRow("", dynamic_score_description)

        self.dynamic_table_columns = QCheckBox(_("Dynamic Category Columns"))
        self.dynamic_table_columns.setChecked(AppSettings.value(SettingKeys.DYNAMIC_TABLE_COLUMNS, False, type=bool))
        table_layout.addRow("", self.dynamic_table_columns)
        dynamic_colomns_description = QLabel(_("Only category columns with an active filter value are display else they are hidden automatically."))
        dynamic_colomns_description.setStyleSheet(f"font-size:12px")
        dynamic_colomns_description.setContentsMargins(28,0,0,0)
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
        self.categories_table.setRowCount(len(get_music_categories()))
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

    def requires_restart(self):
        result = False
        current_locale = AppSettings.value(SettingKeys.LOCALE, type=str)
        result = result or current_locale != self.locale_combo.currentData()
        result = result or self.normalize_volume.isChecked() != AppSettings.value(SettingKeys.NORMALIZE_VOLUME,True, type=bool)

        return result

    def accept(self):
        requires_restart = self.requires_restart()

        AppSettings.setValue(SettingKeys.GEMINI_API_KEY, self.gemini_api_key_input.text())
        AppSettings.setValue(SettingKeys.OPENAI_API_KEY, self.openai_api_key_input.text())
        AppSettings.setValue(SettingKeys.AI_MODEL, self.model_combo.currentText())
        AppSettings.setValue(SettingKeys.TITLE_INSTEAD_OF_FILE_NAME, self.title_file_name_columns.isChecked())
        AppSettings.setValue(SettingKeys.DYNAMIC_TABLE_COLUMNS, self.dynamic_table_columns.isChecked())
        AppSettings.setValue(SettingKeys.DYNAMIC_SCORE_COLUMN, self.dynamic_score_column.isChecked())
        AppSettings.setValue(SettingKeys.SKIP_ANALYZED_MUSIC, self.skip_analyzed_mp3.isChecked())
        AppSettings.setValue(SettingKeys.COLUMN_SUMMARY_VISIBLE, self.summary_column.isChecked())
        AppSettings.setValue(SettingKeys.LOCALE, self.locale_combo.currentData())

        AppSettings.setValue(SettingKeys.NORMALIZE_VOLUME, self.normalize_volume.isChecked())

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


        if requires_restart:

            reply = QMessageBox.question(self, _("Restart Required"),
                                         _("Changing the language requires a restart. Do you want to restart now?"),
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

            if reply == QMessageBox.StandardButton.Yes:
                restart_application()

        super().accept()
