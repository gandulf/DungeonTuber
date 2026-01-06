import logging
import math

import random
from enum import StrEnum
from os import PathLike

from PySide6 import QtWidgets
from PySide6.QtCore import Property, Qt, QSize, Signal, QPropertyAnimation, QEasingCurve, QRect, QPointF, QPoint, \
    QTimer
from PySide6.QtWidgets import QCheckBox, QSlider, QStyle, QVBoxLayout, QLabel, QSizePolicy, QPushButton, QWidget, \
    QHBoxLayout, QFrame
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QIcon, QPolygon, QLinearGradient, QPainterStateGuard, \
    QPolygonF, QResizeEvent, QPalette

from theme import app_theme
from settings import get_category_description, settings, SettingKeys

logger = logging.getLogger("main")

_green = QColor("#5CB338")
_yellow = QColor("#ECE852")
_orange = QColor("#FFC145")
_red = QColor("#FB4141")

PAINTING_SCALE_FACTOR = 20


class Visualizer:
    fake_visualizer = None
    video_frame = None
    visualizer = None

    last_playing = None
    last_value = None
    last_track = None
    last_position = None

    def __init__(self, engine):
        self.engine = engine

    def refresh(self):
        # vis = settings.value(SettingKeys.VISUALIZER, "FAKE", type=str)
        result = self.setup()

        if (self.fake_visualizer is not None):
            if self.last_playing is not None:
                self.fake_visualizer.set_state(self.last_playing, self.last_value)
            if self.last_position is not None:
                self.fake_visualizer.set_position(self.last_position)
            if self.last_track is not None:
                self.fake_visualizer.load_mp3(self.last_track)

        return result

    def setup(self):
        vis = settings.value(SettingKeys.VISUALIZER, "FAKE", type=str)

        self.fake_visualizer = None
        self.video_frame = None
        self.visualizer = None

        if vis == "VLC":
            self.video_frame = VisualizerFrame()
            self.engine.attach_video_frame(self.video_frame)
            return self.video_frame
        elif vis == "FAKE":
            self.fake_visualizer = VisualizerWidget()
            return self.fake_visualizer
        else:
            self.visualizer = QWidget()
            return self.visualizer

    def set_state(self, playing, value):
        self.last_playing = playing
        self.last_value = value
        if self.fake_visualizer is not None:
            self.fake_visualizer.set_state(playing, value)

    def set_position(self, pos: int):
        self.last_position = pos
        if self.fake_visualizer is not None:
            self.fake_visualizer.set_position(pos)

    def load_mp3(self, track_path: str | PathLike[str]):
        self.last_track = track_path
        if self.fake_visualizer is not None:
            self.fake_visualizer.load_mp3(track_path)


class VisualizerFrame(QFrame):
    resized = Signal(QSize)

    def __init__(self, parent=None):
        super(VisualizerFrame, self).__init__(parent)
        self.setAutoFillBackground(True)

    def resizeEvent(self, event: QResizeEvent):
        self.resized.emit(event.size())
        super().resizeEvent(event)


class StarRating:
    """ Handle the actual painting of the stars themselves. """

    def __init__(self):

        # Create the star shape we'll be drawing.
        self._star_polygon = QPolygonF()
        self._star_polygon.append(QPointF(1.0, 0.5))
        for i in range(1, 5):
            self._star_polygon.append(QPointF(0.5 + 0.5 * math.cos(0.8 * i * math.pi),
                                              0.5 + 0.5 * math.sin(0.8 * i * math.pi)))

        # Create the diamond shape we'll show in the editor
        self._diamond_polygon = QPolygonF()
        diamond_points = [QPointF(0.4, 0.5), QPointF(0.5, 0.4),
                          QPointF(0.6, 0.5), QPointF(0.5, 0.6),
                          QPointF(0.4, 0.5)]
        self._diamond_polygon.append(diamond_points)

    def size_hint(self):
        return QSize(PAINTING_SCALE_FACTOR, PAINTING_SCALE_FACTOR)

    def paint(self, painter, filled, rect, palette, brush: QBrush = None):
        """ Paint the stars (and/or diamonds if we're in editing mode). """
        with QPainterStateGuard(painter):
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            if brush is None:
                painter.setBrush(palette.windowText())
            else:
                painter.setBrush(brush)

            rect = rect.adjusted(5, 5, -5, -5)
            y_offset = (rect.height() - PAINTING_SCALE_FACTOR) / 2
            painter.translate(rect.x(), rect.y() + y_offset)
            painter.scale(PAINTING_SCALE_FACTOR, PAINTING_SCALE_FACTOR)

            if filled:
                painter.drawPolygon(self._star_polygon, Qt.FillRule.OddEvenFill)
            else:
                painter.drawPolygon(self._star_polygon, Qt.FillRule.WindingFill)


class QJumpSlider(QSlider):
    def __init__(self, parent=None):
        super(QJumpSlider, self).__init__(parent)

        # Animation
        self.setMouseTracking(True)
        self._glow_size = 0
        self.max_glow_size = 3.0

        # Setup Animation
        self.ani = QPropertyAnimation(self, b"glow_size")
        self.ani.setDuration(200)
        self.ani.setEasingCurve(QEasingCurve.Type.OutCubic)

    @Property(float)
    def glow_size(self):
        return self._glow_size

    @glow_size.setter
    def glow_size(self, value):
        self._glow_size = value
        self.update()  # Force repaint with new animation value

    def animate_glow(self, target):
        if self.ani.endValue() != target:
            self.ani.stop()
            self.ani.setEndValue(target)
            self.ani.start()

    def enterEvent(self, event):
        # self.animate_glow(self.max_glow_size /2)  # Subtle hover glow
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Only shrink if we aren't currently holding the mouse button down
        if not self.isSliderDown():
            self.animate_glow(0.0)
        super().leaveEvent(event)

    def _roundStep(self, a, stepSize):
        return round(float(a) / stepSize) * stepSize

    def mousePressEvent(self, event):
        # handle glow size
        # self.animate_glow(self.max_glow_size)  # Intense press glow
        # Jump to click position
        self.setSliderDown(True)
        if self.orientation() == Qt.Orientation.Vertical:
            value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.position().y(), self.height(),
                                                   not self.invertedAppearance())
        else:
            value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.position().x(), self.width(),
                                                   self.invertedAppearance())

        value = self._roundStep(value, self.singleStep())

        self.setValue(value)

    def mouseReleaseEvent(self, event):
        # handle glow size
        if not self.underMouse():
            self.animate_glow(0.0)
        #
        self.setSliderDown(False)

    def mouseMoveEvent(self, event):
        low = self.minimum()
        high = self.maximum()
        progress = (self.sliderPosition() - low) / (high - low) if high > low else 0
        progress_x = self.width() * progress

        if abs(progress_x - event.position().x()) < 6:
            self.animate_glow(self.max_glow_size)
        else:
            self.animate_glow(0)

        if self.isSliderDown():
            # Jump to pointer position while moving

            if self.orientation() == Qt.Orientation.Vertical:
                value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.position().y(),
                                                       self.height(), not self.invertedAppearance())
            else:
                value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.position().x(),
                                                       self.width(), self.invertedAppearance())

            value = self._roundStep(value, self.singleStep())
            self.setValue(value)


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


class CategorySlider(QVBoxLayout):
    valueChanged = Signal(int)
    _blockSignals = False

    def __init__(self, category=None, parent=None, minValue=0, maxValue=10):
        super(CategorySlider, self).__init__(parent)

        self.label = QLabel(category)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setToolTip(get_category_description(category))

        self.slider = QJumpSlider(Qt.Orientation.Vertical)
        self.slider.setRange(minValue, maxValue)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBothSides)
        self.slider.setTickInterval(1)
        self.slider.setPageStep(1)
        self.slider.setInvertedAppearance(False)

        self.val_label = QLabel("")
        self.val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.val_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.slider.valueChanged.connect(self._forward_value_changed)

        self.addWidget(self.label)
        self.addWidget(self.slider, 0, Qt.AlignmentFlag.AlignHCenter)
        self.addWidget(self.val_label)

    def _forward_value_changed(self, value: int):
        self.update_value_label()
        if not self._blockSignals:
            self.valueChanged.emit(value)

    def blockSignals(self, block: bool = True):
        self._blockSignals = block

    def update_value_label(self):
        if self.value():
            self.val_label.setText(str(self.slider.value()))
        else:
            self.val_label.setText("")

    def setValue(self, value, signal: bool = True):
        if not signal:
            original_block_signals: bool = self._blockSignals
            self._blockSignals = True

        self.slider.setValue(value)

        if not signal:
            self._blockSignals = original_block_signals
            self.update_value_label()

    def value(self):
        return self.slider.value()


class QToggle(QCheckBox):
    _ANIMATION_DURATION = 200  # Time in ms.
    _HANDLE_REL_SIZE = 0.82
    _PREFERRED_HEIGHT = 28
    _TEXT_SIDE_PADDING = 4

    def __init__(self, checkedText="", uncheckedText="", fontHeightRatio=0.5,
                 parent=None):
        super().__init__(parent=parent)
        assert (0 < fontHeightRatio <= 1)

        self._checkedText = checkedText
        self._uncheckedText = uncheckedText
        self._fontHeightRatio = fontHeightRatio

        self._handlePositionMultiplier = 0

        self._animation = QPropertyAnimation(self, b"handlePositionMultiplier")
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.setDuration(self._ANIMATION_DURATION)

        self.stateChanged.connect(self._on_state_changed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_text()

    def _update_text(self):
        self.setText(self._checkedText if self.isChecked() else self._uncheckedText)

    @Property(float)
    def handlePositionMultiplier(self):
        return self._handlePositionMultiplier

    @handlePositionMultiplier.setter
    def handlePositionMultiplier(self, handlePositionMultiplier):
        self._handlePositionMultiplier = handlePositionMultiplier
        self.update()

    def sizeHint(self):
        maxTextWidth = float("-inf")
        for text in [self._checkedText, self._uncheckedText]:
            textSize = self.fontMetrics().size(Qt.TextFlag.TextSingleLine, text)
            maxTextWidth = max(maxTextWidth, textSize.width())

        # We use _PREFERRED_HEIGHT to prevent users from shooting themselves in the foot (visually).
        preferredHeight = max(self.minimumHeight(), self._PREFERRED_HEIGHT)

        # The 1.2 is a magic number creating some padding for the text so
        # that big letters do not overflow the rounded corners.
        return QSize(preferredHeight + maxTextWidth * 1.2 + self._TEXT_SIDE_PADDING, preferredHeight)

    def hitButton(self, pos):
        """ Define the clickable area of the checkbox.
        """
        return self.contentsRect().contains(pos)

    def _on_state_changed(self, state):
        self._animation.stop()
        if bool(state):
            self._animation.setEndValue(1)
        else:
            self._animation.setEndValue(0)
        self._animation.start()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = painter.font()
        font.setBold(True)
        if font.pixelSize() > 2:
            font.setPixelSize(font.pixelSize() - 2)
        painter.setFont(font)

        contRect = self.contentsRect()
        diameter = contRect.height()
        radius = diameter / 2

        # Determine current text based on handle position
        # during the animation - switch it right in the middle.
        if self._handlePositionMultiplier > 0.5:
            currentText = self._checkedText
        else:
            currentText = self._uncheckedText

        # Determine used brushes based on check state.
        if self.isChecked():
            bodyBrush = self._get_checked_body_brush()
            handleBrush = self._get_checked_handle_brush()
        else:
            bodyBrush = self._get_unchecked_body_brush()
            handleBrush = self._get_unchecked_handle_brush()

        # Draw the toggle's body.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bodyBrush)
        painter.drawRoundedRect(contRect, radius, radius)
        painter.setPen(QPen(handleBrush.color().darker(110)))
        painter.setBrush(handleBrush)

        # Draw the text.
        painter.save()
        textPosMultiplier = (1.0 - self._handlePositionMultiplier)
        textRectX = int(diameter * textPosMultiplier + self._TEXT_SIDE_PADDING * self._handlePositionMultiplier)
        textRectWidth = contRect.width() - diameter - self._TEXT_SIDE_PADDING
        textRect = QRect(textRectX, 0, textRectWidth, contRect.height())
        if self.isEnabled():
            # Trick for fading the text through the handle during transition.
            textOpacity = abs(0.5 - self._handlePositionMultiplier) * 2
        else:
            # Override text opacity for disabled toggle.
            textOpacity = 0.5
        painter.setBrush(Qt.BrushStyle.NoBrush)

        text_color = (QColor(self.palette().color(QPalette.ColorRole.Text)))
        text_color.setAlphaF(textOpacity)

        painter.setPen(QPen(text_color))
        painter.drawText(textRect, Qt.AlignmentFlag.AlignCenter, currentText)
        painter.restore()

        # Adjust the handle drawing brush if the toggle is not enabled.
        if not self.isEnabled():
            newColor = painter.brush().color()
            newColor.setAlphaF(0.5)
            painter.setBrush(QBrush(newColor))

        # Draw the handle.
        travelDistance = contRect.width() - diameter
        handlePosX = contRect.x() + radius + travelDistance * self._handlePositionMultiplier
        handleRadius = self._HANDLE_REL_SIZE * radius
        painter.drawEllipse(QPointF(handlePosX, contRect.center().y() + 1), handleRadius, handleRadius)

        painter.restore()

    def setChecked(self, checked):
        super().setChecked(checked)
        # Ensure we are in the finished animation state if there are signals blocked from the outside!
        if self.signalsBlocked():
            self._handlePositionMultiplier = 1 if checked else 0
            # Ensure the toggle is updated visually even though it seems this is not necessary.
            self.update()
        self._update_text()

    def setCheckedNoAnim(self, checked):
        self._animation.setDuration(0)
        self.setChecked(checked)
        self._animation.setDuration(self._ANIMATION_DURATION)

    def _get_checked_handle_brush(self):
        if isinstance(self.palette().accent(), QBrush):
            return self.palette().accent()
        else:
            return QBrush(self.palette().accent())

    def _get_checked_body_brush(self):
        if isinstance(self.palette().accent(), QBrush):
            return QBrush(self.palette().accent().color().lighter(170))
        else:
            return QBrush(self.palette().accent().lighter(170))

    def _get_unchecked_handle_brush(self):
        if isinstance(self.palette().button(), QBrush):
            return self.palette().button()
        else:
            return QBrush(self.palette().button())

    def _get_unchecked_body_brush(self):
        if isinstance(self.palette().button(), QBrush):
            return QBrush(self.palette().button().color().lighter(170))
        else:
            return QBrush(self.palette().button().lighter(170))

class VisualizerWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(40)
        self.setContentsMargins(4, 4, 4, 4)
        self.playing = False
        self.sleeping = True
        self.amplitude = 0
        self.bars = 30
        self.values = [0.0] * self.bars

        self.hop_length_secs = 1 / 30
        self.timer = QTimer(self)

        self.timer.timeout.connect(self.update_fake_visualization)
        self.timer.start(int(self.hop_length_secs * 1000))

    def load_mp3(self, filename):
        # not needed for fake one
        return

    def set_position(self, position_0_1000):
        # not needed for fake one
        return

    def set_state(self, is_playing, volume):
        self.playing = is_playing
        self.amplitude = volume / 100.0

    def update_fake_visualization(self):
        if self.playing:
            # Simulate spectrum data
            for i in range(self.bars):
                # Random noise smoothed by amplitude
                target = random.random() * self.amplitude
                # Simple decay/attack smoothing
                self.values[i] = (self.values[i] * 0.8) + (target * 0.2)
        else:
            # Decay to zero
            for i in range(self.bars):
                self.values[i] *= 0.85

        self.update()  # Trigger paintEvent

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width() - self.contentsMargins().left() - self.contentsMargins().right()
        h = self.height() - self.contentsMargins().top() - self.contentsMargins().bottom()

        base_color = QColor(self.palette().base().color())
        base_color.setAlpha(100)

        painter.fillRect(self.rect(), base_color)

        bar_width = w / self.bars

        # Gradient brush for a modern look
        gradient = QLinearGradient(0, h, 0, 0)
        gradient.setColorAt(0.0, _green)  # Green
        gradient.setColorAt(0.4, _yellow)  # yellow
        gradient.setColorAt(0.6, _orange)  # Orange
        gradient.setColorAt(1.0, _red)  # Red

        for i, val in enumerate(self.values):
            bar_h = max(1, int(val * h * 1.2))  # make the bars fill up more space by using factor 1.2
            x = self.contentsMargins().left() + i * bar_width
            y = self.contentsMargins().top() + h - bar_h

            painter.fillRect(int(x), int(y), int(bar_width - 2), int(bar_h), gradient)
