import logging
import os
from pathlib import Path

from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QApplication, QDialogButtonBox, QLineEdit, QSpinBox, \
    QTextEdit, QCheckBox, QFormLayout, QMessageBox, QColorDialog

from config.theme import app_theme
from config.utils import get_path, is_latest_version, get_latest_version, DOWNLOAD_LINK
from logic.mp3 import Mp3Entry, update_mp3_data

logger = logging.getLogger("main")

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
        layout.addRow(_("Genre") + ":", self.genre_edit)

        self.bpm_edit = QSpinBox()
        self.bpm_edit.setRange(0,200)
        self.bpm_edit.setSpecialValueText("")
        if data.bpm:
            self.bpm_edit.setValue(data.bpm)
        layout.addRow(_("BPM") + ":", self.bpm_edit)

        self.tags_edit = QLineEdit(", ".join(data.tags))
        layout.addRow(_("Tags") + ":", self.tags_edit)

        self.summary_edit = QTextEdit()
        if data.summary:
            self.summary_edit.setPlainText(data.summary)
        layout.addRow(_("Summary") + ":", self.summary_edit)

        self.favorite_edit = QCheckBox(_("Favorite"))
        self.favorite_edit.setChecked(data.favorite)

        layout.addRow("", self.favorite_edit)

        self.color_edit = ColorButton()
        self.color_edit.setMaximumWidth(64)
        self.color_edit.setColor(self.data.color)
        layout.addRow(_("Color"), self.color_edit)

        file_name = QLabel(os.path.abspath(data.path))
        file_name.setWordWrap(True)
        file_name.setStyleSheet(f"font-size:{app_theme.font_size_small}pt;")
        layout.addRow(_("File") + ":", file_name)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def accept(self, /):

        self.data.title = self.title_edit.text()
        self.data.artist = self.artist_edit.text()
        self.data.album = self.album_edit.text()
        self.data.bpm = self.bpm_edit.value() if self.bpm_edit.value() > 0 else None
        self.data.genres = list(map(str.strip, self.genre_edit.text().split(","))) if self.genre_edit.text() != "" else []
        self.data.summary = self.summary_edit.toPlainText()
        self.data.favorite = self.favorite_edit.isChecked()
        self.data.tags = list(map(str.strip, self.tags_edit.text().split(","))) if self.tags_edit.text() != "" else []
        self.data.color =self.color_edit.color()

        new_name = self.name_edit.text()

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




class ColorButton(QtWidgets.QPushButton):
    '''
    Custom Qt Widget to show a chosen color.

    Left-clicking the button shows the color-chooser, while
    right-clicking resets the color to None (no-color).
    '''
    colorChanged = Signal(object)

    def __init__(self, *args, color: QColor=None, **kwargs):
        super().__init__(*args, **kwargs)

        self._color: QColor = None
        self._default: QColor = color
        self.pressed.connect(self.onColorPicker)

        # Set the initial/default state.
        self.setColor(self._default)

    def setColor(self, color: QColor):
        if color != self._color:
            self._color = color
            self.colorChanged.emit(color)

        if self._color:
            self.setStyleSheet("background-color: %s;" % self._color.name())
        else:
            self.setStyleSheet("")

    def color(self):
        return self._color

    def onColorPicker(self):
        '''
        Show color-picker dialog to select color.

        Qt will use the native dialog by default.

        '''
        dlg = QColorDialog()
        if self._color:
            dlg.setCurrentColor(self._color)

        if dlg.exec_():
            self.setColor(dlg.currentColor())

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.setColor(self._default)

        return super().mousePressEvent(e)