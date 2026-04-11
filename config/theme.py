import string
from enum import Enum

from PySide6.QtCore import QObject, Property, Qt, QSize, QMargins
from PySide6.QtGui import QColor, QPalette, QBrush,  QIcon, QFont
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect

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


class FontSize(Enum):
    SMALL = 0
    MEDIUM = 1
    LARGE = 2


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
        self._font_size_large = self._font_size * 1.1  # Large size

        self._spacing = int(self._font_size * 0.8)
        self._padding = int(self._font_size * 0.5)

        self._icon_width = _pt_to_px(self._font_size * 1.5)
        self._icon_height = _pt_to_px(self._font_size * 1.5)

        self._icon_size = QSize(self._icon_width, self._icon_height)

        self._icon_width_small = int(self._icon_width * 0.8)
        self._icon_height_small = int(self._icon_height * 0.8)

        self._icon_width_mini = int(self._icon_width * self._small_factor)
        self._icon_height_mini = int(self._icon_height * self._small_factor)

        self._icon_size_small = QSize(self._icon_width_small, self._icon_height_small)

        self._button_width = _pt_to_px(self._font_size * 4)
        self._button_height = _pt_to_px(self._font_size * 4)
        self._button_size = QSize(self._button_width, self._button_height)

        self._button_height_small = int(self._button_height * self._small_factor)
        self._button_width_small = int(self._button_width * self._small_factor)
        self._button_size_small = QSize(self._button_width_small, self._button_height_small)

    def font_small(self, bold: bool = False) -> QFont:
        return self.font(bold, FontSize.SMALL)

    def font_large(self, bold: bool = False) -> QFont:
        return self.font(bold, FontSize.LARGE)

    def font(self, bold: bool = False, size: FontSize = FontSize.MEDIUM) -> QFont:
        font = self.application.font()
        font.setBold(bold)
        if size == FontSize.SMALL:
            font.setPointSizeF(self._font_size_small)
        elif size == FontSize.MEDIUM:
            font.setPointSizeF(self._font_size)
        else:
            font.setPointSizeF(self._font_size * 1.2)

        return font

    @Property(int)
    def spacing(self) -> int:
        return self._spacing

    def drop_shadow(self, parent):
        shadow = QGraphicsDropShadowEffect(parent)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 160))
        return shadow

    @Property(QMargins)
    def margin(self) -> QMargins:
        return QMargins(self._spacing, self._spacing, self._spacing, self._spacing)

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
        return self._color_cache.setdefault(f"green{alpha}",
                                            _alpha(self._green if self.is_light() else self._green.darker(170), alpha))

    def get_red(self, alpha: int = None):
        return self._color_cache.setdefault(f"red{alpha}",
                                            _alpha(self._red if self.is_light() else self._red.darker(170), alpha))

    def get_orange(self, alpha: int = None):
        return self._color_cache.setdefault(f"orange{alpha}",
                                            _alpha(self._orange if self.is_light() else self._orange.darker(170),
                                                   alpha))

    def get_yellow(self, alpha: int = None):
        return self._color_cache.setdefault(f"yellow{alpha}",
                                            _alpha(self._yellow if self.is_light() else self._yellow.darker(170),
                                                   alpha))

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
            palette.setColor(QPalette.ColorRole.Shadow, QColor(20, 20, 20))
            palette.setColor(QPalette.ColorRole.Button, QColor(63, 63, 63))
            palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
            palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.lightGray)
            palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 102, 255))
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(80, 80, 80))
            palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor(127, 127, 127))

            palette.setColor(QPalette.ColorRole.Dark, QColor(35, 35, 35))
            palette.setColor(QPalette.ColorRole.Mid, QColor(63, 63, 63))
            palette.setColor(QPalette.ColorRole.Midlight, QColor(43, 43, 43))
            palette.setColor(QPalette.ColorRole.Light, QColor(33, 33, 33))

            self.dark_palette = palette

        return self.dark_palette

    def get_light_mode_palette(self) -> QPalette:
        if self.light_palette is None:
            palette = QPalette()

            # --- ACCENT & HIGHLIGHT ---
            # Keeping your blue accent, but slightly more vibrant for light mode
            accent_blue = QColor(0, 102, 255)
            palette.setColor(QPalette.ColorRole.Accent, accent_blue)
            palette.setColor(QPalette.ColorRole.Highlight, accent_blue)
            palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.Link, QColor(0, 80, 203))

            # --- BACKGROUNDS ---
            # Window is the main background; Base is for text inputs/lists
            palette.setColor(QPalette.ColorRole.Window, QColor(245, 245, 247))
            palette.setColor(QPalette.ColorRole.Base, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.AlternateBase, _alpha(QColor(235, 235, 240), 150))
            palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)

            # --- TEXT ---
            # Using a deep charcoal instead of pure black for better readability
            dark_text = QColor(30, 30, 30)
            palette.setColor(QPalette.ColorRole.WindowText, dark_text)
            palette.setColor(QPalette.ColorRole.Text, dark_text)
            palette.setColor(QPalette.ColorRole.ToolTipText, dark_text)
            palette.setColor(QPalette.ColorRole.BrightText, QColor(105, 105, 110))

            # --- BUTTONS ---
            palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorRole.ButtonText, dark_text)

            # --- BORDERS & SHADOWS ---

            palette.setColor(QPalette.ColorRole.Light, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorRole.Midlight, QColor(225, 225, 225))
            palette.setColor(QPalette.ColorRole.Mid, QColor(200, 200, 200))
            palette.setColor(QPalette.ColorRole.Dark, QColor(180, 180, 180))
            palette.setColor(QPalette.ColorRole.Shadow, QColor(140, 140, 140))

            # --- DISABLED STATE ---
            # Crucial: Grey text on a light background must be dark enough to see
            disabled_grey = QColor(160, 160, 160)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_grey)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_grey)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_grey)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(200, 200, 200))
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)

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

        palette: QPalette = self.get_light_mode_palette() if theme == "LIGHT" else self.get_dark_mode_palette()

        global_font = QFont()
        if self.font_families is not None:
            font_family = self.font_families[0]
            global_font.setFamily(font_family)
        else:
            font_family = global_font.family()

        global_font.setPointSizeF(self.font_size)
        self.application.setFont(global_font)

        _base_color = palette.color(QPalette.ColorRole.Base).name()
        _base_alt_color = palette.color(QPalette.ColorRole.Base).darker(110).name()
        _accent_color = palette.color(QPalette.ColorRole.Accent).name()
        _border_color = palette.color(QPalette.ColorRole.Mid).name()
        _text_color = palette.color(QPalette.ColorRole.Text).name()

        _button_color = palette.color(QPalette.ColorRole.Button).name(QColor.HexArgb)
        _button_text_color = palette.color(QPalette.ColorRole.ButtonText).name()
        _button_hover_color = palette.color(QPalette.ColorRole.Button).lighter(120).name(QColor.HexArgb)

        style = f"""                                                  
                    .IconLabel {{
                        border:none;
                        border-bottom:3px solid {_border_color};
                        padding-bottom:3px;
                    }}
                               
                    QMenu {{
                        font-family: '{font_family}';                        
                    }}
                    QMenuBar, QMenuBar::item {{
                        font-family: '{font_family}';                        
                    }}
                    
                    QTreeView, QListView {{
                        border:none
                    }}
                    
                    QFrame#tabs_widget {{
                        border:none;
                        border-top:3px solid {_border_color};
                    }}
                    
                    QTabView {{
                        margin:12px;
                    }}
                    
                    QTabBar::tab:top, QTabBar::tab:bottom {{
                        height: 30px;
                    }}
                    
                    QTabBar::tab:!selected {{                                                                          
                        font-size:{self._font_size_large}pt;
                    }}
                    
                    QTabBar::tab:selected {{                                                                        
                        font-size:{self._font_size_large}pt;
                        font-weight:bold;
                    }}
                    
                    QTableView {{
                        border:none;
                        outline: 0;                        
                    }}
                    QTableView::item:hover {{
                        background-color: transparent;
                        border: none;
                    }}
                    
                    QHeaderView {{                        
                        background-color: {_base_alt_color};
                        border:none        
                    }}
                    
                    QHeaderView::section {{
                        font-family: '{font_family}';
                        background-color: {_base_alt_color};
                        border:none;
                        border-right:1px solid {_border_color};
                    }}
                    
                    QLineEdit[text=""] {{
                        color:{_text_color};
                    }}
                    
                    QPushButton, QToolButton {{
                        background-color: {_button_color};
                    }}
                    
                    QPushButton::selected, QToolButton::selected {{
                        background-color: {_button_hover_color};
                    }}
                    
                    QPushButton::hover, QToolButton::hover {{
                        background-color: {_button_hover_color};
                    }}                    
                    
                    QPushButton[cssClass~="play"]::checked, QToolButton[cssClass~="play"]::checked {{
                        background-color: {_accent_color};                        
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

                    RoundButton {{
                        border:1px solid {_border_color};
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
                        qproperty-iconSize: {self._icon_width_mini}px;
                    }}                    
                    
                    QToolButton[cssClass~="mini"] {{                                                                        
                        width: {int(self._button_width_small * 0.7)}px;                        
                        height: {int(self._button_height_small * 0.7)}px;
                        qproperty-iconSize: {int(self._icon_width_mini)}px;
                    }}                    
                    
                    QPushButton[cssClass~="mini"] {{                                                                                                                        
                        height: {int(self._button_height_small * 0.7)}px;
                        qproperty-iconSize: {int(self._icon_width_mini)}px;
                    }}                
                    
                    QComboBox {{
                        background-color: {_base_color};
                        padding:2px;
                        border: 1px solid {_border_color};
                        border-radius:2px
                    }}
                    
                    QComboBox QListView {{
                        background-color: {_base_color};
                    }}                    
                    
                """

        QIcon.setThemeName(theme)

        self.application.setPalette(palette)
        if theme == "DARK":
            style += f"""        
        
        QMenu {{
            background-color: {_base_color};
            border: 1px solid {_border_color};                        
        }}
        
        QMenu::item {{
            padding:8px;                     
        }}
        
        QMenu::icon {{
            padding:8px;         
        }}
        
        QMenu::item:selected {{           
            background: rgba(100, 100, 100, 150);            
        }}        
        """

        self.application.setStyleSheet(style)


app_theme: AppTheme = AppTheme()
