import os
from enum import Enum, StrEnum

from PySide6.QtCore import QObject, Property, Qt, QSize, QMargins
from PySide6.QtGui import QColor, QPalette, QBrush, QIcon, QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QStyle

from config.settings import AppSettings, SettingKeys
from config.utils import get_path

_alpha_cache: dict[str, QColor] = {}

def _alpha(color: QColor, alpha: int|float|None = None):
    if alpha is None:
        return color

    if isinstance(alpha, int):
        return _alpha_cache.setdefault(f"int{color.name()}{alpha}", QColor.fromRgb(color.red(), color.green(), color.blue(), alpha))
    else:
        return _alpha_cache.setdefault(f"float{color.name()}{alpha}", QColor.fromRgbF(color.redF(), color.greenF(), color.blueF(), alpha))

def _pt_to_px(pt):
    return int(pt * (96 / 72))


QIcon.setThemeSearchPaths([get_path("assets/icons")] + QIcon.themeSearchPaths())


class FontSize(Enum):
    SMALL = 0
    MEDIUM = 1
    LARGE = 2

class Theme(StrEnum):
    SYSTEM = "SYSTEM"
    LIGHT ="LIGHT"
    DARK ="DARK"


class AppTheme(QObject):
    light_palette: QPalette = None
    dark_palette: QPalette = None
    system_palette:QPalette = None

    _green = QColor("#5CB338")
    _yellow = QColor("#ECE852")
    _orange = QColor("#FFC145")
    _red = QColor("#FB4141")

    font_families = None

    _font_small:QFont = None
    _font_medium:QFont = None
    _font_large:QFont = None

    application: QApplication

    _color_cache: dict[str, QColor] = {}
    _brush_cache: dict[str, QBrush] = {}

    _icon_normal_factor = 1.0
    _icon_small_factor = 0.8
    _icon_mini_factor = 0.65

    _size_normal_factor = 2.0
    _size_small_factor = 1.5
    _size_mini_factor = 1.2

    spacing =0

    def __init__(self):
        super().__init__()

        self.light_palette = self.get_light_mode_palette()
        self.dark_palette = self.get_dark_mode_palette()

    def _calculate_sizes(self, base_font_size: float):

        H = _pt_to_px(base_font_size) * 1.333

        U = round(H / 4)

        self._font_size = base_font_size
        self._font_size_small = self._font_size * 0.8  # Small size
        self._font_size_mini = self._font_size * 0.65  # Mini size
        self._font_size_large = self._font_size * 1.2  # Large size

        self.padding_xlarge = 4 * U
        self.padding_large = 3 * U
        self.padding = 2 * U
        self.padding_small = 1 * U
        self.margin_large = QMargins(self.padding_large, self.padding_large, self.padding_large, self.padding_large)
        self.margin = QMargins(self.padding, self.padding, self.padding, self.padding)
        self.margin_small = QMargins(self.padding_small, self.padding_small, self.padding_small, self.padding_small)

        self.icon_width = int(H * self._icon_normal_factor)
        self.icon_height =int(H * self._icon_normal_factor)
        self.icon_size = QSize(self.icon_width, self.icon_height)

        self.icon_width_small = int(H * self._icon_small_factor)
        self.icon_height_small = int(H * self._icon_small_factor)
        self.icon_size_small = QSize(self.icon_width_small, self.icon_height_small)

        self.icon_width_mini = int(H * self._icon_mini_factor)
        self.icon_height_mini = int(H * self._icon_mini_factor)
        self.icon_size_mini = QSize(self.icon_width_mini, self.icon_height_mini)

        self.button_width = int(H * self._size_normal_factor)
        self.button_height = int(H * self._size_normal_factor)
        self.button_size = QSize(self.button_width, self.button_height)

        self.button_height_small = int(H * self._size_small_factor)
        self.button_width_small = int(H * self._size_small_factor)
        self.button_size_small = QSize(self.button_width_small, self.button_height_small)

        self.button_height_mini = int(H * self._size_mini_factor)
        self.button_width_mini = int(H * self._size_mini_factor)
        self.button_size_mini = QSize(self.button_width_mini, self.button_height_mini)

        self.font_large = QFont(self.application.font())
        self.font_large.setBold(False)
        self.font_large.setPointSizeF(self._font_size_large)

        self.font_medium = QFont(self.application.font())
        self.font_medium.setBold(False)
        self.font_medium.setPointSizeF(self._font_size)

        self.font_small = QFont(self.application.font())
        self.font_small.setBold(False)
        self.font_small.setPointSizeF(self._font_size_small)

    def init_application(self, app:QApplication):
        self.application = app
        self.application.setStyle("Fusion")

        self._calculate_sizes(AppSettings.value(SettingKeys.FONT_SIZE, 10, type=int))

        self.system_palette = app.style().standardPalette()
        self.system_palette.setColor(QPalette.ColorRole.Mid, self.system_palette.color(QPalette.ColorRole.Window))

    def drop_shadow(self, parent):
        if self.theme() in [Theme.DARK, Theme.LIGHT]:
            shadow = QGraphicsDropShadowEffect(parent)
            shadow.setBlurRadius(20)
            shadow.setXOffset(0)
            shadow.setYOffset(0)
            shadow.setColor(QColor(0, 0, 0, 160))
            return shadow
        else:
            return None

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

    def is_light(self):
        return self.theme() in [Theme.LIGHT, Theme.SYSTEM]

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

    def get_stylesheet(self, theme:Theme | None = None) -> str:
        if theme is None:
            theme = self.theme()

        palette: QPalette = self.get_palette(theme)

        _h = _pt_to_px(self._font_size) * 1.333

        _window_color = palette.color(QPalette.ColorRole.Window).name()

        _base_color = palette.color(QPalette.ColorRole.Base).name()
        _base_color2 = palette.color(QPalette.ColorRole.Base).darker(103).name()
        _base_alt_color = palette.color(QPalette.ColorRole.Base).darker(110).name()
        _accent_color = palette.color(QPalette.ColorRole.Accent).name()
        _border_color = palette.color(QPalette.ColorRole.Mid).name()
        _text_color = palette.color(QPalette.ColorRole.Text).name()

        _button_color = palette.color(QPalette.ColorRole.Button).name(QColor.NameFormat.HexArgb)
        _button_text_color = palette.color(QPalette.ColorRole.ButtonText).name()
        _button_hover_color = palette.color(QPalette.ColorRole.Button).lighter(120).name(QColor.NameFormat.HexArgb)

        _font_family = self.get_font_family()
        style=f"""                
            
            QTableView {{
                border-top:none
            }}
        
            QSlider#temperature, QSlider#brightness {{
                height: {_h}px;
            }}
                            
            QSlider#temperature::groove:horizontal {{
                height: {_h}px;
                border:1px solid {_border_color};
                border-radius: {_h /2}px;  
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #FF9329,   /* Warm Candlelight */
                    stop:0.5 #FFFFFB, /* Neutral Daylight */
                    stop:1 #C9DAFF);  /* Cold Overcast */        
            }}

            QSlider#temperature::handle:horizontal {{
                background: {_accent_color};
                border: 2px solid {_border_color};
                border-radius: {(_h - 2) /2}px;
                width: {_h - 2}px;
                height: {_h - 2}px;
            }}

            QSlider#brightness::groove:horizontal {{
                height: {_h}px;
                border:1px solid {_border_color};
                border-radius: {_h /2}px; 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #000000, 
                    stop:1 #FFFFFF);        
            }}

            QSlider#brightness::handle:horizontal {{
                background: {_accent_color};
                border: 2px solid {_border_color};
                border-radius: {(_h - 2) /2}px;
                width: {_h - 2}px;
                height: {_h - 2}px;
            }}

        """

        if theme in [Theme.LIGHT, Theme.DARK]:
            style += f"""   
            
                QTabBar::tab {{
                    background: {_base_alt_color};
                    border: none;
                    border-bottom: 2px solid transparent;
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                    padding: 6px 12px;
                    margin-right:2px;
                    margin-bottom:1px;
                    font-size: {self._font_size}pt;
                }}
                
                QTabBar::tab:selected {{
                    color: {_accent_color};
                    background: {_base_color};
                    
                    border-bottom: 2px solid {_accent_color}; 
                    font-weight: 600;
                }}
                                                               
                .IconLabel {{
                    border:none;
                    border-bottom:1px solid {_border_color};
                    padding-bottom:3px;
                }}

                .IconLabel#sub {{
                    border:none;
                }}
            
                QMenuBar, QMenuBar::item {{                                
                    color: {_text_color};                        
                }}
                
                QTreeView, QListView {{
                    background: transparent;
                }}
                
                QTreeView, QListView {{
                    border:none
                }}

                ToolButton, RoundButton {{
                    background-color: {_button_color};
                }}

                ToolButton::selected, RoundButton::selected {{
                    background-color: {_button_hover_color};
                }}

                ToolButton::hover, RoundButton::hover {{
                    background-color: {_button_hover_color};
                }}                    

                ToolButton::checked, RoundButton::checked {{
                    background-color: {_accent_color};                        
                }}
                
                RoundButton {{
                    border:1px solid {_border_color};
                }}

                QLabel[cssClass~="header"] {{
                    font-size: {self._font_size}pt;
                    font-weight: 600;
                }}

                QLabel[cssClass~="small"] {{
                    font-size: {self._font_size_small}pt;                    
                }}

                QLabel[cssClass~="mini"] {{
                    font-size: {self._font_size_mini}pt;                    
                }}

                QListWidget#lights {{
                    show-decoration-selected: 1;
                    outline: 0;
                }}

                QListWidget#lights::item {{
                    border:none;
                    padding-bottom:2px;                        
                }}
                QListWidget#lights::item:selected {{
                    padding-bottom:0px;
                    border: none;
                    border-bottom:2px solid {_accent_color};
                    color: {_text_color};                        
                }}
                
                QTableView {{
                    alternate-background-color: {_base_color2};
                }}
                
                QToolTip {{
                    background-color: {palette.color(QPalette.ColorRole.ToolTipBase).name()};
                    color: {palette.color(QPalette.ColorRole.ToolTipText).name()};
                }}   

            """

        return style

    def get_palette(self, theme:Theme | None = None):
        if theme is None:
            theme = self.theme()

        if theme == Theme.DARK:
            return self.get_dark_mode_palette()
        elif theme == Theme.LIGHT:
            return self.get_light_mode_palette()
        else:
            return self.get_system_palette()

    def get_list_palette(self):
        palette =QPalette(self.get_palette(self.theme()))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 0, 0, 10))  # Set hover alpha to 0 # Set the Highlight role to the same as the Base (background) role
        palette.setColor(QPalette.ColorRole.HighlightedText, palette.color(QPalette.ColorRole.Text))  # Set hover alpha to 0 # Set the Highlight role to the same as the Base (background) role
        return palette

    def get_system_palette(self) -> QPalette:
        return self.system_palette

    def get_dark_mode_palette(self) -> QPalette:
        if self.dark_palette is None:
            palette = QPalette()


            _accent = QColor(0, 80, 203)
            # --- ACCENT & HIGHLIGHT ---
            # Keeping your blue accent, but slightly less vibrant for dark mode
            palette.setColor(QPalette.ColorRole.Accent, _accent)
            palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 102, 255))
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(80, 80, 80))
            palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor(127, 127, 127))
            palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))

            # --- BACKGROUNDS ---
            # Window is the main background; Base is for text inputs/lists
            palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.Base, QColor(42, 42, 42))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(66, 66, 66, 50))
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(53, 53, 53))

            # --- TEXT ---
            palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
            palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
            palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.lightGray)

            # --- BUTTONS ---
            palette.setColor(QPalette.ColorRole.Button, QColor(73, 73, 73))
            palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))

            # --- BORDERS & SHADOWS ---
            palette.setColor(QPalette.ColorRole.Light, QColor(73, 73, 73))
            palette.setColor(QPalette.ColorRole.Midlight, QColor(63, 63, 63))
            palette.setColor(QPalette.ColorRole.Mid, QColor(43, 43, 43))
            palette.setColor(QPalette.ColorRole.Dark, QColor(35, 35, 35))

            palette.setColor(QPalette.ColorRole.Shadow, QColor(20, 20, 20))

            self.dark_palette = palette

        return self.dark_palette

    def get_light_mode_palette(self) -> QPalette:
        if self.light_palette is None:
            palette = QPalette()

            # --- ACCENT & HIGHLIGHT ---
            # Keeping your blue accent, but slightly more vibrant for light mode
            _accent = QColor(0, 102, 255)
            palette.setColor(QPalette.ColorRole.Accent, _accent)
            palette.setColor(QPalette.ColorRole.Highlight, _accent)
            palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.Link, _accent)

            # --- BACKGROUNDS ---

            # Window is the main background; Base is for text inputs/lists
            palette.setColor(QPalette.ColorRole.Window, QColor(243, 243, 243))
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
            palette.setColor( QPalette.ColorRole.Button, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorRole.ButtonText, dark_text)

            # --- BORDERS & SHADOWS ---
            light = QColor(240, 240, 240)
            palette.setColor(QPalette.ColorRole.Light, light)
            palette.setColor(QPalette.ColorRole.Midlight, light.darker(107))  # Result: ~224
            palette.setColor(QPalette.ColorRole.Mid, light.darker(120))  # Result: 200
            palette.setColor(QPalette.ColorRole.Dark, light.darker(133))  # Result: 180

            palette.setColor(QPalette.ColorRole.Shadow, QColor(140, 140, 140))  # Result: 140

            # --- DISABLED STATE ---
            # Crucial: Grey text on a light background must be dark enough to see
            disabled_grey = QColor(160, 160, 160)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_grey)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_grey)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_grey)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, disabled_grey.lighter(125))
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

    def set_theme(self, theme: Theme):
        AppSettings.setValue(SettingKeys.THEME, theme)
        self._color_cache.clear()
        self._brush_cache.clear()
        self.apply_stylesheet()

    def theme(self) -> Theme:
        return AppSettings.value(SettingKeys.THEME, Theme.LIGHT, type=str)

    def get_icon(self, icon_name: str, theme_name: str):
        for path in QIcon.themeSearchPaths():
            full_path =get_path(os.path.join(path, theme_name, "32x32", f"{icon_name}.svg"))
            if os.path.exists(full_path):
                return QIcon(full_path)
        return None

    def get_font_family(self):
        if self.font_families is not None:
            return self.font_families[0]
        else:
            return QFont().family()

    def get_icon_theme_name(self):
        if self.theme() == Theme.DARK:
            return Theme.DARK
        else:
            return Theme.LIGHT

    def apply_stylesheet(self):
        theme = self.theme()
        QIcon.setThemeName(self.get_icon_theme_name())
        self.application.setPalette(self.get_palette(theme))

        self.font_medium.setWeight(QFont.Weight.Normal)

        self.application.setFont(self.font_medium)

        self.application.setStyleSheet(self.get_stylesheet(theme))

app_theme: AppTheme = AppTheme()
