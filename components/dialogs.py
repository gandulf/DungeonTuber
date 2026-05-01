import logging
import os
from pathlib import Path

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QPixmap, QIcon, QShortcut, QKeySequence, QPalette
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QApplication, QDialogButtonBox, QLineEdit, QSpinBox, \
    QTextEdit, QCheckBox, QFormLayout, QMessageBox, QFileDialog, QPushButton, QScrollArea

from config.theme import app_theme
from config.utils import get_path, is_latest_version, get_latest_version, DOWNLOAD_LINK
from lights import LightSettingsWidget
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
        file_name.setFont(app_theme.font_small())
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