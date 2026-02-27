import string

from PySide6.QtCore import QObject, Property, Qt, QSize
from PySide6.QtGui import QColor, QPalette, QBrush, QGradient, QIcon, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from config.settings import AppSettings, SettingKeys
from config.utils import get_path


def _alpha(color: QColor, alpha: int = None):
    if alpha is None:
        return color

    new_color = QColor(color)
    new_color.setAlpha(alpha)
    return new_color


def _pt_to_px(pt):
    return int(pt * (96 / 72))


QIcon.setThemeSearchPaths([get_path("assets/icons")] + QIcon.themeSearchPaths())


class AppTheme(QObject):
    light_palette: QPalette = None
    dark_palette: QPalette = None

    _green = QColor("#5CB338")
    _yellow = QColor("#ECE852")
    _orange = QColor("#FFC145")
    _red = QColor("#FB4141")

    font_families = None

    application: QApplication

    _color_cache: dict[string, QColor] = {}
    _brush_cache: dict[string, QBrush] = {}

    _small_factor = 0.6

    def __init__(self):
        super().__init__()
        self._calculate_sizes(AppSettings.value(SettingKeys.FONT_SIZE, 10.5, type=int))

        self.light_palette = self.get_light_mode_palette()
        self.dark_palette = self.get_dark_mode_palette()

    def _calculate_sizes(self, base_font_size: float):
        self._font_size = base_font_size
        self._font_size_small = self._font_size * 0.8  # Small size

        self._spacing = int(self._font_size * 0.8)
        self._padding = int(self._font_size * 0.5)

        self._icon_width = _pt_to_px(self._font_size * 1.5)
        self._icon_height = _pt_to_px(self._font_size * 1.5)

        self._icon_size = QSize(self._icon_width, self._icon_height)

        self._icon_width_small = int(self._icon_width * self._small_factor)
        self._icon_height_small = int(self._icon_height * self._small_factor)

        self._icon_size_small = QSize(self._icon_width_small, self._icon_height_small)

        self._button_width = _pt_to_px(self._font_size * 4)
        self._button_height = _pt_to_px(self._font_size * 4)
        self._button_size = QSize(self._button_width, self._button_height)

        self._button_height_small = int(self._button_height * self._small_factor)
        self._button_width_small = int(self._button_width * self._small_factor)
        self._button_size_small = QSize(self._button_width_small, self._button_height_small)

    def font(self, bold: bool = False, small: bool = False):
        font = self.application.font()
        font.setBold(bold)
        if small:
            font.setPointSizeF(self._font_size_small)
        else:
            font.setPointSizeF(self._font_size)

        return font

    @Property(int)
    def spacing(self) -> int:
        return self._spacing

    @Property(int)
    def padding(self) -> int:
        return self._padding

    @Property(QSize)
    def icon_size(self) -> QSize:
        return self._icon_size

    @Property(QSize)
    def button_size(self) -> QSize:
        return self._button_size

    @Property(QSize)
    def icon_size_small(self) -> QSize:
        return self._icon_size_small

    @Property(QSize)
    def button_size_small(self) -> QSize:
        return self._button_size_small

    @Property(float)
    def font_size(self) -> float:
        return self._font_size

    @Property(int)
    def font_size_px(self) -> int:
        return _pt_to_px(self._font_size)

    @font_size.setter
    def font_size(self, size):
        AppSettings.setValue(SettingKeys.FONT_SIZE, size)
        self._calculate_sizes(size)

        # Re-apply the stylesheet to trigger a global update
        self.apply_stylesheet()

    @icon_size.setter
    def icon_size(self, size):
        self._icon_size = size
        # Re-apply the stylesheet to trigger a global update
        self.apply_stylesheet()

    @button_size.setter
    def button_size(self, size):
        self._button_size = size
        # Re-apply the stylesheet to trigger a global update
        self.apply_stylesheet()

    def is_dark(self):
        return self.theme() != "LIGHT"

    def is_light(self):
        return self.theme() == "LIGHT"

    def get_green_brush(self, alpha: int = None):
        return self._brush_cache.setdefault(f"green{alpha}", self.get_green(alpha))

    def get_red_brush(self, alpha: int = None):
        return self._brush_cache.setdefault(f"red{alpha}", self.get_red(alpha))

    def get_yellow_brush(self, alpha: int = None):
        return self._brush_cache.setdefault(f"yellow{alpha}", self.get_yellow(alpha))

    def get_orange_brush(self, alpha: int = None):
        return self._brush_cache.setdefault(f"orange{alpha}", self.get_orange(alpha))

    def get_green(self, alpha: int = None):
        return self._color_cache.setdefault(f"green{alpha}", _alpha(self._green if self.is_light() else self._green.darker(170), alpha))

    def get_red(self, alpha: int = None):
        return self._color_cache.setdefault(f"red{alpha}", _alpha(self._red if self.is_light() else self._red.darker(170), alpha))

    def get_orange(self, alpha: int = None):
        return self._color_cache.setdefault(f"orange{alpha}", _alpha(self._orange if self.is_light() else self._orange.darker(170), alpha))

    def get_yellow(self, alpha: int = None):
        return self._color_cache.setdefault(f"yellow{alpha}", _alpha(self._yellow if self.is_light() else self._yellow.darker(170), alpha))

    def get_dark_mode_palette(self) -> QPalette:
        if self.dark_palette is None:
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Accent, QColor(0, 80, 203))
            palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
            palette.setColor(QPalette.ColorRole.Base, QColor(42, 42, 42))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(66, 66, 66, 50))
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
            palette.setColor(QPalette.ColorRole.Dark, QColor(35, 35, 35))
            palette.setColor(QPalette.ColorRole.Shadow, QColor(20, 20, 20))
            palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
            palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.lightGray)
            palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 102, 255))
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(80, 80, 80))
            palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor(127, 127, 127), )

            palette.setBrush(QPalette.ColorRole.Mid, QBrush(QGradient.Preset.PremiumDark))
            palette.setBrush(QPalette.ColorRole.Midlight, QBrush(QGradient.Preset.EternalConstance))

            self.dark_palette = palette

        return self.dark_palette

    def get_light_mode_palette(self) -> QPalette:
        if self.light_palette is None:
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Accent, QColor(0, 80, 203))
            # darkPalette.setColor(QPalette.Window, QColor(53, 53, 53))
            # darkPalette.setColor(QPalette.WindowText, Qt.white)
            # darkPalette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))
            # darkPalette.setColor(QPalette.Base, QColor(42, 42, 42))
            # darkPalette.setColor(QPalette.AlternateBase, QColor(66, 66, 66))
            # darkPalette.setColor(QPalette.ToolTipBase, QColor(53, 53, 53))
            # darkPalette.setColor(QPalette.ToolTipText, Qt.white)
            # darkPalette.setColor(QPalette.Text, Qt.white)
            # darkPalette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
            # darkPalette.setColor(QPalette.Dark, QColor(35, 35, 35))
            # darkPalette.setColor(QPalette.Shadow, QColor(20, 20, 20))
            # darkPalette.setColor(QPalette.Button, QColor(53, 53, 53))
            # darkPalette.setColor(QPalette.ButtonText, Qt.white)
            # darkPalette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
            # darkPalette.setColor(QPalette.BrightText, Qt.red)
            # darkPalette.setColor(QPalette.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.Highlight, QColor(0, 102, 255))
            # darkPalette.setColor(QPalette.Disabled, QPalette.Highlight, QColor(80, 80, 80))
            # darkPalette.setColor(QPalette.HighlightedText, Qt.white)
            # darkPalette.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor(127, 127, 127), )

            palette.setBrush(QPalette.ColorRole.Mid, QBrush(QGradient.Preset.SaintPetersburg))
            palette.setBrush(QPalette.ColorRole.Midlight, QBrush(QGradient.Preset.HeavyRain))
            # palette.setBrush(QPalette.ColorRole.Button, QBrush(QGradient.Preset.EverlastingSky))

            self.light_palette = palette

        return self.light_palette

    def create_play_pause_icon(self):
        # 1. Get the system theme icons
        play_icon_theme = QIcon.fromTheme(QIcon.ThemeIcon.MediaPlaybackStart)
        pause_icon_theme = QIcon.fromTheme(QIcon.ThemeIcon.MediaPlaybackPause)

        # 2. Create a new empty icon to hold both states
        combined_icon = QIcon()

        # 3. Transfer pixmaps from theme icons to the combined icon
        # We loop through standard sizes to ensure sharpness at different scales
        for size in [16, 24, 32, 48, 64]:
            q_size = QSize(size, size)

            # Add 'Play' to the Unchecked (Off) state
            play_pixmap = play_icon_theme.pixmap(q_size)
            if not play_pixmap.isNull():
                combined_icon.addPixmap(play_pixmap, QIcon.Mode.Normal, QIcon.State.Off)

            # Add 'Pause' to the Checked (On) state
            pause_pixmap = pause_icon_theme.pixmap(q_size)
            if not pause_pixmap.isNull():
                combined_icon.addPixmap(pause_pixmap, QIcon.Mode.Normal, QIcon.State.On)

        return combined_icon

    def set_theme(self, theme: str):
        AppSettings.setValue(SettingKeys.THEME, theme)
        self._color_cache.clear()
        self._brush_cache.clear()
        self.apply_stylesheet()

    def theme(self):
        return AppSettings.value(SettingKeys.THEME, "LIGHT", type=str)

    def apply_stylesheet(self):
        theme = self.theme()

        global_font = QFont()
        if self.font_families is not None:
            font_family = self.font_families[0]
            global_font.setFamily(font_family)
        else:
            font_family = global_font.family()

        global_font.setPointSizeF(self.font_size)
        self.application.setFont(global_font)

        style = f"""        
                    QMenu {{
                        font-family: '{font_family}';                        
                    }}
                    QMenuBar, QMenuBar::item {{
                        font-family: '{font_family}';                        
                    }}
                    
                    QHeaderView {{
                        font-family: '{font_family}';        
                    }}
                    
                    QPushButton[cssClass~="play"]::checked, QToolButton[cssClass~="play"]::checked {{
                        background-color: rgb(0, 102, 255);                        
                    }}
                    
                    QLabel[cssClass~="header"] {{
                        font-size: {self._font_size}pt;
                        font-weight: bold;
                    }}
                    
                    QLabel[cssClass~="small"] {{
                        font-size: {self._font_size_small}pt;                    
                    }}
                    
                    QLabel[cssClass~="mini"] {{
                        font-size: {self._font_size_small * 0.8}pt;                    
                    }}
                    
                    QSlider[cssClass="button"] {{                                                                        
                        height: {self._button_height}px;
                    }}
                    
                    QSlider[cssClass="buttonSmall"] {{                                                                       
                        height: {self._button_height_small + 4}px;
                    }}
                    
                    QToolButton {{                                                 
                        width: {self._button_width}px;                        
                        height: {self._button_height}px;
                        qproperty-iconSize: {self._icon_width}px;
                    }}
                    
                    QToolButton[cssClass~="small"]  {{                        
                        width: {self._button_width_small}px;                        
                        height: {self._button_height_small}px;
                        qproperty-iconSize: {self._icon_width_small}px;
                    }}
                    QPushButton[cssClass~="small"]  {{                                                                                                                        
                        height: {self._button_height_small}px;
                        qproperty-iconSize: {self._icon_width_small}px;
                    }}                    
                    
                    QToolButton[cssClass~="mini"] {{                                                                        
                        width: {int(self._button_width_small * 0.7)}px;                        
                        height: {int(self._button_height_small * 0.7)}px;
                        qproperty-iconSize: {int(self._icon_width_small)}px;
                    }}                    
                    
                    QPushButton[cssClass~="mini"] {{                                                                                                                        
                        height: {int(self._button_height_small * 0.7)}px;
                        qproperty-iconSize: {int(self._icon_width_small)}px;
                    }}
                    
                    
                """

        QIcon.setThemeName(theme)

        if theme == "LIGHT":
            self.application.setPalette(self.get_light_mode_palette())
        else:
            self.application.setPalette(self.get_dark_mode_palette())
            style += """
                
        QLineEdit[text=""] {
            color:white;
        }
        
        QPushButton, QToolButton {
            background-color: rgba(42,42,42,200);
        }
        
        QPushButton::selected, QToolButton::selected {
            background-color: rgba(82,82,82,170);
        }
        
        QPushButton::hover, QToolButton::hover {
            background-color: rgba(82,82,82,170);
        }
        
        QMenu {
            background-color: rgb(42, 42, 42);
            border: 1px solid rgb(60, 60, 60);                        
        }
        
        QMenu::item {
            padding:5px;                     
        }
        
        QMenu::icon {
            padding:5px;         
        }
        
        QMenu::item:selected {            
            background: rgba(100, 100, 100, 150);            
        }
        
        QComboBox {
            background-color: rgb(42, 42, 42);
            padding:2px;
            border: 1px solid rgb(80, 80, 80);
            border-radius:2px
        }
        
        QComboBox QListView {
            background-color: rgb(42, 42, 42);
        }
        """

        self.application.setStyleSheet(style)


app_theme: AppTheme = AppTheme()
