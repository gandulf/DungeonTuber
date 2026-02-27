# Compilation mode, standalone everywhere, except on macOS there app bundle
# nuitka-project-if: {OS} in ("Windows", "Linux", "FreeBSD"):
#    nuitka-project: --mode=standalone
#    nuitka-project: --windows-console-mode=disable
#    nuitka-project: --windows-icon-from-ico={MAIN_DIRECTORY}/docs/icon.ico
# nuitka-project-else:
#    nuitka-project: --mode=standalone
#    nuitka-project: --macos-create-app-bundle
#
# nuitka-project: --enable-plugin=pyside6
# nuitka-project: --include-data-files={MAIN_DIRECTORY}/docs/icon.ico=docs/icon.ico
# nuitka-project: --include-data-files={MAIN_DIRECTORY}/docs/splash.png=docs/splash.png
# nuitka-project: --include-data-dir={MAIN_DIRECTORY}/assets=assets
# nuitka-project: --include-data-dir={MAIN_DIRECTORY}/locales=locales
# nuitka-project: --mingw64
# nuitka-project: --output-dir=dist

import functools
import importlib
import json
import locale
import logging
import os
import sys
import traceback

from config import log

log.setup_logging()

import gettext
from pathlib import Path
from os import PathLike

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, QFileDialog, QMessageBox, QMenu, QStatusBar, QProgressBar, QSplitter
from PySide6.QtCore import Qt, QSize, QPersistentModelIndex, QTimer, QKeyCombination, QPoint, QFileInfo, QEvent
from PySide6.QtGui import QAction, QIcon, QActionGroup, QResizeEvent

from config.settings import AppSettings, SettingKeys, SettingsDialog, Preset, MusicCategory, set_music_categories, set_presets
from config.theme import app_theme
from config.utils import get_path, get_latest_version, is_latest_version, get_current_version, is_frozen

from components.effects import EffectList, EffectWidget
from components.widgets import FeatureOverlay
from components.player import PlayerWidget
from components.dialogs import AboutDialog, EditSongDialog
from components.filter import FilterWidget
from components.songs import SongTable
from components.files import DirectoryWidget

from logic.mp3 import Mp3Entry, parse_mp3, create_m3u, get_m3u_paths, save_playlist
from logic.analyzer import Analyzer

logger = logging.getLogger(__file__)

class MusicPlayer(QMainWindow):

    toggle_directory_tree_action: QAction
    toggle_effects_tree_action: QAction

    light_theme_action: QAction
    dark_theme_action: QAction

    table_tabs: QTabWidget = None
    old_table: SongTable | None = None

    def __init__(self, application: QApplication):
        super().__init__()

        icon_path = get_path("docs/icon.ico")
        if icon_path is not None and os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setWindowTitle(application.applicationName() + " " + application.applicationVersion())

        window_size = AppSettings.value(SettingKeys.WINDOW_SIZE, type=QSize, defaultValue=None)
        if window_size:
            self.resize(window_size)
        else:
            self.resize(1200, 700)

        self.load_settings()

        self.analyzer = Analyzer.get_analyzer()

        self.init_ui()
        self.load_initial_directory()

        self.check_newer_version()

        if AppSettings.value(SettingKeys.START_TOUR, True, type=bool):
            QTimer.singleShot(500, lambda: self.start_tour())

    def load_settings(self):
        # Load custom categories and tags
        try:
            custom_categories = AppSettings.value(SettingKeys.CATEGORIES)
            if custom_categories:
                list_of_custom_categories = json.loads(custom_categories)
                set_music_categories([MusicCategory(**d) for d in list_of_custom_categories])
        except Exception as e:
            AppSettings.remove(SettingKeys.CATEGORIES)
            logger.error("Failed to load custom categories: {0}", e)

        try:
            custom_presets = AppSettings.value(SettingKeys.PRESETS)
            if custom_presets:
                list_of_custom_presets = json.loads(custom_presets)
                set_presets([Preset(**d) for d in list_of_custom_presets])
        except Exception as e:
            AppSettings.remove(SettingKeys.PRESETS)
            logger.error("Failed to load custom presets: {0}", e)

    def check_newer_version(self):
        if not is_latest_version() and is_frozen():
            version_text = _("Newer version available {0}").format(get_latest_version())
            self.statusBar().showMessage(version_text)

    def exit(self):
        sys.exit(0)

    def config_simple_mode(self):
        self.toggle_directory_tree_action.setChecked(True)
        self.toggle_effects_tree_action.setChecked(False)

        self.presets_action.setChecked(False)
        self.tags_action.setChecked(True)
        self.genres_action.setChecked(True)
        self.russel_action.setChecked(False)
        self.bpm_action.setChecked(False)
        self.categories_action.setChecked(False)

    def config_complex_mode(self):
        self.toggle_directory_tree_action.setChecked(True)
        self.toggle_effects_tree_action.setChecked(True)

        self.presets_action.setChecked(True)
        self.tags_action.setChecked(True)
        self.genres_action.setChecked(True)
        self.russel_action.setChecked(True)
        self.bpm_action.setChecked(True)
        self.categories_action.setChecked(True)

    def init_main_menu(self):

        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu(_("File"))
        file_menu.setContentsMargins(0, 0, 0, 0)

        open_dir_action = QAction(_("Open Directory"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen))
        open_dir_action.triggered.connect(self.pick_load_directory)
        file_menu.addAction(open_dir_action)

        open_playlist_action = QAction(_("Open Playlist"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.DocumentOpen))
        open_playlist_action.triggered.connect(self.pick_load_playlist)
        file_menu.addAction(open_playlist_action)

        save_favorites_action = QAction(_("Save Favorites"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.DocumentSave))
        save_favorites_action.triggered.connect(self.pick_save_playlist)
        file_menu.addAction(save_favorites_action)

        file_menu.addSeparator()

        self.analyze_file_action = QAction(_("Analyze File"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.Scanner))
        self.analyze_file_action.triggered.connect(self.pick_analyze_file)
        self.analyze_file_action.setVisible(AppSettings.value(SettingKeys.VOXALYZER_URL, "", type=str) != "")
        file_menu.addAction(self.analyze_file_action)

        file_menu.addSeparator()

        settings_action = QAction(_("Settings"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.DocumentProperties))
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()

        exit_action = QAction(_("Exit"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.ApplicationExit))
        exit_action.triggered.connect(self.exit)
        file_menu.addAction(exit_action)

        view_menu = menu_bar.addMenu(_("View"))

        filter_menu = QMenu(_("Filter"), self, icon=QIcon.fromTheme("filter"))
        view_menu.addMenu(filter_menu)

        config_simple_action = QAction(_("Simple Mode"), self, icon=QIcon.fromTheme("filter"))
        config_simple_action.triggered.connect(self.config_simple_mode)
        filter_menu.addAction(config_simple_action)

        config_complex_action = QAction(_("Complex Mode"), self, icon=QIcon.fromTheme("filter"))
        config_complex_action.triggered.connect(self.config_complex_mode)
        filter_menu.addAction(config_complex_action)

        filter_menu.addSeparator()

        self.presets_action = QAction(_("Presets"), self, icon=QIcon.fromTheme("russel"))
        self.presets_action.setCheckable(True)
        self.presets_action.setChecked(AppSettings.value(SettingKeys.PRESET_WIDGETS, True, type=bool))
        self.presets_action.changed.connect(self.filter_widget.toggle_presets)
        filter_menu.addAction(self.presets_action)

        self.russel_action = QAction(_("Circumplex model of emotion"), self, icon=QIcon.fromTheme("russel"))
        self.russel_action.setCheckable(True)
        self.russel_action.setChecked(AppSettings.value(SettingKeys.RUSSEL_WIDGET, True, type=bool))
        self.russel_action.changed.connect(self.filter_widget.toggle_russel_widget)
        filter_menu.addAction(self.russel_action)

        self.categories_action = QAction(_("Category Sliders"), self, icon=QIcon.fromTheme("filter"))
        self.categories_action.setCheckable(True)
        self.categories_action.setChecked(AppSettings.value(SettingKeys.CATEGORY_WIDGETS, True, type=bool))
        self.categories_action.changed.connect(self.filter_widget.toggle_category_widgets)
        filter_menu.addAction(self.categories_action)

        self.bpm_action = QAction(_("Beats per Minute"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical))
        self.bpm_action.setCheckable(True)
        self.bpm_action.setChecked(AppSettings.value(SettingKeys.BPM_WIDGET, True, type=bool))
        self.bpm_action.changed.connect(self.filter_widget.toggle_bpm_widget)
        filter_menu.addAction(self.bpm_action)

        self.tags_action = QAction(_("Tags"), self, icon=QIcon.fromTheme("tags"))
        self.tags_action.setCheckable(True)
        self.tags_action.setChecked(AppSettings.value(SettingKeys.TAGS_WIDGET, True, type=bool))
        self.tags_action.changed.connect(self.filter_widget.toggle_tags_widget)
        filter_menu.addAction(self.tags_action)

        self.genres_action = QAction(_("Genres"), self, icon=QIcon.fromTheme("tags"))
        self.genres_action.setCheckable(True)
        self.genres_action.setChecked(AppSettings.value(SettingKeys.GENRES_WIDGET, True, type=bool))
        self.genres_action.changed.connect(self.filter_widget.toggle_genres_widget)
        filter_menu.addAction(self.genres_action)

        self.toggle_directory_tree_action = QAction(_("Directory Tree"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.FolderOpen))
        self.toggle_directory_tree_action.setCheckable(True)
        self.toggle_directory_tree_action.setChecked(AppSettings.value(SettingKeys.DIRECTORY_TREE, True, type=bool))
        self.toggle_directory_tree_action.changed.connect(self.toggle_directory_tree)
        view_menu.addAction(self.toggle_directory_tree_action)

        self.toggle_effects_tree_action = QAction(_("Effects Tree"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.AudioCard))
        self.toggle_effects_tree_action.setCheckable(True)
        self.toggle_effects_tree_action.setChecked(AppSettings.value(SettingKeys.EFFECTS_TREE, True, type=bool))
        self.toggle_effects_tree_action.changed.connect(self.toggle_effects_tree)
        view_menu.addAction(self.toggle_effects_tree_action)

        view_menu.addSeparator()

        font_size_small_action = QAction(_("Smaller"), self)
        font_size_small_action.setShortcut(QKeyCombination(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_Minus))
        font_size_small_action.triggered.connect(lambda: setattr(app_theme, 'font_size', app_theme.font_size - 1.0))

        font_size_medium_action = QAction(_("Medium"), self)
        font_size_medium_action.setShortcut(QKeyCombination(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_0))
        font_size_medium_action.triggered.connect(lambda: setattr(app_theme, 'font_size', 10.5))

        font_size_large_action = QAction(_("Larger"), self)
        font_size_large_action.setShortcut(QKeyCombination(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_Plus))
        font_size_large_action.triggered.connect(lambda: setattr(app_theme, 'font_size', app_theme.font_size + 1.0))

        font_size_group = QActionGroup(self, exclusionPolicy=QActionGroup.ExclusionPolicy.Exclusive)
        font_size_group.addAction(font_size_small_action)
        font_size_group.addAction(font_size_medium_action)
        font_size_group.addAction(font_size_large_action)

        font_size_menu = QMenu(_("Font Size"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.FormatTextBold))

        font_size_menu.addAction(font_size_small_action)
        font_size_menu.addAction(font_size_medium_action)
        font_size_menu.addAction(font_size_large_action)
        view_menu.addMenu(font_size_menu)

        visualizer_menu = QMenu(_("Visualizer"), self, icon=QIcon.fromTheme("spectrum"))

        visualizer_group = QActionGroup(self, exclusionPolicy=QActionGroup.ExclusionPolicy.Exclusive)

        vis_vlc_action = QAction(_("VLC Spectrum"), self)
        vis_vlc_action.setCheckable(True)
        vis_vlc_action.triggered.connect(self.set_visualizer_vlc)

        vis_fake_action = QAction(_("Fake"), self)
        vis_fake_action.setCheckable(True)
        vis_fake_action.triggered.connect(self.set_visualizer_fake)

        vis_none_action = QAction(_("None"), self)
        vis_none_action.setCheckable(True)
        vis_none_action.triggered.connect(self.set_visualizer_none)

        visualizer_group.addAction(vis_vlc_action)

        visualizer_group.addAction(vis_fake_action)
        visualizer_group.addAction(vis_none_action)

        vis = AppSettings.value(SettingKeys.VISUALIZER, "NONE", type=str)
        if vis == "FAKE":
            vis_fake_action.setChecked(True)
        elif vis == "VLC":
            vis_vlc_action.setChecked(True)
        else:
            vis_none_action.setChecked(True)

        visualizer_menu.addAction(vis_vlc_action)
        visualizer_menu.addAction(vis_fake_action)
        visualizer_menu.addAction(vis_none_action)

        view_menu.addMenu(visualizer_menu)

        theme_menu = QMenu(_("Theme"), self, icon=QIcon.fromTheme("theme"))

        theme_group = QActionGroup(self, exclusionPolicy=QActionGroup.ExclusionPolicy.Exclusive)

        self.light_theme_action = QAction(_("Light"), self)
        self.light_theme_action.triggered.connect(self.set_light_theme)
        self.light_theme_action.setCheckable(True)

        self.dark_theme_action = QAction(_("Dark"), self)
        self.dark_theme_action.triggered.connect(self.set_dark_theme)
        self.dark_theme_action.setCheckable(True)
        if app_theme.theme() == "LIGHT":
            self.light_theme_action.setChecked(True)
        else:
            self.dark_theme_action.setChecked(True)

        theme_group.addAction(self.light_theme_action)
        theme_group.addAction(self.dark_theme_action)

        theme_menu.addActions(theme_group.actions())

        view_menu.addMenu(theme_menu)

        # Help Menu
        help_menu = menu_bar.addMenu(_("Help"))

        tour_action = QAction(_("Show Tour"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.HelpFaq))
        tour_action.triggered.connect(self.start_tour)
        help_menu.addAction(tour_action)

        about_action = QAction(_("About"), self, icon=QIcon.fromTheme(QIcon.ThemeIcon.HelpAbout))
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def changeEvent(self, event, /):
        if event.type() == QEvent.Type.ApplicationFontChange or event.type() == QEvent.Type.FontChange:
            self.table_tabs.setIconSize(app_theme.icon_size)

            # for btn in [self.btn_prev, self.btn_play, self.btn_next, self.slider_vol.btn_volume, self.btn_repeat]:

    def _get_first_slider(self):
        if len(self.filter_widget.sliders.values()) > 0:
            return next(iter(self.filter_widget.sliders.values())).slider
        else:
            return None

    def start_tour(self):
        steps = [
            {"widget": self.directory_widget, 'message': _("Tour Directory Tree")},
            {'widget': self.filter_widget.russel_widget, 'message': _("Tour Russel Widget")},
            {'widget': self._get_first_slider(), 'message': _("Tour Category Slider")},
            {'widget': self.filter_widget.bpm_widget, 'message': _("Tour BPM Widget")},
            {'widget': self.filter_widget.tags_genres_widget, 'message': _("Tour Tags Widget")},
            {'widget': self.filter_widget.presets_widget, 'message': _("Tour Presets Widget")},
            {'widget': self.table_tabs, 'message': _("Tour Song Table")},
            {'widget': self.effects_widget, 'message': _("Tour Effectslist")},
            {'widget': self.menuBar(), 'message': _("Tour Menubar")}
        ]
        self.overlay = FeatureOverlay(self, steps)
        AppSettings.setValue(SettingKeys.START_TOUR, False)

    def show_about_dialog(self):
        dialog = AboutDialog(self)
        dialog.exec()

    def set_light_theme(self):
        self.light_theme_action.setChecked(True)

        app_theme.set_theme("LIGHT")

    def set_dark_theme(self):
        self.dark_theme_action.setChecked(True)

        app_theme.set_theme("DARK")

    def set_visualizer_vlc(self):
        AppSettings.setValue(SettingKeys.VISUALIZER, "VLC")
        self.player.refresh_visualizer()

    def set_visualizer_fake(self):
        AppSettings.setValue(SettingKeys.VISUALIZER, "FAKE")
        self.player.refresh_visualizer()

    def set_visualizer_real(self):
        AppSettings.setValue(SettingKeys.VISUALIZER, "REAL")
        self.player.refresh_visualizer()

    def set_visualizer_none(self):
        AppSettings.setValue(SettingKeys.VISUALIZER, "NONE")
        self.player.refresh_visualizer()

    def toggle_directory_tree(self, visible: bool = None):

        if visible is None:
            visible = not AppSettings.value(SettingKeys.DIRECTORY_TREE, True, type=bool)

        if visible:
            sizes = self.central_splitter.sizes()
            sizes[1] = sizes[1] - 200
            sizes[0] = 200
            self.central_splitter.setSizes(sizes)
            AppSettings.setValue(SettingKeys.DIRECTORY_TREE, True)
            self.directory_widget.setEnabled(True)
        else:
            sizes = self.central_splitter.sizes()
            sizes[1] = sizes[1] + sizes[0]
            sizes[0] = 0
            self.central_splitter.setSizes(sizes)
            AppSettings.setValue(SettingKeys.DIRECTORY_TREE, False)
            self.directory_widget.setEnabled(False)

    def toggle_effects_tree(self, visible: bool = None):

        if visible is None:
            visible = not AppSettings.value(SettingKeys.EFFECTS_TREE, True, type=bool)

        if visible:
            sizes = self.central_splitter.sizes()
            sizes[1] = sizes[1] - 200
            sizes[2] = 200
            self.central_splitter.setSizes(sizes)
            AppSettings.setValue(SettingKeys.EFFECTS_TREE, True)
            self.effects_widget.setEnabled(True)
        else:
            sizes = self.central_splitter.sizes()
            sizes[1] = sizes[1] + sizes[2]
            sizes[2] = 0
            self.central_splitter.setSizes(sizes)
            AppSettings.setValue(SettingKeys.EFFECTS_TREE, False)
            self.effects_widget.setEnabled(False)

    def open_settings(self):

        dialog = SettingsDialog(self)
        if dialog.exec():
            self.filter_widget.update_sliders(self.get_available_categories())
            if self.current_table() is not None:
                self.current_table().update_category_column_visibility()

            self.analyze_file_action.setVisible(AppSettings.value(SettingKeys.VOXALYZER_URL, "", type=str) != "")

    def on_layout_splitter_moved(self, pos_x: int, index: int):
        if index == 1:
            if pos_x == 0:
                self.toggle_directory_tree_action.setChecked(False)
                self.directory_widget.setEnabled(False)
            else:
                self.toggle_directory_tree_action.setChecked(True)
                self.directory_widget.setEnabled(True)
        else:
            if pos_x + self.central_splitter.handleWidth() >= self.width():
                self.toggle_effects_tree_action.setChecked(False)
                self.effects_widget.setEnabled(False)
            else:
                self.toggle_effects_tree_action.setChecked(True)
                self.effects_widget.setEnabled(True)

    def tree_open_file(self, file_info: QFileInfo):
        if file_info.isDir():
            self.load_directory(file_info.filePath(), activate=True)
        elif file_info.suffix().lower() == "m3u":
            self.load_playlist(file_info.filePath(), activate=True)
        else:
            entry = parse_mp3(Path(file_info.filePath()))
            self.player.play_track(QPersistentModelIndex(), entry)

    def analyze_files(self, datas: list[Mp3Entry]):
        for data in datas:
            self.analyzer.process(data.path)

    def edit_song(self, datas: list[Mp3Entry]):
        dialog = EditSongDialog(datas[0], self)
        if dialog.exec():
            table: SongTable = self.current_table()
            if table is not None:
                index = table.index_of(datas[0])
                if index.isValid():
                    table.model().setData(index, datas[0], Qt.ItemDataRole.UserRole)
                    table.update()
            list: EffectList = self.effects_widget.list_widget
            if list is not None:
                index = list.index_of(datas[0])
                if index.isValid():
                    list.model().setData(index, datas[0], Qt.ItemDataRole.UserRole)
                    list.update()

    def populate_mp3_entry_context_menu(self, menu: QMenu, datas: list[Mp3Entry]):
        if len(datas) > 0:
            edit_name_action = menu.addAction(QIcon.fromTheme(QIcon.ThemeIcon.EditPaste), _("Edit Song"))
            edit_name_action.triggered.connect(functools.partial(self.edit_song, datas))

            if AppSettings.value(SettingKeys.VOXALYZER_URL, "", type=str) != "":
                analyze_action = menu.addAction(QIcon.fromTheme(QIcon.ThemeIcon.Scanner), _("Analyze"))
                analyze_action.triggered.connect(functools.partial(self.analyze_files, datas))

            menu.addSeparator()

    def populate_playlist_context_menu(self, menu: QMenu, datas: list[Mp3Entry]):
        if len(datas) > 0:
            add_to_playlist = QMenu(_("Add to playlist"), icon=QIcon.fromTheme(QIcon.ThemeIcon.ListAdd))
            add_new_action = add_to_playlist.addAction(_("<New Playlist>"))
            add_new_action.setIcon(QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical))
            add_new_action.triggered.connect(functools.partial(self.pick_new_playlist, datas))
            for playlist in self.get_playlists():
                add_action = add_to_playlist.addAction(QFileInfo(playlist).baseName())
                add_action.setIcon(QIcon.fromTheme(QIcon.ThemeIcon.MediaOptical))
                add_action.triggered.connect(functools.partial(self.add_to_playlist, playlist, datas))

            menu.addMenu(add_to_playlist)

    def init_ui(self):

        self.player = PlayerWidget()
        self.player.track_changed.connect(self.play_track)

        self.central_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.central_splitter.splitterMoved.connect(self.on_layout_splitter_moved)
        self.setCentralWidget(self.central_splitter)

        self.directory_widget = DirectoryWidget()
        self.directory_widget.directory_tree.file_opened.connect(self.tree_open_file)
        self.directory_widget.directory_tree.file_analyzed.connect(self.analyzer.process)
        self.directory_widget.directory_tree.open_context_menu.connect(self.populate_mp3_entry_context_menu)
        self.directory_widget.directory_tree.open_context_menu.connect(self.populate_playlist_context_menu)
        self.central_splitter.addWidget(self.directory_widget)
        self.central_splitter.setCollapsible(0, True)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setObjectName("main_layout")
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.central_splitter.addWidget(main_widget)
        self.central_splitter.setCollapsible(1, False)

        self.effects_widget = EffectWidget()
        self.effects_widget.list_widget.open_context_menu.connect(self.populate_mp3_entry_context_menu)
        self.effects_widget.list_widget.open_context_menu.connect(self.populate_playlist_context_menu)

        self.central_splitter.addWidget(self.effects_widget)
        self.central_splitter.setCollapsible(2, True)

        # Menu Bar
        self.filter_widget = FilterWidget(self)
        main_layout.addWidget(self.filter_widget)

        main_layout.addWidget(self.player, 0)

        self.toggle_directory_tree(AppSettings.value(SettingKeys.DIRECTORY_TREE, True, type=bool))
        self.toggle_effects_tree(AppSettings.value(SettingKeys.EFFECTS_TREE, True, type=bool))
        # -------------------------------------

        # Table Widget for Playlist

        self.table_tabs = QTabWidget()
        self.table_tabs.tabBar().setMovable(True)
        self.table_tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_tabs.tabBar().customContextMenuRequested.connect(self.show_tabs_context_menu)
        self.table_tabs.tabBar().setAutoHide(True)
        self.table_tabs.setTabsClosable(True)
        self.table_tabs.currentChanged.connect(self.on_table_tab_changed)
        self.table_tabs.tabCloseRequested.connect(self.on_table_tab_close)
        self.table_tabs.tabBar().tabMoved.connect(self.on_table_tab_moved)

        main_layout.addWidget(self.table_tabs, 2)

        self.setStatusBar(QStatusBar())
        self.statusBar().messageChanged.connect(self.update_status_message)

        self.status_progress = QProgressBar()
        self.status_progress.setContentsMargins(0, 0, 0, 0)
        self.status_progress.setRange(0, 0)
        self.statusBar().addPermanentWidget(self.status_progress)

        self.statusBar().setVisible(False)

        self.analyzer.progress.connect(self.update_status_label)
        self.analyzer.error.connect(self.update_status_label)
        self.analyzer.result.connect(self.update_table_entry)

        self.init_main_menu()

    def resizeEvent(self, event: QResizeEvent):
        AppSettings.setValue(SettingKeys.WINDOW_SIZE, event.size())

    def update_table_entry(self, path: PathLike[str]):
        self.current_table().refresh_item(path)

    def show_tabs_context_menu(self, position: QPoint):
        # 4. Identify which tab was clicked
        tab_index = self.table_tabs.tabBar().tabAt(position)

        if tab_index == -1:
            return  # Right-click happened on empty space of the tab bar

        # Create the menu
        menu = QMenu(self)

        refresh_action = QAction(_("Refresh"), icon=QIcon.fromTheme(QIcon.ThemeIcon.ViewRefresh))
        refresh_action.setData(tab_index)
        refresh_action.triggered.connect(self.reload_table)
        menu.addAction(refresh_action)

        close_tables_action = QAction(_("Close All"), icon=QIcon.fromTheme(QIcon.ThemeIcon.WindowClose))
        close_tables_action.triggered.connect(self.close_tables)
        menu.addAction(close_tables_action)

        menu.exec(self.table_tabs.tabBar().mapToGlobal(position))

    def update_status_message(self, msg: str):
        if msg is None or msg == "":
            self.statusBar().setVisible(False)
        else:
            self.statusBar().setVisible(True)

    def update_status_label(self, msg: str, progress: bool = True):
        if msg is not None:
            self.statusBar().setVisible(True)
            self.statusBar().showMessage(msg, 5000)
            self.status_progress.setVisible(progress)

    def add_table_tab(self, file_path: PathLike[str] = None, lazy: bool = False, activate: bool = True):
        if os.path.isfile(file_path):
            mp3_files = get_m3u_paths(file_path)
        elif os.path.isdir(file_path):
            mp3_files = list(Path(file_path).rglob("*.mp3"))
        else:
            QMessageBox.warning("Invalid File Path")
            return None

        table = SongTable(self, file_path, mp3_files, lazy=lazy)
        index = self.table_tabs.addTab(table, table.get_icon(), table.get_name())

        if activate:
            self.table_tabs.setCurrentIndex(index)

        return table

    def attach_song_table(self, table: SongTable):
        table.item_double_clicked.connect(self.play_track)
        table.content_changed.connect(self.on_table_content_changed)
        table.open_context_menu.connect(self.populate_mp3_entry_context_menu)
        table.open_context_menu.connect(self.populate_playlist_context_menu)
        table.files_opened.connect(self.files_opened)
        table.file_analyzed.connect(self.analyzer.process)

    def detach_song_table(self, table: SongTable):
        try:
            table.item_double_clicked.disconnect(self.play_track)
            table.content_changed.disconnect(self.on_table_content_changed)
            table.open_context_menu.disconnect(self.populate_mp3_entry_context_menu)
            table.open_context_menu.disconnect(self.populate_playlist_context_menu)
            table.files_opened.disconnect(self.files_opened)
            table.file_analyzed.disconnect(self.analyzer.process)
        except Exception:
            # in case of duplicate calls this throws an error if nothing is attached
            pass
        except RuntimeWarning:
            # in case of duplicate calls this throws an error if nothing is attached
            pass

    def on_table_content_changed(self, table: SongTable = None):
        if table is None:
            table = self.sender()

        if table == self.current_table():
            self.player.set_enabled(table.rowCount() > 0)
            self.filter_widget.attach_song_table(table)

    def on_table_tab_changed(self, index: int):
        if self.old_table:
            self.detach_song_table(self.old_table)

        table: SongTable = self.table_tabs.widget(index)

        if table:
            self.old_table = table
            self.attach_song_table(table)
            if not table.is_loaded:
                table.start_lazy_loading()

            table.update_category_column_visibility()
            self.filter_widget.attach_song_table(table)
            self.player.set_enabled(table.rowCount() > 0)
        else:
            self.old_table = None
            self.filter_widget.attach_song_table(None)
            self.player.set_enabled(False)

    def on_table_tab_close(self, index: int):
        table: SongTable = self.table_tabs.widget(index)
        if table:
            self.detach_song_table(table)
            if self.old_table == table:
                self.old_table = None

        self.table_tabs.removeTab(index)
        self.table_tabs.tabBar().setVisible(self.table_tabs.count() > 1)

        AppSettings.setValue(SettingKeys.OPEN_TABLES, self.get_open_tables())

    def on_table_tab_moved(self, fromIndex: int, toIndex: int):
        AppSettings.setValue(SettingKeys.OPEN_TABLES, self.get_open_tables())

    def pick_analyze_file(self):
        file_path, ignore = QFileDialog.getOpenFileName(self, _("Select File to Analyze"),
                                                        dir=self._get_default_directory(),
                                                        filter=_("Mp3 (*.mp3 *.MP3);;All (*)"))
        if file_path:
            self.analyzer.process(file_path)

    def _get_default_directory(self) -> str:
        if AppSettings.value(SettingKeys.ROOT_DIRECTORY):
            return str(AppSettings.value(SettingKeys.ROOT_DIRECTORY))
        elif AppSettings.value(SettingKeys.LAST_DIRECTORY):
            return str(AppSettings.value(SettingKeys.LAST_DIRECTORY))
        else:
            return os.path.abspath(Path.home())

    def pick_load_playlist(self):
        file_path, ignore = QFileDialog.getOpenFileName(self, _("Select Playlist to Load"),
                                                        dir=self._get_default_directory(),
                                                        filter=_("Playlist (*.m3u *.M3U);;All (*)"))
        if file_path:
            self.load_playlist(file_path)

    def pick_new_playlist(self, entries: list[Mp3Entry]):
        new_play_list = self.pick_save_playlist(entries)

        if new_play_list is not None:
            self.load_playlist(new_play_list)

    def pick_save_playlist(self, entries: list[Mp3Entry]):
        file_path, ignore = QFileDialog.getSaveFileName(self, _("Select Playlist to Save"),
                                                        dir=self._get_default_directory(),
                                                        filter=_("Playlist (*.m3u *M3U);;All (*)"))
        if file_path:
            try:
                if save_playlist(file_path, entries):
                    self.statusBar().showMessage(
                        _("Save Complete") + ": " + _("File {0} processed.").format(Path(file_path).name), 5000)
                    return file_path
                else:
                    QMessageBox.critical(self, _("Save Error"), _("No favorites found."))
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, _("Save Error"), _("Failed to save file: {0}").format(e))
        return None

    def pick_load_directory(self):
        directory = QFileDialog.getExistingDirectory(self, _("Select Music Directory"),
                                                     dir=self._get_default_directory())
        if directory:
            self.load_directory(directory)

    def files_opened(self, file_infos: list[QFileInfo]):
        for file_info in file_infos:
            if file_info.isDir():
                self.load_directory(file_info.filePath())
            elif file_info.fileName().lower().endswith(".m3u"):
                self.load_playlist(file_info.filePath())

    def load_playlist(self, playlist_path: PathLike[str], activate: bool = True, lazy: bool = False) -> SongTable | None:
        try:
            if playlist_path in self.get_open_tables():
                self.statusBar().showMessage(_("Playlist already opened"))
                return None

            self.statusBar().showMessage(_("Loading playlist"), 2000)
            QApplication.processEvents()

            table = self.add_table_tab(playlist_path, lazy=lazy, activate=activate)

            AppSettings.setValue(SettingKeys.OPEN_TABLES, self.get_open_tables())

            self.statusBar().clearMessage()

            return table
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, _("Open Error"), _("Failed to load playlist: {0}").format(e))

    def add_to_playlist(self, playlist: PathLike[str], songs: list[Mp3Entry]):
        for i in range(self.table_tabs.count()):
            table = self.table_tabs.widget(i)
            if table.playlist == playlist:
                table.table_model.addRows(songs)
                break

        if table:
            create_m3u(table.mp3_datas(), playlist)

    def get_open_tables(self) -> list[PathLike[str]]:
        open_tables = []
        for i in range(self.table_tabs.count()):
            table = self.table_tabs.widget(i)
            if table.playlist is not None:
                open_tables.append(table.playlist)
            else:
                open_tables.append(table.directory)

        return open_tables

    def get_playlists(self) -> list[PathLike[str]]:
        playlists = []
        for i in range(self.table_tabs.count()):
            table = self.table_tabs.widget(i)
            if table.playlist is not None:
                playlists.append(table.playlist)

        return playlists

    def load_directory(self, directory: PathLike[str], activate: bool = True, lazy: bool = False) -> SongTable | None:
        try:
            if directory in self.get_open_tables():
                self.statusBar().showMessage(_("Directory already opened"))
                return None

            self.statusBar().showMessage(_("Loading directory"), 5000)
            QApplication.processEvents()

            AppSettings.setValue(SettingKeys.LAST_DIRECTORY, directory)

            table = self.add_table_tab(directory, lazy=lazy, activate=activate)

            AppSettings.setValue(SettingKeys.OPEN_TABLES, self.get_open_tables())

            self.statusBar().clearMessage()
            return table
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, _("Error"), _("Failed to scan directory: {0}").format(e))

    def get_available_categories(self) -> list[MusicCategory]:
        table = self.current_table()
        return table.table_model.available_categories if table is not None else []

    def close_tables(self):
        self.table_tabs.clear()

    def reload_table(self, index: int | None):
        if index is None:
            index = self.sender().data()

        table = self.table(index)
        table.reload_files()

    def table(self, index: int) -> SongTable | None:
        return self.table_tabs.widget(index) if self.table_tabs is not None else None

    def current_table(self) -> SongTable | None:
        return self.table_tabs.currentWidget() if self.table_tabs is not None else None

    def load_initial_directory(self):
        open_tables = AppSettings.value(SettingKeys.OPEN_TABLES, [], type=list)

        if open_tables:
            for index, open_table in enumerate(open_tables):
                self.load(open_table, lazy=index != 0, activate=index == 0)

    def load(self, path: PathLike[str], activate=True, lazy: bool = False):
        if Path(path).is_dir():
            self.load_directory(path, lazy=lazy, activate=activate)
        elif Path(path).is_file():
            self.load_playlist(path, lazy=lazy, activate=activate)
        else:
            QMessageBox.critical(self, _("Open Error"), _("Failed to load: {0}").format(path))

    def play_track(self, index: QPersistentModelIndex | None, entry: Mp3Entry | None):
        table = self.current_table()
        if table is None:
            if entry is not None:
                self.player.play_track(index, entry)
                return
            else:
                return

        if not index.isValid() and entry is not None:
            # calc index of entry
            entry_index = table.index_of(entry)
            if entry_index.isValid():
                table.clearSelection()
                table.selectRow(entry_index.row())
            self.player.play_track(QPersistentModelIndex(entry_index), entry)
        elif index.isValid():
            table.clearSelection()
            table.selectRow(index.row())
            self.player.play_track(index, index.data(Qt.ItemDataRole.UserRole))
        else:
            index = table.model().index(0, 0)
            table.clearSelection()
            table.selectRow(index.row())
            self.player.play_track(index, index.data(Qt.ItemDataRole.UserRole))

def hide_splash(window: QMainWindow):
    if '_PYI_SPLASH_IPC' in os.environ and importlib.util.find_spec("pyi_splash"):
        import pyi_splash
        pyi_splash.close()

        # bring window to top and act like a "normal" window!
        window.setWindowFlags(
            window.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)  # set always on top flag, makes window disappear
        window.show()  # makes window reappear, but it's ALWAYS on top
        window.setWindowFlags(
            window.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowCloseButtonHint)  # clear always on top flag, makes window disappear
        window.show()  # makes window reappear, acts like normal window now (on top now but can be underneath if you raise another window)
    else:
        window.show()

def main():
    if "DEBUG" in os.environ:
        logger.setLevel(logging.DEBUG)

    app = QApplication(sys.argv)

    # Set up Gettext

    language = AppSettings.value(SettingKeys.LOCALE, type=str)
    if language is None or language == "":
        loc, encoding = locale.getlocale()
        language = loc

    i18n = gettext.translation("DungeonTuber", get_path("locales"), fallback=True, languages=[language])

    # Create the "magic" function
    i18n.install()

    app.setOrganizationName("Gandulf")
    app.setApplicationName("Dungeon Tuber")
    app.setApplicationVersion(get_current_version())

    app_theme.application = app
    app_theme.apply_stylesheet()

    window = MusicPlayer(app)
    hide_splash(window)

    sys.exit(app.exec())

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        logger.exception("Main crashed. Error: {0}", e)
