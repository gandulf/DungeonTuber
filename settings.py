import json
from enum import StrEnum

import jsonpickle
from PySide6 import QtWidgets
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QCompleter, QTextEdit, QVBoxLayout, QTabWidget, QWidget, \
    QDialogButtonBox, QFormLayout, QCheckBox, QHBoxLayout, QTableWidget, QHeaderView, QPushButton, QTableWidgetItem, \
    QGroupBox

# --- Configuration ---
CATEGORY_MIN = 1
CATEGORY_MAX = 10

class Preset:
    name: str
    categories: dict[str, int]

    def __init__(self, name, categories):
        self.name = name
        self.categories = categories

PRESETS = [
    Preset("Kampf",
           {"Tempo": 8, "Dunkelheit": 8, "Heroik": 6, "Emotional": 3, "Mystik": 3, "Spannung": 8}),

]

_original_presets = PRESETS.copy()

MUSIC_TAGS = {"Reise": "Nordische Musik, Wikinger, Russland (Tempo<6, Spannung<4, Heroik<4, Mystik<5)",
              "Kampf": "Hektische, spannende treibende Musik (Tempo>6, Spannung>6, Heroik>5)"}

_original_music_tags = MUSIC_TAGS.copy()

class MusicCategory:
    def __init__(self, name: str, description: str, levels: dict[int,str], group :str = None) -> None:
        self.name = name
        self.group = group
        self.description = description
        self.levels = levels

# music_categories = {
#     "Dynamik": MusicCategory("Dynamik","",{
#         -5: "Minimalistisch (langsam, leise, dezent)",
#         0: "Moderat (fließend, neutral)",
#         +5: "Antreibend (schnell, energetisch, brachial)"
#     }),
#     "Moral": MusicCategory("Moral","",{
#         -5: "Abgründig (düster, bösartig, bedrohlich)",
#         0: "Neutral (sachlich, unvoreingenommen)",
#         +5: "Strahlend (heroisch, hoffnungsvoll, göttlich)"
#     }),
#     "Realität": MusicCategory("Realität","", {
#         -5: "Rustikal (bodenständig, Taverne, handgemacht)",
#         0: "Zivilisiert (klassisch-orchestral, geordnet)",
#         +5: "Sphärisch (magisch, transzendent, fremdartig)"
#     }),
#     "Gefühl": MusicCategory("Gefühl","", {
#         -5: "Kühl (distanziert, analytisch, einsam)",
#         0: "Ausgeglichen (ruhig erzählend)",
#         +5: "Herzergreifend (warm, intim, voller Pathos)"
#     }),
#     "Spannung": MusicCategory("Spannung","",{
#         -5: "Erlösend (abgeschlossen, sicher, entspannend)",
#         0: "Beiläufig (plätschernd, unaufgeregt)",
#         +5: "Nervenaufreibend (hochspannend, lauernd, kurz vor dem Knall)"
#     })
# }

# music_categories = [
#     ("Tempo", None,
#      "Tempo / Bewegung, Wie schnell sich die Musik anfühlt:\n1 = sehr langsam, getragen.\n10 = sehr schnell, treibend (Gut für Reise, Kampf, Verfolgung, hektische Szenen)."),
#     ("Intensität", None,
#      "Energie / Intensität, Wie „kraftvoll“ oder zurückhaltend die Musik wirkt.\n1 = ruhig, dezent.\n10 = überwältigend, episch."),
#     ("Dunkelheit", None,
#      "Dunkelheit / Bedrohung, Wie unheimlich, düster oder gefährlich die Musik wirkt.\n1 = hell, freundlich.\n10 = finster, bedrohlich, albtraumhaft (Perfekt für Dämonisches, Intrigen, finstere Orte)."),
#     ("Emotional", None,
#      "Emotionale Wärme, Wie emotional nah oder berührend die Musik ist.\n1 = kühl, distanziert.\n10 = sehr emotional, herzergreifend (Abschiede, Liebesszenen, Tragik, Erinnerungen)."),
#     ("Mystik", None,
#      "Mystik / Übernatürlichkeit, Wie stark Magie, Götter oder das Fremde mitschwingen.\n1 = weltlich, bodenständig.\n10 = stark magisch, transzendent (Magie, Feenreiche, Visionen, alte Artefakte)."),
#     ("Spannung", None,
#      "Spannung / Erwartung, Wie sehr die Musik „auf etwas hinführt“.\n1 = entspannend, abgeschlossen.\n10 = hochspannend, nervös (Schleichen, Intrigen, kurz vor dem Kampf)."),
#     ("Bodenständigkeit", None,
#      "Weltnähe / Bodenständigkeit, Wie „irdisch“ oder „alltäglich“ die Musik wirkt.\n1 = abstrakt, sphärisch.\n10 = tavernentauglich, volksnah (Tavernen, Städte, Reisen, Alltagsszenen)."),
#     ("Heroik", None,
#      "Heroik / Erhabenheit, Wie sehr die Musik Größe, Mut oder Heldentum vermittelt.\n1 = schlicht, persönlich, alltäglich, unscheinbar. intim, klein, persönlich (Kneipe, Alltag, Reise)\n10 = heroisch, göttlich, legendär, welterschütternd, schicksalshaft, königlich, imperial, göttlich (Schlachten, große Auftritte, Siege, Prophezeiungen)."),
# ]

MUSIC_CATEGORIES = {
    "Tempo": MusicCategory("Tempo", "Tempo / Bewegung & Intensität", {
        1: "Ruhig, dezent und sehr langsam (getragen)",
        5: "Moderat (fließend, neutral)",
        10: "Antreibend, schnell und überwältigend (episch, hektisch, treibend)"
    }),
    "Dunkelheit": MusicCategory("Dunkelheit", "Bedrohung & Licht", {
        1: "Hell, freundlich und einladend",
        5: "Neutral (unvoreingenommen, beobachtend)",
        10: "Finster, bedrohlich und albtraumhaft (Dämonisches, Intrigen)"
    }),
    "Emotional": MusicCategory("Emotional", "Emotionale Wärme & Distanz", {
        1: "Kühl, distanziert und sachlich",
        5: "Ausgeglichen (ruhig erzählend)",
        10: "Sehr emotional, herzergreifend und intim (Tragik, Abschiede)"
    }),
    "Mystik": MusicCategory("Mystik", "Übernatürlichkeit vs. Weltlichkeit", {
        1: "Weltlich, bodenständig und irdisch, Tavernentauglich, volksnah und handgemacht (Reise, Alltag)",
        5: "Gelegentliche magische Nuancen, Zivilisiert (klassisch-orchestral, geordnet)",
        10: "Stark magisch, transzendent, abstrakt, sphärisch entfremdet und fremdartig (Visionen, Götter)"
    }),
    "Spannung": MusicCategory("Spannung", "Erwartung & Entspannung", {
        1: "Entspannend, abgeschlossen und sicher",
        5: "Beiläufig (plätschernd, unaufgeregt)",
        10: "Hochspannend, nervös und lauernd (kurz vor dem Kampf)"
    }),
    "Heroik": MusicCategory("Heroik", "Größe & Schlichtheit", {
        1: "Schlicht, persönlich, intim und klein (Kneipe, Alltag)",
        5: "Solidarisch (gefestigt, mutig)",
        10: "Heroisch, legendär, schicksalhaft und göttlich (Schlachten, Siege)"
    })
}

_original_music_categories = MUSIC_CATEGORIES.copy()

def get_category_description(category: str) -> str | None:
    cat = MUSIC_CATEGORIES[category]
    tooltip = cat.description+"\n"

    for level, descr in cat.levels.items():
        tooltip += str(level)+": "+descr+"\n"

    return tooltip.removesuffix("\n")

settings: QSettings = QSettings("Gandulf", "DungeonTuber")

def default_gemini_api_key() -> str | None:
    try:
        return str(open("apikey.txt","r").readline())
    except FileNotFoundError:
        return None

DEFAULT_GEMINI_API_KEY = default_gemini_api_key()
DEFAULT_MOCK_MODE = False

def reset_presets():
    global PRESETS
    PRESETS = _original_presets.copy()

class SettingKeys(StrEnum):
    GEMINI_API_KEY = "geminiApiKey"
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

    DYNAMIC_TABLE_COLUMNS = "dynamicTableColumns"
    COLUMN_FAVORITE_VISIBLE = "columnFavoriteVisible"
    COLUMN_TITLE_VISIBLE="columnTitleVisible"
    COLUMN_ALBUM_VISIBLE = "columnAlbumVisible"
    COLUMN_ARTIST_VISIBLE="columnArtistVisible"
    COLUMN_SUMMARY_VISIBLE ="columnSummaryVisible"

    TITLE_INSTEAD_OF_FILE_NAME = "titleInsteadOfFilename"

    TAGS = "tags"
    CATEGORIES = "categories"
    PRESETS ="presets"


class SettingsDialog(QDialog):
    class SettingsTableDelegate(QtWidgets.QStyledItemDelegate):

        def __init__(self, groups: set[str]):
            super().__init__()
            self.groups = groups

        def createEditor(self, parent, option, index):
            if index.column() == 1:
                lineEdit = QLineEdit(parent)
                completer = QCompleter(sorted(list(self.groups)))
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
                lineEdit.setCompleter(completer)
                return lineEdit
            elif index.column() == 2 or index.column() == 3:
                textEdit = QTextEdit(parent)
                return textEdit
            else:
                return super(SettingsDialog.SettingsTableDelegate, self).createEditor(parent, option, index)

        def setEditorData(self, editor, index):
            if index.column() == 1:
                editor.setText(index.data())
            elif index.column() == 2 or index.column() == 3:
                editor.setPlainText(index.data())
            else:
                return super(SettingsDialog.SettingsTableDelegate, self).setEditorData(editor, index)

        def setModelData(self, editor, model, index):
            if index.column() == 1:
                model.setData(index, editor.text())
                self.groups.add(editor.text())
            elif index.column() == 2 or index.column() == 3:
                model.setData(index, editor.toPlainText())
            else:
                return super(SettingsDialog.SettingsTableDelegate, self).setModelData(editor, model, index)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West)
        layout.addWidget(self.tabs)

        # General Tab
        self.general_tab = QWidget()
        self.init_general_tab()
        self.tabs.addTab(self.general_tab, "General")

        # Categories Tab
        self.categories_tab = QWidget()
        self.init_categories_tab()
        self.tabs.addTab(self.categories_tab, "Categories")

        # Tags Tab
        self.tags_tab = QWidget()
        self.init_tags_tab()
        self.tabs.addTab(self.tags_tab, "Tags")

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def init_general_tab(self):
        global settings
        layout =  QVBoxLayout(self.general_tab)

        analyzer_layout = QFormLayout()
        analyzerGroup = QGroupBox("Analyzer")
        analyzerGroup.setLayout(analyzer_layout)

        layout.addWidget(analyzerGroup,0)

        self.api_key_input = QLineEdit()
        self.api_key_input.setText(settings.value(SettingKeys.GEMINI_API_KEY, DEFAULT_GEMINI_API_KEY))
        analyzer_layout.addRow("Gemini API Key:", self.api_key_input)

        self.mock_mode_checkbox = QCheckBox("Enable Mock Mode")
        self.mock_mode_checkbox.setChecked(settings.value(SettingKeys.MOCK_MODE, DEFAULT_MOCK_MODE, type=bool))
        analyzer_layout.addRow("", self.mock_mode_checkbox)

        self.skip_analyzed_mp3 = QCheckBox("Skip Analyzed Music")
        self.skip_analyzed_mp3.setChecked(settings.value(SettingKeys.SKIP_ANALYZED_MUSIC, True, type=bool))
        analyzer_layout.addRow("", self.skip_analyzed_mp3)

        #

        table_layout = QFormLayout()
        tableGroup = QGroupBox("Song Table")
        tableGroup.setLayout(table_layout)

        layout.addWidget(tableGroup,0)

        self.title_file_name_columns = QCheckBox("Use mp3 title instead of file name")
        self.title_file_name_columns.setChecked(settings.value(SettingKeys.TITLE_INSTEAD_OF_FILE_NAME, False, type=bool))
        table_layout.addRow("", self.title_file_name_columns)

        self.dynamic_table_columns = QCheckBox("Dynamic Category Columns")
        self.dynamic_table_columns.setChecked(settings.value(SettingKeys.DYNAMIC_TABLE_COLUMNS, False, type=bool))
        table_layout.addRow("", self.dynamic_table_columns)

        self.fav_column = QCheckBox("Favorite Column Visible")
        self.fav_column.setChecked(settings.value(SettingKeys.COLUMN_FAVORITE_VISIBLE, True, type=bool))
        table_layout.addRow("", self.fav_column)

        self.title_column = QCheckBox("Title Column Visible")
        self.title_column.setChecked(settings.value(SettingKeys.COLUMN_TITLE_VISIBLE, False, type=bool))
        table_layout.addRow("", self.title_column)

        self.artist_column = QCheckBox("Artist Column Visible")
        self.artist_column.setChecked(settings.value(SettingKeys.COLUMN_ARTIST_VISIBLE, False, type=bool))
        table_layout.addRow("", self.artist_column)

        self.album_column = QCheckBox("Album Column Visible")
        self.album_column.setChecked(settings.value(SettingKeys.COLUMN_ALBUM_VISIBLE, False, type=bool))
        table_layout.addRow("", self.album_column)

        self.summary_column = QCheckBox("Summary Visible")
        self.summary_column.setChecked(settings.value(SettingKeys.COLUMN_SUMMARY_VISIBLE, True, type=bool))
        table_layout.addRow("", self.summary_column)

        layout.addStretch()

    def init_categories_tab(self):

        groups = set()
        for cat in MUSIC_CATEGORIES.values():
            if cat.group is not None and cat.group != "":
                groups.add(cat.group)

        layout = QVBoxLayout(self.categories_tab)
        self.categories_table = QTableWidget()
        self.categories_table.setItemDelegate(SettingsDialog.SettingsTableDelegate(groups))
        self.categories_table.setColumnCount(4)
        self.categories_table.setHorizontalHeaderLabels(["Category", "Group", "Description","Levels (json)"])
        self.categories_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.fill_categories()

        layout.addWidget(self.categories_table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_category)
        btn_layout.addWidget(add_btn)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self.remove_category)
        btn_layout.addWidget(remove_btn)

        reset_cat_btn = QPushButton("Reset All")
        reset_cat_btn.clicked.connect(self.reset_categories)
        btn_layout.addWidget(reset_cat_btn)
        layout.addLayout(btn_layout)

    def fill_categories(self):
        self.categories_table.setRowCount(len(MUSIC_CATEGORIES))
        for row, cat in enumerate(MUSIC_CATEGORIES.values()):
            self.categories_table.setItem(row, 0, QTableWidgetItem(cat.name))
            self.categories_table.setItem(row, 1, QTableWidgetItem(cat.group))
            self.categories_table.setItem(row, 2, QTableWidgetItem(cat.description))
            self.categories_table.setItem(row, 3, QTableWidgetItem(json.dumps(cat.levels, ensure_ascii=False, indent=2)))

        self.categories_table.resizeRowsToContents()

    def init_tags_tab(self):
        layout = QVBoxLayout(self.tags_tab)
        self.tags_table = QTableWidget()
        self.tags_table.setColumnCount(2)
        self.tags_table.setHorizontalHeaderLabels(["Tag", "Description"])
        self.tags_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.fill_tags()

        layout.addWidget(self.tags_table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_tag)
        btn_layout.addWidget(add_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self.remove_tag)
        btn_layout.addWidget(remove_btn)

        reset_tags_btn = QPushButton("Reset All")
        reset_tags_btn.clicked.connect(self.reset_tags)
        btn_layout.addWidget(reset_tags_btn)
        layout.addLayout(btn_layout)

    def fill_tags(self):
        self.tags_table.setRowCount(len(MUSIC_TAGS))
        for row, (tag, desc) in enumerate(MUSIC_TAGS.items()):
            self.tags_table.setItem(row, 0, QTableWidgetItem(tag))
            self.tags_table.setItem(row, 1, QTableWidgetItem(desc))

        self.tags_table.resizeRowsToContents()

    def add_category(self):
        row = self.categories_table.rowCount()
        self.categories_table.insertRow(row)
        self.categories_table.setItem(row, 0, QTableWidgetItem("New Category"))
        self.categories_table.setItem(row, 1, QTableWidgetItem("Group"))
        self.categories_table.setItem(row, 2, QTableWidgetItem("Description"))
        self.categories_table.setItem(row, 3, QTableWidgetItem("""{
  "1":"",
  "5":"",
  "10":""
}"""))
        self.categories_table.resizeRowsToContents()

    def reset_categories(self):
        global MUSIC_CATEGORIES, settings
        settings.remove(SettingKeys.CATEGORIES)

        MUSIC_CATEGORIES = _original_music_categories.copy()

        self.fill_categories()

    def reset_tags(self):
        global MUSIC_TAGS, settings
        settings.remove(SettingKeys.TAGS)

        MUSIC_TAGS = _original_music_tags.copy()

        self.fill_tags()

    def remove_category(self):
        row = self.categories_table.currentRow()
        if row >= 0:
            self.categories_table.removeRow(row)

    def add_tag(self):
        row = self.tags_table.rowCount()
        self.tags_table.insertRow(row)
        self.tags_table.setItem(row, 0, QTableWidgetItem("New Tag"))
        self.tags_table.setItem(row, 1, QTableWidgetItem("Description"))

    def remove_tag(self):
        row = self.tags_table.currentRow()
        if row >= 0:
            self.tags_table.removeRow(row)

    def accept(self):
        global settings
        settings.setValue(SettingKeys.GEMINI_API_KEY, self.api_key_input.text())
        settings.setValue(SettingKeys.MOCK_MODE, self.mock_mode_checkbox.isChecked())
        settings.setValue(SettingKeys.TITLE_INSTEAD_OF_FILE_NAME, self.title_file_name_columns.isChecked())
        settings.setValue(SettingKeys.DYNAMIC_TABLE_COLUMNS, self.dynamic_table_columns.isChecked())
        settings.setValue(SettingKeys.SKIP_ANALYZED_MUSIC, self.skip_analyzed_mp3.isChecked())
        settings.setValue(SettingKeys.COLUMN_FAVORITE_VISIBLE, self.fav_column.isChecked())
        settings.setValue(SettingKeys.COLUMN_TITLE_VISIBLE, self.title_column.isChecked())
        settings.setValue(SettingKeys.COLUMN_ARTIST_VISIBLE, self.artist_column.isChecked())
        settings.setValue(SettingKeys.COLUMN_ALBUM_VISIBLE, self.album_column.isChecked())
        settings.setValue(SettingKeys.COLUMN_SUMMARY_VISIBLE, self.summary_column.isChecked())

        MUSIC_CATEGORIES.clear()
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
                    MUSIC_CATEGORIES[cat]= MusicCategory(cat, desc, levels, group = group)
        settings.setValue(SettingKeys.CATEGORIES, jsonpickle.encode(MUSIC_CATEGORIES))

        MUSIC_TAGS.clear()
        for row in range(self.tags_table.rowCount()):
            tag_item = self.tags_table.item(row, 0)
            desc_item = self.tags_table.item(row, 1)
            if tag_item and desc_item:
                tag = tag_item.text()
                desc = desc_item.text()
                if tag:
                    MUSIC_TAGS[tag] = desc

        settings.setValue(SettingKeys.TAGS, json.dumps(MUSIC_TAGS))

        super().accept()
