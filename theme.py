from PySide6.QtCore import QObject, Property, Qt
from PySide6.QtGui import QColor, QPalette, QBrush, QGradient
from PySide6.QtWidgets import QApplication

from settings import settings, SettingKeys

def _alpha(color: QColor, alpha: int = None):
    if alpha is None:
        return color
    else:
        new_color = QColor(color)
        new_color.setAlpha(alpha)
        return new_color


class AppTheme(QObject):
    light_palette: QPalette = None
    dark_palette: QPalette = None

    _green = QColor("#5CB338")
    _yellow = QColor("#ECE852")
    _orange = QColor("#FFC145")
    _red = QColor("#FB4141")

    application: QApplication

    def __init__(self):
        super().__init__()
        self._font_size = settings.value(SettingKeys.FONT_SIZE, 14, type=int)  # Default size
        self._icon_size = self._font_size * 2
        self._button_size = self._font_size * 4

        self.light_palette = self.get_lightModePalette()
        self.dark_palette = self.get_darkModePalette()

    @Property(int)
    def icon_size(self):
        return self._icon_size

    @Property(int)
    def button_size(self):
        return self._button_size

    @Property(int)
    def font_size(self):
        return self._font_size

    @font_size.setter
    def font_size(self, size):
        settings.setValue(SettingKeys.FONT_SIZE, size)
        self._font_size = size
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

    def get_green(self, alpha: int = None):
        return _alpha(self._green if self.is_light() else self._green.darker(170), alpha)

    def get_red(self, alpha: int = None):
        return _alpha(self._red if self.is_light() else self._red.darker(170), alpha)

    def get_orange(self, alpha: int = None):
        return _alpha(self._orange if self.is_light() else self._orange.darker(170), alpha)

    def get_yellow(self, alpha: int = None):
        return _alpha(self._yellow if self.is_light() else self._yellow.darker(170), alpha)

    def get_darkModePalette(self) -> QPalette:
        if self.dark_palette is None:
            darkPalette = QPalette()
            darkPalette.setColor(QPalette.Accent,QColor(0,80,203))
            darkPalette.setColor(QPalette.Window, QColor(53, 53, 53))
            darkPalette.setColor(QPalette.WindowText, Qt.GlobalColor.white)
            darkPalette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))
            darkPalette.setColor(QPalette.Base, QColor(42, 42, 42))
            darkPalette.setColor(QPalette.AlternateBase, QColor(66, 66, 66))
            darkPalette.setColor(QPalette.ToolTipBase, QColor(53, 53, 53))
            darkPalette.setColor(QPalette.ToolTipText, Qt.GlobalColor.white)
            darkPalette.setColor(QPalette.Text, Qt.GlobalColor.white)
            darkPalette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
            darkPalette.setColor(QPalette.Dark, QColor(35, 35, 35))
            darkPalette.setColor(QPalette.Shadow, QColor(20, 20, 20))
            darkPalette.setColor(QPalette.Button, QColor(53, 53, 53))
            darkPalette.setColor(QPalette.ButtonText, Qt.GlobalColor.white)
            darkPalette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
            darkPalette.setColor(QPalette.BrightText, darkPalette.color(QPalette.Accent))
            darkPalette.setColor(QPalette.Link, QColor(42, 130, 218))
            darkPalette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            darkPalette.setColor(QPalette.Disabled, QPalette.Highlight, QColor(80, 80, 80))
            darkPalette.setColor(QPalette.HighlightedText, Qt.GlobalColor.white)
            darkPalette.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor(127, 127, 127), )

            darkPalette.setBrush(QPalette.ColorRole.Mid, QBrush(QGradient.Preset.PremiumDark))
            darkPalette.setBrush(QPalette.ColorRole.Midlight, QBrush(QGradient.Preset.EternalConstance))

            self.dark_palette = darkPalette

        return self.dark_palette

    def get_lightModePalette(self) -> QPalette:
        if self.light_palette is None:
            lightPalette = QPalette()
            lightPalette.setColor(QPalette.ColorRole.Accent,  QColor(1, 71, 173))
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
            # darkPalette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            # darkPalette.setColor(QPalette.Disabled, QPalette.Highlight, QColor(80, 80, 80))
            # darkPalette.setColor(QPalette.HighlightedText, Qt.white)
            # darkPalette.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor(127, 127, 127), )

            lightPalette.setBrush(QPalette.ColorRole.Mid, QBrush(QGradient.Preset.SaintPetersburg))
            lightPalette.setBrush(QPalette.ColorRole.Midlight, QBrush(QGradient.Preset.HeavyRain))
            # lightPalette.setBrush(QPalette.ColorRole.Button, QBrush(QGradient.Preset.EverlastingSky))

            self.light_palette = lightPalette

        return self.light_palette

    def set_theme(self, theme: str):
        settings.setValue(SettingKeys.THEME, theme)
        self.apply_stylesheet()

    def theme(self):
        return settings.value(SettingKeys.THEME, "LIGHT", type=str)

    def apply_stylesheet(self):
        theme = self.theme()

        style = f"""
                    QWidget {{
                        font-size: {self._font_size}px;
                    }}
                    QPushButton {{
                        padding: {self._font_size // 2}px;
                    }}
                """

        if theme == "LIGHT":
            self.application.setPalette(self.get_lightModePalette())
        else:
            self.application.setPalette(self.get_darkModePalette())
            style += f"""

                QLineEdit[text=""] {{
                    color:white
                }}

                QPushButton {{
                    background-color: rgba(42,42,42,200)
                }}

                QPushButton::selected {{
                    background-color: rgba(82,82,82,170)
                }}

                QPushButton::hover {{
                    background-color: rgba(82,82,82,170)
                }}

                QMenu {{
                    background-color: rgb(42, 42, 42);
                    border: 1px solid rgb(60, 60, 60);                
                }}

                QMenu::item {{

                }}

                QMenu::item:selected {{                
                    background: rgba(100, 100, 100, 150);
                }}
            """

        self.application.setStyleSheet(style)


app_theme: AppTheme = AppTheme()