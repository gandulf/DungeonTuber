from enum import StrEnum

from PySide6 import QtWidgets
from PySide6.QtCore import QRect, QPoint, Signal, QSize
from PySide6.QtGui import QLinearGradient, QColor, QPolygon, QPen, QBrush, QPainter, Qt, QIcon
from PySide6.QtWidgets import QStyle, QHBoxLayout, QPushButton

from components.QJumpSlider import QJumpSlider
from config.theme import app_theme


class VolumeSliderStyle(QtWidgets.QProxyStyle):
    def drawComplexControl(self, control, option, painter: QPainter, widget: QJumpSlider = None):
        if control == QStyle.ComplexControl.CC_Slider:

            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            rect = option.rect
            glow_size = widget.property("glow_size") if widget else 0

            # Adjust for margins
            margin = 2
            w = rect.width() - (margin * 2)
            h = rect.height() - (margin * 2)

            # 1. Define the Triangle Geometry
            p1 = QPoint(rect.left() + margin, rect.bottom() - margin)
            p2 = QPoint(rect.right() - margin, rect.top() + margin)
            p3 = QPoint(rect.right() - margin, rect.bottom() - margin)
            triangle = QPolygon([p1, p2, p3])

            # 2. Draw Background (Hollow/Empty part)
            base = QColor(option.palette.base().color())
            base.setAlpha(50)

            border = QColor(option.palette.text().color())
            border.setAlpha(50)


            painter.save()

            painter.setPen(QPen(border))
            painter.setBrush(QBrush(base))
            painter.drawPolygon(triangle)

            painter.restore()

            # 3. Calculate Fill based on Slider Position
            # QStyleOptionSlider gives us the current position accurately
            low = option.minimum
            high = option.maximum
            progress = (option.sliderPosition - low) / (high - low) if high > low else 0

            fill_width = int(w * progress)
            fill_height = int(h * progress)

            painter.drawText(0, 20, f"{round(progress * 100, 0)}%")

            # 4. Draw the Filled Part (Clipped)
            painter.save()
            clip_rect = QRect(rect.left(), rect.top(), fill_width + margin, rect.height())
            painter.setClipRect(clip_rect)

            # Use a gradient for a professional "Volume" look
            gradient = QLinearGradient(0, 0, w, 0)
            gradient.setColorAt(0.0, app_theme.get_green())  # Green
            gradient.setColorAt(0.7, app_theme.get_green())  # Green
            gradient.setColorAt(0.8, app_theme.get_yellow())  # Orange
            gradient.setColorAt(0.9, app_theme.get_orange())  # Orange
            gradient.setColorAt(1.0, app_theme.get_red())  # Red

            painter.setBrush(gradient)  # gradient fill
            painter.drawPolygon(triangle)
            painter.restore()

            # 5. Draw the Handle (The vertical line or knob)
            know_width = 14

            handle_x = max(0, rect.left() + margin + fill_width - (know_width / 2))
            if handle_x + know_width > rect.width():
                handle_x = rect.width() - know_width

            handle_y = max(0, rect.top() + (h - fill_height) - 2)

            handle_rect = QRect(handle_x, handle_y, know_width, fill_height + 4)

            painter.setBrush(option.palette.base())
            painter.drawRoundedRect(handle_rect, 4.0, 4.0)

            bump = 5 - glow_size

            handle_rect.adjust(bump, bump, -bump, -bump)
            if handle_rect.width() < 0:
                handle_rect.setWidth(0)
            if handle_rect.height() < 0:
                handle_rect.setHeight(0)

            painter.setBrush(option.palette.accent())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(handle_rect, 4.0, 4.0)

            painter.restore()

        else:
            super().drawComplexControl(control, option, painter, widget)


class VolumeSlider(QHBoxLayout):
    icon_volume_off: QIcon = QIcon.fromTheme(QIcon.ThemeIcon.AudioVolumeMuted)
    icon_volume_down: QIcon = QIcon.fromTheme(QIcon.ThemeIcon.AudioVolumeLow)
    icon_volume_up: QIcon = QIcon.fromTheme(QIcon.ThemeIcon.AudioVolumeHigh)

    # icon_volume_off = MaterialIcon('volume_off', size=materialIconSize)
    # icon_volume_down = MaterialIcon('volume_down', size=materialIconSize)
    # icon_volume_up = MaterialIcon('volume_down', size=materialIconSize)
    last_volume: int
    volumeChanged = Signal(int)

    def __init__(self, value: int = 70):
        super(VolumeSlider, self).__init__()
        self.btn_volume = QPushButton()
        self.btn_volume.setFixedSize(QSize(48, 48))
        self.btn_volume.setIconSize(QSize(20, 20))
        self.btn_volume.clicked.connect(self.toggle_mute)
        self.update_volume_icon(value)
        self.addWidget(self.btn_volume)

        self.slider_vol = QJumpSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(value)
        self.slider_vol.setFixedWidth(280)
        self.slider_vol.setFixedHeight(48)
        self.slider_vol.max_glow_size = 2
        self.slider_vol.valueChanged.connect(self.adjust_volume)
        self.slider_vol.setStyle(VolumeSliderStyle())
        self.slider_vol.setSingleStep(5)
        self.addWidget(self.slider_vol, 1)

    def volume(self):
        return self.slider_vol.value()

    def adjust_volume(self, value):
        self.update_volume_icon(value)
        self.volumeChanged.emit(value)

    def setButtonSize(self, buttonSize):
        self.btn_volume.setFixedSize(buttonSize)

    def setIconSize(self, iconSize):
        self.btn_volume.setIconSize(iconSize)

    def setValue(self, value):
        self.slider_vol.setValue(value)
        self.update_volume_icon(value)

    def toggle_mute(self):
        if self.slider_vol.value() > 0:
            self.last_volume = self.slider_vol.value()
            self.slider_vol.setValue(0)
        else:
            self.slider_vol.setValue(self.last_volume)

        self.volumeChanged.emit(self.slider_vol.value())

    def update_volume_icon(self, volume):
        if volume == 0:
            self.btn_volume.setIcon(self.icon_volume_off)
        elif volume < 50:
            self.btn_volume.setIcon(self.icon_volume_down)
        else:
            self.btn_volume.setIcon(self.icon_volume_up)


class RepeatMode(StrEnum):
    NO_REPEAT = "No Repeat"
    REPEAT_SINGLE = "Repeat Single"
    REPEAT_ALL = "Repeat All"


class RepeatButton(QPushButton):
    icon_no_repeat: QIcon = QIcon.fromTheme(QIcon.ThemeIcon.MediaPlaylistShuffle)
    icon_repeat_1: QIcon = QIcon.fromTheme(QIcon.ThemeIcon.MediaPlaylistRepeat)
    icon_repeat_all: QIcon = QIcon.fromTheme(QIcon.ThemeIcon.MediaPlaylistRepeat)

    # icon_no_repeat = MaterialIcon('repeat', size=materialIconSize)
    # icon_repeat_1 = MaterialIcon('repeat_one', size=materialIconSize)
    # icon_repeat_all = MaterialIcon('repeat_on', size=materialIconSize)

    REPEAT_MODES = [RepeatMode.NO_REPEAT, RepeatMode.REPEAT_SINGLE]

    valueChanged = Signal(RepeatMode)

    def __init__(self, value: int | RepeatMode = RepeatMode.NO_REPEAT, parent=None):
        super(RepeatButton, self).__init__(parent)

        if isinstance(value, RepeatMode):
            self.repeat_mode = value
        else:
            self.repeat_mode = self.REPEAT_MODES[int(value)]

        self.clicked.connect(self.cycle_repeat_mode)
        self.update_repeat_button()

    def cycle_repeat_mode(self):
        repeat_mode_index = (self.REPEAT_MODES.index(self.repeat_mode) + 1) % len(self.REPEAT_MODES)
        self.repeat_mode = self.REPEAT_MODES[repeat_mode_index]
        self.update_repeat_button()

        self.valueChanged.emit(self.repeat_mode)

    def setRepeatMode(self, repeatMode):
        self.repeat_mode = repeatMode
        self.valueChanged.emit(self.repeat_mode)

    def repeatMode(self):
        return self.repeat_mode

    def update_repeat_button(self):
        self.setToolTip(self.repeat_mode)

        if self.repeat_mode == RepeatMode.NO_REPEAT:
            self.setIcon(self.icon_no_repeat)
        elif self.repeat_mode == RepeatMode.REPEAT_SINGLE:
            self.setIcon(self.icon_repeat_1)
        elif self.repeat_mode == RepeatMode.REPEAT_ALL:
            self.setIcon(self.icon_repeat_all)

