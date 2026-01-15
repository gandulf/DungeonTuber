from enum import StrEnum

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, Property, QEasingCurve, QPointF, QRect, QSize, QPoint, QTimer
from PySide6.QtGui import QMouseEvent, QBrush, QPen, QColor, QPalette, QPainter, QIcon, QLinearGradient, QPolygon, QFontMetrics, QPaintEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QSlider, QVBoxLayout, QStyle, QCheckBox, QPushButton, QHBoxLayout, QProxyStyle, QWidget, \
    QGraphicsOpacityEffect

from config.settings import MusicCategory
from config.theme import app_theme

class JumpSlider(QSlider):
    mouse_pressed = Signal(QMouseEvent)
    mouse_released = Signal(QMouseEvent)

    def __init__(self, parent=None):
        super(JumpSlider, self).__init__(parent)
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

    def _roundStep(self, a, step_size):
        return round(float(a) / step_size) * step_size

    def mousePressEvent(self, event: QMouseEvent):
        self.mouse_pressed.emit(event)
        if event.button() == Qt.MouseButton.LeftButton:
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

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.mouse_released.emit(event)
        if event.button() == Qt.MouseButton.LeftButton:
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

            self.setValue(self._roundStep(value, self.singleStep()))


class CategoryTooltip(QWidget):

    __parent: QWidget

    def __init__(self, parent: QWidget):
        super(CategoryTooltip, self).__init__(None)

        self.__parent = parent
        self.setWindowFlags(
            Qt.WindowType.ToolTip |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setPalette(parent.palette())
        self.setStyle(parent.style())
        self.setContentsMargins(8,8,8,8)
        self.setHidden(True)
        self.__opacity_effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.__opacity_effect)

        self.__current_opacity = 0.0

        self._auto_hidden=False

        self.__show_delay = 100
        self.__hide_delay = 100
        self.__fade_in_duration = 150
        self.__fade_out_duration = 150
        self.__fade_in_easing_curve = QEasingCurve.Type.Linear
        self.__fade_out_easing_curve = QEasingCurve.Type.Linear

        self.__text_widget = QLabel(self)
        self.__text_widget.setText("")

        self.__text_widget.setStyleSheet(f"font-size: {app_theme.font_size*0.8}px")
        self.__text_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.__fade_in_animation = QPropertyAnimation(self.__opacity_effect, b'opacity')
        self.__fade_in_animation.setDuration(self.__fade_in_duration)
        self.__fade_in_animation.setEasingCurve(self.__fade_in_easing_curve)
        self.__fade_in_animation.valueChanged.connect(self.__update_current_opacity)
        #self.__fade_in_animation.finished.connect(self.__start_duration_timer)

        self.__fade_out_animation = QPropertyAnimation(self.__opacity_effect, b'opacity')
        self.__fade_out_animation.setDuration(self.__fade_out_duration)
        self.__fade_out_animation.setEasingCurve(self.__fade_out_easing_curve)
        self.__fade_out_animation.valueChanged.connect(self.__update_current_opacity)
        self.__fade_out_animation.finished.connect(self.__hide)

        self.__show_delay_timer = QTimer(self)
        self.__show_delay_timer.setInterval(self.__show_delay)
        self.__show_delay_timer.setSingleShot(True)
        self.__show_delay_timer.timeout.connect(self.__start_fade_in)

        self.__hide_delay_timer = QTimer(self)
        self.__hide_delay_timer.setInterval(self.__hide_delay)
        self.__hide_delay_timer.setSingleShot(True)
        self.__hide_delay_timer.timeout.connect(self.__start_fade_out)

    def __hide(self):
        """Hide the tooltip"""

        super().hide()

    def __update_current_opacity(self, value: float):
        """Update the current_opacity attribute with the new value of the animation

        :param value: value received by the valueChanged event
        """

        self.__current_opacity = value

    def __start_show_delay(self):
        """Start a delay that will start the fade in animation when finished"""

        self.__hide_delay_timer.stop()
        self.__show_delay_timer.start()

    def __start_hide_delay(self):
        """Start a delay that will start the fade out animation when finished"""

        self.__show_delay_timer.stop()
        self.__hide_delay_timer.start()

    def __start_fade_out(self):
        """Start the fade out animation"""

        self.__fade_out_animation.setStartValue(self.__current_opacity)
        self.__fade_out_animation.setEndValue(0)
        self.__fade_out_animation.start()

    def __start_fade_in(self):
        # Start fade in animation and show
        self.__fade_in_animation.setStartValue(self.__current_opacity)
        self.__fade_in_animation.setEndValue(1)
        self.__fade_in_animation.start()
        super().show()

    def paintEvent(self, event: QPaintEvent):
        super(CategoryTooltip, self).paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QBrush(QColor(self.palette().color(QPalette.ColorRole.Base))))
        painter.drawRoundedRect(self.rect(),4.0,4.0)

    def setText(self, text: str):
        self.__text_widget.setStyleSheet(f"font-size: {app_theme.font_size * 0.8}px")

        if self.isVisible() and text == "":
            self._auto_hidden = True
            self.hide()
        else:
            self.__text_widget.setText(text)
            self._update_ui()
            if not self.isVisible() and self._auto_hidden == True and text != "":
                self.show()
                self._auto_hidden = False
        return

    def _update_ui(self, text:str = None):
        pos = self.__parent.mapToGlobal(self.__parent.rect().topLeft())

        if text is None:
            text = self.__text_widget.text()

        fm = QFontMetrics(self.__text_widget.font())
        rect = fm.boundingRect(text)
        rect = rect.marginsAdded(self.__text_widget.contentsMargins())
        rect = rect.marginsAdded(self.contentsMargins())
        self.__text_widget.resize(rect.size())
        self.resize(rect.size())
        pos.setX(pos.x() - self.width() / 2 + self.__parent.width() /2)
        pos.setY(pos.y() + self.height() + self.__parent.height() -8)
        self.move(pos)


    def show(self, delay: bool = False):
        """Start the process of showing the tooltip

        :param delay: whether the tooltip should be shown with the delay (default: False)
        """
        self._update_ui()

        if delay:
            self.__start_show_delay()
        else:
            self.__start_fade_in()

    def hide(self, delay: bool = False):
        """Start the process of hiding the tooltip

        :param delay: whether the tooltip should be hidden with the delay (default: False)
        """
        self.__show_delay_timer.stop()
        self.__fade_in_animation.stop()

        if delay:
            self.__start_hide_delay()
        else:
            self.__start_fade_out()





class CategoryWidget(QVBoxLayout):
    valueChanged = Signal(int)
    _block_signals = False
    _orig_value: int

    def __init__(self, category: MusicCategory = None, parent=None, min_value=0, max_value=10):
        super(CategoryWidget, self).__init__(parent)

        self.category = category
        self.label = QLabel(category.name)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setToolTip(category.get_detailed_description())

        self.slider = JumpSlider(Qt.Orientation.Vertical)
        self.slider.setRange(min_value, max_value)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBothSides)
        self.slider.setTickInterval(1)
        self.slider.setPageStep(1)
        self.slider.setInvertedAppearance(False)
        self.slider.valueChanged.connect(self._forward_value_changed)
        self.slider.mouse_pressed.connect(self.mouse_down)
        self.slider.mouse_released.connect(self.mouse_up)

        # Add tooltip to button
        self.tooltip = CategoryTooltip(self.slider)

        self.val_label = QLabel("")
        self.val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.val_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.addWidget(self.label)
        self.addWidget(self.slider, 0, Qt.AlignmentFlag.AlignHCenter)
        self.addWidget(self.val_label)

    def mouse_down(self, event: QMouseEvent):
        self.refresh_tooltip(True)

        self.blockSignals()
        self._orig_value = self.value()


    def mouse_up(self, event: QMouseEvent):
        self.unblockSignals()
        self.tooltip.hide()

        if self._orig_value is None or self.value() != self._orig_value:
            self.valueChanged.emit(self.value())

    def _forward_value_changed(self, value: int):
        self.update_value_label(value)

        if not self._block_signals:
            self.valueChanged.emit(value)

    def blockSignals(self, block: bool = True):
        self._block_signals = block

    def unblockSignals(self):
        self._block_signals = False

    def refresh_tooltip(self, show: bool = True):
        nearest_level = min(self.category.levels.keys(), key=lambda x: abs(int(x) - self.value()))
        text = self.category.levels.get(nearest_level, "")
        self.tooltip.setText(text)

        if text != "" and show and self.tooltip.isHidden():
            self.tooltip.show(True)


    def update_value_label(self, value: int = None):
        if value is None:
            value = self.slider.value()

        if value:
            self.val_label.setText(str(value))
            self.refresh_tooltip(False)
        else:
            self.val_label.setText("")
            self.tooltip.setText("")

    def set_value(self, value, signal: bool = True):
        _original_block_signals = False
        if not signal:
            _original_block_signals: bool = self._block_signals
            self._block_signals = True

        value = value if value is not None else 0

        self.slider.setValue(value)

        if not signal:
            self._block_signals = _original_block_signals
            self.update_value_label(value)

    def value(self):
        return self.slider.value()


class ToggleSlider(QCheckBox):
    _ANIMATION_DURATION = 200  # Time in ms.
    _HANDLE_REL_SIZE = 0.82
    _PREFERRED_HEIGHT = 28
    _TEXT_SIDE_PADDING = 4

    def __init__(self, checked_text="", unchecked_text="", font_height_ratio=0.5,
                 parent=None):
        super().__init__(parent=parent)
        assert (0 < font_height_ratio <= 1)

        self._checked_text = checked_text
        self._unchecked_text = unchecked_text
        self._font_height_ratio = font_height_ratio

        self._handle_position_multiplier = 0

        self._animation = QPropertyAnimation(self, b"handlePositionMultiplier")
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.setDuration(self._ANIMATION_DURATION)

        self.stateChanged.connect(self._on_state_changed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_text()

    def _update_text(self):
        self.setText(self._checked_text if self.isChecked() else self._unchecked_text)

    @Property(float)
    def handlePositionMultiplier(self):
        return self._handle_position_multiplier

    @handlePositionMultiplier.setter
    def handlePositionMultiplier(self, handlePositionMultiplier):
        self._handle_position_multiplier = handlePositionMultiplier
        self.update()

    def sizeHint(self):
        max_text_width = float("-inf")
        for text in [self._checked_text, self._unchecked_text]:
            text_size = self.fontMetrics().size(Qt.TextFlag.TextSingleLine, text)
            max_text_width = max(max_text_width, text_size.width())

        # We use _PREFERRED_HEIGHT to prevent users from shooting themselves in the foot (visually).
        preferred_height = max(self.minimumHeight(), self._PREFERRED_HEIGHT)

        # The 1.2 is a magic number creating some padding for the text so
        # that big letters do not overflow the rounded corners.
        return QSize(preferred_height + max_text_width * 1.2 + self._TEXT_SIDE_PADDING, preferred_height)

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

        content_rect = self.contentsRect()
        diameter = content_rect.height()
        radius = diameter / 2

        # Determine current text based on handle position
        # during the animation - switch it right in the middle.
        if self._handle_position_multiplier > 0.5:
            current_text = self._checked_text
        else:
            current_text = self._unchecked_text

        # Determine used brushes based on check state.
        if self.isChecked():
            body_brush = self._get_checked_body_brush()
            handle_brush = self._get_checked_handle_brush()
        else:
            body_brush = self._get_unchecked_body_brush()
            handle_brush = self._get_unchecked_handle_brush()

        # Draw the toggle's body.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(body_brush)
        painter.drawRoundedRect(content_rect, radius, radius)
        painter.setPen(QPen(handle_brush.color().darker(110)))
        painter.setBrush(handle_brush)

        # Draw the text.
        painter.save()
        text_pos_multiplier = (1.0 - self._handle_position_multiplier)
        text_rect_x = int(diameter * text_pos_multiplier + self._TEXT_SIDE_PADDING * self._handle_position_multiplier)
        text_rect_width = content_rect.width() - diameter - self._TEXT_SIDE_PADDING
        text_rect = QRect(text_rect_x, 0, text_rect_width, content_rect.height())
        if self.isEnabled():
            # Trick for fading the text through the handle during transition.
            text_opacity = abs(0.5 - self._handle_position_multiplier) * 2
        else:
            # Override text opacity for disabled toggle.
            text_opacity = 0.5
        painter.setBrush(Qt.BrushStyle.NoBrush)

        text_color = (QColor(self.palette().color(QPalette.ColorRole.Text)))
        text_color.setAlphaF(text_opacity)

        painter.setPen(QPen(text_color))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, current_text)
        painter.restore()

        # Adjust the handle drawing brush if the toggle is not enabled.
        if not self.isEnabled():
            new_color = painter.brush().color()
            new_color.setAlphaF(0.5)
            painter.setBrush(QBrush(new_color))

        # Draw the handle.
        travel_distance = content_rect.width() - diameter
        handle_pos_x = content_rect.x() + radius + travel_distance * self._handle_position_multiplier
        handle_radius = self._HANDLE_REL_SIZE * radius
        painter.drawEllipse(QPointF(handle_pos_x, content_rect.center().y() + 1), handle_radius, handle_radius)

        painter.restore()

    def setChecked(self, checked):
        super().setChecked(checked)
        # Ensure we are in the finished animation state if there are signals blocked from the outside!
        if self.signalsBlocked():
            self._handle_position_multiplier = 1 if checked else 0
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


class VolumeSliderStyle(QProxyStyle):
    def drawComplexControl(self, control, option, painter: QPainter, widget: JumpSlider = None):
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
    volume_changed = Signal(int)

    def __init__(self, value: int = 70):
        super(VolumeSlider, self).__init__()
        self.btn_volume = QPushButton()
        self.btn_volume.setFixedSize(QSize(app_theme.button_size, app_theme.button_size))
        self.btn_volume.setIconSize(QSize(app_theme.icon_size, app_theme.icon_size))
        self.btn_volume.clicked.connect(self.toggle_mute)
        self._update_volume_icon(value)
        self.addWidget(self.btn_volume,0)

        self.slider_vol = JumpSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(value)
        self.slider_vol.setMinimumWidth(100)
        self.slider_vol.setFixedHeight(app_theme.button_size)
        self.slider_vol.max_glow_size = 2
        self.slider_vol.valueChanged.connect(self._on_value_changed)
        self.slider_vol.setStyle(VolumeSliderStyle())
        self.slider_vol.setSingleStep(5)
        self.addWidget(self.slider_vol, 1)

    @Property(int, notify=volume_changed)
    def volume(self):
        return self.slider_vol.value()

    @volume.setter
    def volume(self, value):
        self.slider_vol.setValue(value)
        self._update_volume_icon(value)

    def _on_value_changed(self, value):
        self._update_volume_icon(value)
        self.volume_changed.emit(value)

    def set_button_size(self, button_size: QSize):
        self.btn_volume.setFixedSize(button_size)

    def set_icon_size(self, icon_size: QSize):
        self.btn_volume.setIconSize(icon_size)

    def toggle_mute(self):
        if self.slider_vol.value() > 0:
            self.last_volume = self.slider_vol.value()
            self.slider_vol.setValue(0)
        else:
            self.slider_vol.setValue(self.last_volume)

        self.volume_changed.emit(self.slider_vol.value())

    def _update_volume_icon(self, volume):
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

    value_changed = Signal(RepeatMode)

    def __init__(self, value: int | RepeatMode = RepeatMode.NO_REPEAT, parent=None):
        super(RepeatButton, self).__init__(parent)

        if isinstance(value, RepeatMode):
            self._repeat_mode = value
        else:
            self._repeat_mode = self.REPEAT_MODES[int(value)]

        self.clicked.connect(self.cycle_repeat_mode)
        self.update_repeat_button()

    def cycle_repeat_mode(self):
        repeat_mode_index = (self.REPEAT_MODES.index(self._repeat_mode) + 1) % len(self.REPEAT_MODES)
        self._repeat_mode = self.REPEAT_MODES[repeat_mode_index]
        self.update_repeat_button()

        self.value_changed.emit(self._repeat_mode)

    def set_repeat_mode(self, repeat_mode):
        self._repeat_mode = repeat_mode
        self.value_changed.emit(self._repeat_mode)

    def repeat_mode(self):
        return self._repeat_mode

    def update_repeat_button(self):
        self.setToolTip(self._repeat_mode)

        if self._repeat_mode == RepeatMode.NO_REPEAT:
            self.setIcon(self.icon_no_repeat)
        elif self._repeat_mode == RepeatMode.REPEAT_SINGLE:
            self.setIcon(self.icon_repeat_1)
        elif self._repeat_mode == RepeatMode.REPEAT_ALL:
            self.setIcon(self.icon_repeat_all)
