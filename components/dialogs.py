import json
import logging
import os
from pathlib import Path

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QPixmap, QIcon, QShortcut, QKeySequence, QPalette
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QApplication, QDialogButtonBox, QLineEdit, QSpinBox, \
    QTextEdit, QCheckBox, QFormLayout, QMessageBox, QFileDialog, QPushButton, QScrollArea, QCompleter, QStyledItemDelegate, QHBoxLayout, QHeaderView, \
    QTableWidget, QTableWidgetItem, QGroupBox, QComboBox, QWidget, QTabWidget

from config.theme import app_theme
from config.utils import get_path, is_latest_version, get_latest_version, DOWNLOAD_LINK, restart_application, get_broadcast_ip, get_available_locales, \
    get_executable_path
from config.settings import MusicCategory, set_music_categories, SettingKeys, AppSettings, get_music_categories, has_local_voxalyzer
from components.lights import LightSettingsWidget
from logic.lightengine import LightSetting
from logic.mp3 import Mp3Entry, update_mp3_data, update_mp3_cover

logger = logging.getLogger(__file__)

class NameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(_("Save as Preset"))
        self.setWindowIcon(QIcon.fromTheme(QIcon.ThemeIcon.DocumentSaveAs))
        self.setModal(True)

        layout = QFormLayout(self)
        layout.setObjectName("save_name_layout")
        self.name_edit = QLineEdit()
        layout.addRow("Name", self.name_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_name(self):
        return self.name_edit.text()

    def set_name(self, name:str):
        return self.name_edit.setText(name)

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("About"))

        layout = QVBoxLayout(self)

        # Logo/Splash
        logo_label = QLabel()
        splash_path = get_path("docs/splash.png")
        if os.path.exists(splash_path):
            pixmap = QPixmap(splash_path)
            if not pixmap.isNull():
                # Scale to reasonable size, e.g. width 400
                scaled_pixmap = pixmap.scaledToWidth(400, Qt.TransformationMode.SmoothTransformation)
                logo_label.setPixmap(scaled_pixmap)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo_label)

        if not is_latest_version():
            version_text = _("Newer version available {0}").format(f"<a href=\"{DOWNLOAD_LINK}\">{get_latest_version()}</a>")
        else:
            version_text = ""
        # Text Info
        # Using HTML for formatting and link
        info_text = f"""
        <h3 align="center">Dungeon Tuber {QApplication.applicationVersion()}</h3>
        <p align="center"><strong>{version_text}</strong></p>
        <p align="center">{_('Author')}: Gandulf Kohlweiss</p>
        <p align="center"><a href="https://github.com/gandulf/DungeonTuber">https://github.com/gandulf/DungeonTuber</a></p>
        """

        info_label = QLabel(info_text)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setOpenExternalLinks(True)
        layout.addWidget(info_label)

        # Button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)



class EditSongDialog(QDialog):

    def __init__(self, data: Mp3Entry, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Edit Song"))
        self.resize(500, 400)
        self.data = data

        self.new_cover_path = None
        layout = QFormLayout(self)

        self.name_edit = QLineEdit(data.name)
        layout.addRow(_("Name") + ":", self.name_edit)

        self.title_edit = QLineEdit(data.title)
        layout.addRow(_("Title") + ":", self.title_edit)

        self.album_edit = QLineEdit(data.album)
        layout.addRow(_("Album") + ":", self.album_edit)

        self.artist_edit = QLineEdit(data.artist)
        layout.addRow(_("Artist") + ":", self.artist_edit)

        self.genre_edit = QLineEdit(", ".join(data.genres))
        self.genre_edit.setToolTip(_("Separate multiple tags with comma"))
        layout.addRow(_("Genre") + ":", self.genre_edit)

        self.bpm_edit = QSpinBox()
        self.bpm_edit.setRange(0,200)
        self.bpm_edit.setSpecialValueText("")
        if data.bpm:
            self.bpm_edit.setValue(data.bpm)
        layout.addRow(_("BPM") + ":", self.bpm_edit)

        self.tags_edit = QLineEdit(", ".join(data.tags))
        self.tags_edit.setToolTip(_("Separate multiple tags with comma"))
        layout.addRow(_("Tags") + ":", self.tags_edit)

        self.summary_edit = QTextEdit()
        if data.summary:
            self.summary_edit.setPlainText(data.summary)
        layout.addRow(_("Summary") + ":", self.summary_edit)

        self.favorite_edit = QCheckBox(_("Favorite"))
        self.favorite_edit.setChecked(data.favorite)

        layout.addRow("", self.favorite_edit)

        self.choose_cover = QPushButton(_("Select Image"))
        self.choose_cover.clicked.connect(self.pick_image_file)
        layout.addRow(_("Cover"), self.choose_cover)

        self.light_settings = LightSettingsWidget(settings = self.data.light)
        self.light_settings.setDisabled(False)
        layout.addRow(_("Lights"), self.light_settings)

        file_name = QLabel(os.path.abspath(data.path))
        file_name.setWordWrap(True)
        file_name.setFont(app_theme.font_small)
        layout.addRow(_("File") + ":", file_name)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def pick_image_file(self):
        file_path, ignore = QFileDialog.getOpenFileName(self, _("Select Image"),
                                                        filter=_("Image (*.png *.jpg *.jpeg *.gif *.bmp);;All (*)"))
        if file_path:
            self.new_cover_path = file_path

    def accept(self, /):

        self.data.title = self.title_edit.text()
        self.data.artist = self.artist_edit.text()
        self.data.album = self.album_edit.text()
        self.data.bpm = self.bpm_edit.value() if self.bpm_edit.value() > 0 else None
        self.data.genres = list(map(str.strip, self.genre_edit.text().split(","))) if self.genre_edit.text() != "" else []
        self.data.summary = self.summary_edit.toPlainText()
        self.data.favorite = self.favorite_edit.isChecked()
        self.data.tags = list(map(str.strip, self.tags_edit.text().split(","))) if self.tags_edit.text() != "" else []
        self.data.light = self.light_settings.get_settings() if not self.light_settings.get_settings().is_empty() else None

        new_name = self.name_edit.text()

        if self.new_cover_path is not None:
            update_mp3_cover(self.data.path, self.new_cover_path)
            self.data.clear_cover()
        # Update Summary
        update_mp3_data(self.data.path, self.data)

        # Update Name (Filename)
        if new_name != self.data.name:
            try:
                old_path = Path(self.data.path)
                new_filename = new_name
                if not new_filename.lower().endswith(".mp3"):
                    new_filename += ".mp3"

                new_path = old_path.with_name(new_filename)
                os.rename(old_path, new_path)

                self.data.path = Path(new_path)
                self.data.name = new_filename.removesuffix(".mp3").removesuffix(".MP3").removesuffix(".Mp3")

            except Exception as e:
                logger.error("Failed to rename file: {0}", e)
                QMessageBox.warning(self, _("Update Error"), _("Failed to rename file: {0}").format(e))

        super().accept()

class EditLightDialog(QDialog):

    def __init__(self,data: LightSetting, name:str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Edit Light"))
        self.resize(500, 250)

        self.light_setting = data

        layout = QFormLayout(self)

        self.name_edit = QLineEdit(name)
        layout.addRow(_("Name") + ":", self.name_edit)

        self.light_settings = LightSettingsWidget(settings = self.light_setting)
        self.light_settings.setDisabled(False)
        layout.addRow(_("Lights"), self.light_settings)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def accept(self, /):
        self.light_setting = self.light_settings.get_settings() if not self.light_settings.get_settings().is_empty() else None
        self.name = self.name_edit.text()

        super().accept()


class ImagePopup(QDialog):
    def __init__(self, title: str, image: QPixmap | os.PathLike[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(800, 600)

        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)

        # 2. Setup Fullscreen Shortcut (Press F11 or Esc)
        self.fs_shortcut = QShortcut(QKeySequence("F11"), self)
        self.fs_shortcut.activated.connect(self.toggle_fullscreen)

        self.esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.esc_shortcut.activated.connect(self.exit_fullscreen)

        # 1. Setup Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)

        # 2. Create Scroll Area (in case image is huge)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        # 3. Create Label to hold the image
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)

        # 4. Load and Set Image
        if isinstance(image, QPixmap):
            self.original_pixmap = image
        else:
            self.original_pixmap = QPixmap(image)

        if self.original_pixmap.isNull():
            self.image_label.setText(_("Failed to load image."))

        self.scroll_area.setWidget(self.image_label)

        self.scroll_area.setAutoFillBackground(True)
        self.scroll_area.setBackgroundRole(QPalette.ColorRole.Dark)
        layout.addWidget(self.scroll_area)

        self.update_image_size()

    def mouseDoubleClickEvent(self, event, /):
        self.toggle_fullscreen()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def exit_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.close()  # Standard behavior: Esc closes a dialog

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            # If the window is no longer active, close it
            if not self.isActiveWindow():
                self.close()
        super().changeEvent(event)

    def showEvent(self, event):
        """Called when the dialog is shown for the first time."""
        if not self.original_pixmap.isNull():
            self.update_image_size()
        super().showEvent(event)

    def resizeEvent(self, event):
        """This triggers every time the user drags the window corner."""
        if not self.original_pixmap.isNull():
            self.update_image_size()
        super().resizeEvent(event)

    def update_image_size(self):
        # Get the current size of the scroll area (the visible container)
        container_size = self.scroll_area.viewport().size()

        # Scale the original image to the container size
        scaled_pixmap = self.original_pixmap.scaled(
            container_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.image_label.setPixmap(scaled_pixmap)

class SettingsDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Settings"))
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        self.changed_keys = []

        self.tabs = QTabWidget()
        self.tabs.setContentsMargins(app_theme.margin_large)
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

        self.lights_tab = QWidget()
        self.init_lights_tab()
        self.tabs.addTab(self.lights_tab, _("Lights"))

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
        self.analyzer_layout.addRow(_("Voxalyzer BaseUrl"), self.voxalyzerUrl)

        self.local_voxalyzer = QCheckBox(_("Use Local Voxalyzer"))
        self.local_voxalyzer.setEnabled(os.path.isfile(get_executable_path("voxalyzer.exe")))
        self.local_voxalyzer.setChecked(has_local_voxalyzer() and AppSettings.value(SettingKeys.VOXALYZER_LOCAL, True, type=bool))
        self.local_voxalyzer.clicked.connect(self._local_voxalyzer_changed)
        self.analyzer_layout.addRow("", self.local_voxalyzer)

        self.voxalyzerUrl.setEnabled(not self.local_voxalyzer.isEnabled() or not self.local_voxalyzer.isChecked())

        #
        player_group = QGroupBox(_("Player"))
        self.player_layout = QFormLayout(player_group)

        self.normalize_volume = QCheckBox(_("Normalize Volume") + "*")
        self.normalize_volume.setToolTip(_("Requires restart"))
        self.normalize_volume.setChecked(AppSettings.value(SettingKeys.NORMALIZE_VOLUME, True, type=bool))
        self.player_layout.addRow("", self.normalize_volume)
        normalize_volume_description = QLabel(_("All songs will be played at a normalized volume."))
        normalize_volume_description.setProperty("cssClass", "small")
        normalize_volume_description.setContentsMargins(28, 0, 0, 0)
        self.player_layout.addRow("", normalize_volume_description)

        layout.addWidget(player_group, 0)
        #
        table_group = QGroupBox(_("Song Table"))
        table_layout = QFormLayout(table_group)

        layout.addWidget(table_group, 0)

        self.title_file_name_columns = QCheckBox(_("Use mp3 title instead of file name"))
        self.title_file_name_columns.setChecked(AppSettings.value(SettingKeys.SONGS_TITLE_INSTEAD_OF_FILE_NAME, False, type=bool))
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

        self.summary_column = QCheckBox(_("Display summary next to title"))
        self.summary_column.setChecked(AppSettings.value(SettingKeys.COLUMN_TITLE_SUMMARY_VISIBLE, True, type=bool))
        table_layout.addRow("", self.summary_column)

        self.debug_checkbox = QCheckBox(_("Debug"))
        self.debug_checkbox.setChecked(AppSettings.value(SettingKeys.DEBUG, False, type=bool))
        self.analyzer_layout.addRow("", self.debug_checkbox)

        layout.addStretch()

    def init_lights_tab(self):
        layout = QVBoxLayout(self.lights_tab)

        wiz_group = QGroupBox(_("Wiz Lights"))
        form_layout = QFormLayout(wiz_group)
        layout.addWidget(wiz_group, 0)

        layout.addLayout(form_layout, 0)

        self.lights_enabled = QCheckBox(_("Enabled"))
        self.lights_enabled.setChecked(AppSettings.value(SettingKeys.LIGHTS_WIDGET, True, type=bool))
        form_layout.addRow("", self.lights_enabled)

        ip = AppSettings.value(SettingKeys.LIGHTS_BROADCAST_IP, get_broadcast_ip(), type=str)

        self.lights_broadcast_ip = QLineEdit()
        self.lights_broadcast_ip.setPlaceholderText(get_broadcast_ip())
        self.lights_broadcast_ip.setText(ip)
        form_layout.addRow(_("Broadcast Space"), self.lights_broadcast_ip)
        lights_broadcast_ip_description = QLabel(_("Take the ip address of you local wlan network and replace the last number with 255."))
        lights_broadcast_ip_description.setProperty("cssClass", "small")
        lights_broadcast_ip_description.setContentsMargins(0, 0, 0, 0)
        form_layout.addRow("", lights_broadcast_ip_description)

        self.lights_broadcast_timeout = QLineEdit()
        self.lights_broadcast_timeout.setText(AppSettings.value(SettingKeys.LIGHTS_TIMEOUT, "5", type=str))
        self.lights_broadcast_timeout.setToolTip(_("Time to search for bulbs in seconds"))
        form_layout.addRow(_("Timeout"), self.lights_broadcast_timeout)

        layout.addStretch(1)

    def _local_voxalyzer_changed(self, checked: bool = False):
        self.voxalyzerUrl.setEnabled(not checked)

    def init_categories_tab(self):

        groups = set()
        for cat in get_music_categories():
            if cat.group is not None and cat.group != "":
                groups.add(cat.group)

        layout = QVBoxLayout(self.categories_tab)
        self.categories_table = QTableWidget()
        self.categories_table.setItemDelegate(SettingsTableDelegate(groups))
        self.categories_table.setColumnCount(5)
        self.categories_table.setHorizontalHeaderLabels([_("Key"), _("Name"), _("Group"), _("Description"), _("Levels (json)")])
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

    def _set_settings_value(self, key: SettingKeys, type: object | None, value: object):
        original_value = AppSettings.value(key, type=type)

        if value is None:
            AppSettings.remove(key)
        else:
            AppSettings.setValue(key, value)

        if original_value != value:
            self.changed_keys.append(key)

        return original_value != value

    def exec(self, /):
        self.changed_keys.clear()
        return super().exec()

    def has_changed(self, *keys: SettingKeys) -> bool:
        for key in keys:
            if key in self.changed_keys:
                return True

        return False

    def accept(self):
        requires_restart = self.requires_restart()

        self._set_settings_value(SettingKeys.SONGS_TITLE_INSTEAD_OF_FILE_NAME, bool, self.title_file_name_columns.isChecked())
        self._set_settings_value(SettingKeys.DYNAMIC_TABLE_COLUMNS, bool, self.dynamic_table_columns.isChecked())
        self._set_settings_value(SettingKeys.DYNAMIC_SCORE_COLUMN, bool, self.dynamic_score_column.isChecked())
        self._set_settings_value(SettingKeys.COLUMN_TITLE_SUMMARY_VISIBLE, bool, self.summary_column.isChecked())
        self._set_settings_value(SettingKeys.LOCALE, str, self.locale_combo.currentData())
        self._set_settings_value(SettingKeys.DEBUG, bool, self.debug_checkbox.isChecked())
        self._set_settings_value(SettingKeys.VOXALYZER_LOCAL, bool, self.local_voxalyzer.isChecked())
        if self.voxalyzerUrl.text() == '' or self.voxalyzerUrl.text() is None:
            self._set_settings_value(SettingKeys.VOXALYZER_URL, str, None)
        else:
            self._set_settings_value(SettingKeys.VOXALYZER_URL, str, self.voxalyzerUrl.text())

        self._set_settings_value(SettingKeys.NORMALIZE_VOLUME, bool, self.normalize_volume.isChecked())

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
                    _categories.append(MusicCategory(cat_name, cat_desc, cat_levels, group=cat_group, key=cat_key))
        set_music_categories(_categories)

        # Lights
        self._set_settings_value(SettingKeys.LIGHTS_BROADCAST_IP, str, self.lights_broadcast_ip.text())
        self._set_settings_value(SettingKeys.LIGHTS_TIMEOUT, int, int(self.lights_broadcast_timeout.text()))
        self._set_settings_value(SettingKeys.LIGHTS_WIDGET, bool, self.lights_enabled.isChecked())

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
