from enum import StrEnum

from PySide6.QtCore import QPointF, QSize, Qt, QRect, Signal, QPropertyAnimation, QEasingCurve, Property, QEvent, \
    QPoint, QObject, QSortFilterProxyModel, QTimer, QKeyCombination, QMimeData, QByteArray
from PySide6.QtGui import QIcon, QBrush, QPainter, QMouseEvent, QColor, \
    QPaintEvent, QFontMetrics, QFont, QKeyEvent, QPen, QPalette, QLinearGradient, QPolygon, QAction, QKeySequence, QShortcut, QDrag, QPixmap
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSpacerItem, QPushButton, QAbstractScrollArea, QLayout, QSizePolicy, QSlider, QVBoxLayout, QStyle, \
    QCheckBox, QProxyStyle, QGraphicsOpacityEffect, QDial, QToolButton, QApplication, QColorDialog

from config.settings import MusicCategory
from config.theme import app_theme


class IconLabel(QWidget):
    icon_size = QSize(16, 16)
    horizontal_spacing = 2

    clicked = Signal()

    def mousePressEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def __init__(self, icon: QIcon, text: str, final_stretch: bool = True, parent: QWidget = None):
        super(IconLabel, self).__init__(parent)

        self.layout = QHBoxLayout(self)
        self.layout.setObjectName("IconLabel_layout")
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.icon = icon
        self.icon_label = QLabel(self)
        if icon is not None:
            self.icon_label.setPixmap(icon.pixmap(self.icon_size))
            self.icon_label.setVisible(True)
            self.icon_label.setContentsMargins(0, 0, 4, 0)
        else:
            self.icon_label.setVisible(False)

        self.layout.addWidget(self.icon_label)
        self.layout.addSpacing(self.horizontal_spacing)

        self.text_label = QLabel(text, self)
        self.text_label.setOpenExternalLinks(True)
        self.layout.addWidget(self.text_label)

        if final_stretch:
            self.layout.addStretch()

    def set_icon_size(self, size: QSize):
        self.icon_label.setPixmap(self.icon.pixmap(size))

    def add_widget(self, widget: QWidget, stretch: int = 0):
        self.layout.addWidget(widget, stretch)

    def insert_widget(self, index: int, widget: QWidget, stretch: int = 0):
        self.layout.insertWidget(index, widget, stretch)

    def set_alignment(self, alignment: Qt.AlignmentFlag):
        self.text_label.setAlignment(alignment)

        if alignment == Qt.AlignmentFlag.AlignCenter:
            if not isinstance(self.layout.itemAt(0), QSpacerItem):
                self.layout.insertStretch(0)
        elif isinstance(self.layout.itemAt(0), QSpacerItem):
            spacer = self.layout.takeAt(0)

    def set_style_sheet(self, stylesheet: str):
        self.text_label.setStyleSheet(stylesheet)

    def set_text(self, text: str):
        self.text_label.setText(text)

    def set_icon(self, icon: QIcon):
        if icon is not None:
            self.icon_label.setPixmap(icon.pixmap(self.icon_size))
            self.icon_label.setVisible(True)
        else:
            self.icon_label.setVisible(False)


class FeatureOverlay(QWidget):

    def __init__(self, parent: QWidget | None, steps: list):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self.steps = steps
        self.current_step = 0

        # Highlight rectangle as animatable property
        self._highlight_rect = QRect(0, 0, 0, 0)

        # Help text label
        self.label = QLabel(self)
        self.label.setStyleSheet("color: white;")
        self.label.setWordWrap(True)
        self.label.setContentsMargins(8, 8, 8, 8)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setMinimumWidth(300)

        # Next button
        self.next_button = QPushButton(_("Next"), self)
        self.next_button.setShortcut(Qt.Key.Key_Enter)
        self.next_button.clicked.connect(self.next_step)

        self.close_button = QPushButton(_("Close"), self)
        self.close_button.setShortcut(Qt.Key.Key_Escape)
        self.close_button.clicked.connect(self.close)

        # Track parent changes
        self.parent().installEventFilter(self)

        self.setGeometry(parent.geometry())
        self.show()
        self.show_step(initial=True)

        # Animatable property

    def get_highlight_rect(self) -> QRect:
        return self._highlight_rect

    def set_highlight_rect(self, rect: QRect):
        self._highlight_rect = rect
        self.update_label_button()
        self.update()

    highlight_rect = Property(QRect, get_highlight_rect, set_highlight_rect)

    def update_label_button(self, position: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignBottom):
        label_padding = 16

        parent_rect = self.parent().rect()
        highlight_rect: QRect = self.get_highlight_rect()

        self.label.setMinimumWidth(max(300, self._highlight_rect.width()))

        button_group_right = QHBoxLayout()
        if self.current_step < len(self.steps):
            self.label.setText(self.steps[self.current_step]['message'])
            self.label.adjustSize()

        if self.current_step == len(self.steps) - 1:
            self.next_button.setText(_("Ok"))
            self.close_button.setVisible(False)
        else:
            self.next_button.setText(_("Next"))
            self.close_button.setVisible(True)

        if position == Qt.AlignmentFlag.AlignBottom:
            if highlight_rect.bottom() + self.label.height() + self.next_button.height() + label_padding > parent_rect.bottom():
                self.update_label_button(Qt.AlignmentFlag.AlignRight)
                return
            self.label.move(highlight_rect.left(), highlight_rect.bottom() + label_padding)
        elif position == Qt.AlignmentFlag.AlignRight:
            if highlight_rect.right() + self.label.width() > parent_rect.right():
                self.update_label_button(Qt.AlignmentFlag.AlignLeft)
                return
            self.label.move(highlight_rect.right() + label_padding, highlight_rect.top())
        elif position == Qt.AlignmentFlag.AlignLeft:
            if highlight_rect.left() - self.label.width() < parent_rect.left():
                self.update_label_button(Qt.AlignmentFlag.AlignTop)
                return
            self.label.move(highlight_rect.left() - self.label.width() - label_padding, highlight_rect.top())
        else:
            self.label.move(highlight_rect.left(), highlight_rect.top() - self.label.height() - label_padding - self.next_button.height() - label_padding)

        # Position button below label
        self.next_button.move(self.label.geometry().right() - self.next_button.width(), self.label.geometry().bottom() + label_padding)
        self.close_button.move(self.label.geometry().left(), self.label.geometry().bottom() + label_padding)

    def compute_highlight_rect(self, widget: QWidget):
        """
        Returns the QRect of the widget relative to the overlay,
        accounting for window frame, DPI, and any layout offsets.
        """
        # Map the widget's top-left to global coordinates
        top_left_global = widget.mapToGlobal(QPoint(0, 0))
        bottom_right_global = widget.mapToGlobal(QPoint(widget.width(), widget.height()))

        # Convert global coordinates to overlay coordinates
        top_left_overlay = self.mapFromGlobal(top_left_global)
        bottom_right_overlay = self.mapFromGlobal(bottom_right_global)

        rect = QRect(top_left_overlay, bottom_right_overlay)
        return rect

    def show_step(self, initial=False):
        if self.current_step >= len(self.steps):
            self.close()
            return

        step = self.steps[self.current_step]
        widget = step['widget']

        if widget is None or not widget.isVisible() or not widget.isEnabled():
            self.next_step()
            return

        # Correct mapping: widget -> overlay coordinates
        target_rect = self.compute_highlight_rect(widget)

        if initial:
            # Jump immediately
            self.set_highlight_rect(target_rect)
        else:
            # Animate highlight rectangle
            self.anim = QPropertyAnimation(self, b"highlight_rect")
            self.anim.setDuration(500)
            self.anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            self.anim.setStartValue(self._highlight_rect)
            self.anim.setEndValue(target_rect)
            self.anim.start()

    def next_step(self):
        self.current_step += 1
        self.show_step()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))

        # Clear highlight area
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.setBrush(QBrush(Qt.BrushStyle.SolidPattern))
        painter.drawRoundedRect(self._highlight_rect, 8, 8)
        painter.restore()

        # Rounded border around highlight
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(QColor(255, 255, 255))
        painter.drawRoundedRect(self._highlight_rect, 8, 8)

        painter.setBrush(QBrush(QColor(0, 0, 0, 150)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.label.geometry(), 8.0, 8.0)

    def eventFilter(self, obj: QObject, event: QEvent):
        # Update highlight if parent resizes or moves
        if obj == self.parent() and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self.setGeometry(self.parent().geometry())
            self.show_step(initial=True)
        return super().eventFilter(obj, event)

class AutoSearchHelper():
    _ignore_keys = [Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_PageDown, Qt.Key.Key_PageUp, Qt.Key.Key_Home, Qt.Key.Key_End]

    def __init__(self, proxy_model: QSortFilterProxyModel, parent: QAbstractScrollArea = None):
        self.parent = parent
        self.proxy_model = proxy_model
        self.search_string = ""

    def keyPressEvent(self, event: QKeyEvent):
        # If user presses Backspace, remove last char
        if event.key() in self._ignore_keys:
            return False

        if event.key() == Qt.Key.Key_Backspace:
            self.search_string = self.search_string[:-1]
        # If it's a valid character (letter/number), append to search
        elif event.text().isalnum() or event.text() in " _-":
            self.search_string += event.text()
        # If Escape is pressed, clear filter
        elif event.key() == Qt.Key.Key_Escape:
            self.search_string = ""
        else:
            return False

        # Apply the filter to the proxy
        self.proxy_model.setFilterFixedString(self.search_string)

        self.parent.viewport().update()

        return True

    def paintEvent(self, event: QPaintEvent):
        # 2. If there is a search string, draw the popup overlay
        if self.search_string:
            painter = QPainter(self.parent.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Style settings
            font = app_theme.font(False, small=True)
            painter.setFont(font)
            metrics = QFontMetrics(font)

            padding = 10
            text_width = metrics.horizontalAdvance(self.search_string)
            text_height = metrics.height()

            # Calculate the rectangle size and position (Top Right)
            rect_w = text_width + (padding * 2)
            rect_h = text_height + padding
            margin = 10

            popup_rect = QRect(
                self.parent.viewport().width() - rect_w - margin,
                margin,
                rect_w,
                rect_h
            )

            # Draw the background (Semi-transparent dark grey)
            painter.setBrush(QColor(50, 50, 50, 200))
            if self.proxy_model.rowCount() == 0:
                painter.setPen(app_theme.get_red(100))  # Light red border
            else:
                painter.setPen(QColor(200, 200, 200))  # Light border
            painter.drawRoundedRect(popup_rect, 5, 5)

            # Draw the text
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(popup_rect, Qt.AlignmentFlag.AlignCenter, self.search_string)

            painter.end()


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super(FlowLayout, self).__init__(parent)

        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)

        self.setSpacing(spacing)
        self.margin = margin

        # spaces between each item
        self.spaceX = 5
        self.spaceY = 5

        self.item_list: list[QWidget] = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item: QWidget):
        self.item_list.append(item)

    def count(self):
        return len(self.item_list)

    def itemAt(self, index) -> QWidget | None:
        if 0 <= index < len(self.item_list):
            return self.item_list[index]

        return None

    def takeAt(self, index) -> QWidget | None:
        if 0 <= index < len(self.item_list):
            return self.item_list.pop(index)

        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width: int) -> int:
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect: QRect):
        super(FlowLayout, self).setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()

        for item in self.item_list:
            size = size.expandedTo(item.minimumSize())

        size += QSize(2 * self.margin, 2 * self.margin)
        return size

    def doLayout(self, rect: QRect, test_only: bool) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0

        for item in self.item_list:
            next_x = x + item.sizeHint().width() + self.spaceX
            if next_x - self.spaceX > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + self.spaceY
                next_x = x + item.sizeHint().width() + self.spaceX
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()


class BPMSlider(QWidget):
    value_changed = Signal(int)

    _last_changed_bpm = None

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.bpm_widget = QDial()
        self.bpm_widget.setMinimum(0)
        self.bpm_widget.setMaximum(200)
        self.bpm_widget.setSingleStep(20)
        self.bpm_widget.setPageStep(20)
        self.bpm_widget.setNotchesVisible(True)
        self.bpm_widget.setNotchTarget(20.0)
        self.bpm_widget.valueChanged.connect(self._snap_and_update_label)

        self.bpm_label = QLabel("")
        self.bpm_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        bpm_title = QLabel(_("Beats per Minute"))
        bpm_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout.addWidget(bpm_title, 0)
        self.layout.addWidget(self.bpm_widget, 1)
        self.layout.addWidget(self.bpm_label, 0)

    def value(self):
        return self.bpm_widget.value() if self.bpm_widget.value() > 0 else None

    def set_value(self, value):
        self.bpm_widget.setValue(value)

    def reset(self, signal: bool = True):
        originalBlockSignal = self.bpm_widget.signalsBlocked()
        if not signal:
            self.bpm_widget.blockSignals(True)

        self.bpm_widget.setValue(0)

        if not signal:
            self.bpm_label.setText("")
            self.bpm_widget.blockSignals(originalBlockSignal)

    def _snap_and_update_label(self, value):
        """Rounds the dial value to the closest multiple of 20 and updates the label."""

        # Logic to round to the closest multiple of 20
        # Formula: ((x + half_of_step) // step) * step
        snapped_value = ((value + 10) // 20) * 20

        # Ensure the snapped value is within the defined range (40 to 200)
        snapped_value = max(0, min(200, snapped_value))

        # 1. Update the Dial's position (essential for 'snapping' effect)
        # Block signals temporarily to prevent a recursion loop
        if snapped_value != self.bpm_widget.value():
            self.bpm_widget.blockSignals(True)
            self.bpm_widget.setValue(snapped_value)
            self.bpm_widget.blockSignals(False)

        if self._last_changed_bpm is None or self._last_changed_bpm != snapped_value:
            self.value_changed.emit(snapped_value)
            self._last_changed_bpm = snapped_value

        # 2. Update the Label
        if snapped_value > 0:
            self.bpm_label.setText(f"{snapped_value} BPM")
        else:
            self.bpm_label.setText("")


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
        if step_size == 0:
            return a
        else:
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
        self.setContentsMargins(8, 8, 8, 8)
        self.setHidden(True)
        self.__opacity_effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.__opacity_effect)

        self.__current_opacity = 0.0

        self.__show_delay = 100
        self.__hide_delay = 100
        self.__fade_in_duration = 150
        self.__fade_out_duration = 150
        self.__fade_in_easing_curve = QEasingCurve.Type.Linear
        self.__fade_out_easing_curve = QEasingCurve.Type.Linear

        self.__text_widget = QLabel(self)
        self.__text_widget.setText("")
        self.__text_widget.setFont(app_theme.font(small=True))
        self.__text_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.__fade_in_animation = QPropertyAnimation(self.__opacity_effect, b'opacity')
        self.__fade_in_animation.setDuration(self.__fade_in_duration)
        self.__fade_in_animation.setEasingCurve(self.__fade_in_easing_curve)
        self.__fade_in_animation.valueChanged.connect(self.__update_current_opacity)
        # self.__fade_in_animation.finished.connect(self.__start_duration_timer)

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
        # hide empty tooltip
        if self.__text_widget.text() == "":
            return

        super(CategoryTooltip, self).paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QBrush(QColor(self.palette().color(QPalette.ColorRole.Base))))
        painter.drawRoundedRect(self.rect(), 4.0, 4.0)

    def set_text(self, text: str):
        self.__text_widget.setFont(app_theme.font(small=True))
        self.__text_widget.setText(text)
        self._update_ui()

    def _update_ui(self, text: str = None):
        pos = self.__parent.mapToGlobal(self.__parent.rect().topLeft())

        if text is None:
            text = self.__text_widget.text()

        fm = QFontMetrics(self.__text_widget.font())
        rect = fm.boundingRect(text)
        rect = rect.marginsAdded(self.__text_widget.contentsMargins())
        rect = rect.marginsAdded(self.contentsMargins())
        self.__text_widget.resize(rect.size())
        self.resize(rect.size())
        pos.setX(int(pos.x() - self.width() / 2 + self.__parent.width() / 2))
        pos.setY(pos.y() + self.height() + self.__parent.height() - 8)
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


class CategoryWidget(QWidget):
    value_changed = Signal(MusicCategory, object)  # actual int | None but not possible with c++ binding
    _block_signals = False
    _orig_value: int
    _visible_tooltip = False

    _disable_value: int

    def __init__(self, category: MusicCategory = None, parent=None, min_value=0, max_value=10):
        super(CategoryWidget, self).__init__(parent)

        self.layout = QVBoxLayout(self)

        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.category = category
        self.label = QLabel(category.name)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setToolTip(category.get_detailed_description())

        self._disable_value = min_value - 1
        self.slider = JumpSlider(Qt.Orientation.Vertical)
        self.slider.setRange(min_value - 1, max_value)
        self.slider.setValue(self._disable_value)
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

        self.layout.addWidget(self.label)
        self.layout.addWidget(self.slider, 0, Qt.AlignmentFlag.AlignHCenter)
        self.layout.addWidget(self.val_label)

    def mouse_down(self, event: QMouseEvent):
        self._visible_tooltip = True
        self.refresh_tooltip()

        self.blockSignals()
        self._orig_value = self.value()

    def mouse_up(self, event: QMouseEvent):
        self._visible_tooltip = False
        self.unblockSignals()
        self.tooltip.hide()

        if self._orig_value is None or self.value() != self._orig_value:
            self.value_changed.emit(self.category, self.value())

    def _forward_value_changed(self, value: int | None):
        self.update_value_label(value)

        if not self._block_signals:
            self.value_changed.emit(self.category, value)

    def blockSignals(self, block: bool = True):
        self._block_signals = block

    def unblockSignals(self):
        self._block_signals = False

    def refresh_tooltip(self, show: bool = True):
        if self.value() is not None:
            nearest_level = min(self.category.levels.keys(), key=lambda x: abs(int(x) - self.value()))
            self.tooltip.set_text(self.category.levels.get(nearest_level, ""))
        else:
            self.tooltip.set_text("")

        if show and self._visible_tooltip and self.tooltip.isHidden():
            self.tooltip.show(True)

    def update_value_label(self, value: int | None = None):
        if value is None:
            value = self.slider.value()

        if value != self._disable_value:
            self.val_label.setText(str(value))
            self.refresh_tooltip(False)
        else:
            self.val_label.setText("")
            self.tooltip.set_text("")

    def reset(self, signal: bool = True):
        self.set_value(self._disable_value, signal)

    def set_value(self, value, signal: bool = True):
        _original_block_signals = False
        if not signal:
            _original_block_signals: bool = self._block_signals
            self._block_signals = True

        value = value if value is not None else self._disable_value

        self.slider.setValue(value)

        if not signal:
            self._block_signals = _original_block_signals
            self.update_value_label(value)

    def value(self):
        return self.slider.value() if self.slider.value() != self._disable_value else None


class ToggleSlider(QCheckBox):
    _ANIMATION_DURATION = 200  # Time in ms.
    _HANDLE_REL_SIZE = 0.82
    _PREFERRED_HEIGHT = 28
    _TEXT_SIDE_PADDING = 4

    def __init__(self, checked_text="", unchecked_text="", font_height_ratio=0.5,
                 parent=None, draggable=True):
        super().__init__(parent=parent)
        assert (0 < font_height_ratio <= 1)

        self._checked_text = checked_text
        self._unchecked_text = unchecked_text
        self._font_height_ratio = font_height_ratio
        self._draggable = draggable

        self._handle_position_multiplier = 0
        self._drag_start_position = None

        self._animation = QPropertyAnimation(self, b"handlePositionMultiplier")
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.setDuration(self._ANIMATION_DURATION)

        self.stateChanged.connect(self._on_state_changed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_text()

    def mousePressEvent(self, event):
        if self._draggable and event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not self._drag_start_position:
            return

        if (event.position().toPoint() - self._drag_start_position).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setData("text/slider", QByteArray(self._checked_text.encode(encoding="utf-8")))
        drag.setMimeData(mime_data)

        # Create custom pixmap
        font = self.font()
        if font.pixelSize() > 2:
            font.setPixelSize(font.pixelSize() - 2)

        font.setBold(True)
        fm = QFontMetrics(font)
        text_size = fm.size(Qt.TextFlag.TextSingleLine, self._checked_text)

        padding = 10
        rect_width = text_size.width() + padding * 2
        rect_height = text_size.height() + padding

        pixmap = QPixmap(rect_width, rect_height)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(font)

        # Draw rounded rect
        painter.setBrush(self.palette().color(QPalette.ColorRole.Highlight))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, rect_width, rect_height, 12, 12)

        # Draw text
        painter.setPen(self.palette().color(QPalette.ColorRole.HighlightedText))
        painter.drawText(QRect(0, 0, rect_width, rect_height), Qt.AlignmentFlag.AlignCenter, self._checked_text)

        painter.end()

        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(rect_width // 2, rect_height // 2))

        drag.exec(Qt.DropAction.LinkAction)

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

    def setChecked(self, checked: bool, signals: bool = False):
        original_blocked = self.signalsBlocked()
        if not signals:
            self.blockSignals(True)

        super().setChecked(checked)
        # Ensure we are in the finished animation state if there are signals blocked from the outside!
        if self.signalsBlocked():
            self._handle_position_multiplier = 1 if checked else 0
            # Ensure the toggle is updated visually even though it seems this is not necessary.
            self.update()
        self._update_text()

        if not signals:
            self.blockSignals(original_blocked)

    def setCheckedNoAnim(self, checked):
        self._animation.setDuration(0)
        self.setChecked(checked)
        self._animation.setDuration(self._ANIMATION_DURATION)

    def _get_checked_handle_brush(self):
        if isinstance(self.palette().highlight(), QBrush):
            return QBrush(self.palette().highlight().color().darker(130))
        else:
            return QBrush(self.palette().highlight().darker(130))

    def _get_checked_body_brush(self):
        if isinstance(self.palette().highlight(), QBrush):
            return self.palette().highlight()
        else:
            return QBrush(self.palette().highlight())

    def _get_unchecked_handle_brush(self):
        if isinstance(self.palette().button(), QBrush):
            return QBrush(self.palette().button().color().darker(110))
        else:
            return QBrush(self.palette().button().darker(110))

    def _get_unchecked_body_brush(self):
        if isinstance(self.palette().button(), QBrush):
            return self.palette().button()
        else:
            return QBrush(self.palette().button())


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

            painter.drawText(0, 20, f"{round(progress * widget.maximum(), 0)}%")

            # 4. Draw the Filled Part (Clipped)
            painter.save()
            clip_rect = QRect(rect.left(), rect.top(), fill_width + margin, rect.height())
            painter.setClipRect(clip_rect)

            # Use a gradient for a professional "Volume" look
            gradient = QLinearGradient(0, 0, w, 0)
            gradient.setColorAt(0.0, app_theme.get_green())  # Green
            gradient.setColorAt(0.5, app_theme.get_green())  # Green
            gradient.setColorAt(0.7, app_theme.get_yellow())  # Orange
            gradient.setColorAt(0.8, app_theme.get_orange())  # Orange
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
    last_volume: int = None
    volume_changed = Signal(int)

    def __init__(self, value: int = 70, shortcut: QKeySequence | QKeyCombination | QKeySequence.StandardKey | str | int = None):
        super(VolumeSlider, self).__init__()

        toggle_mute_action = QAction(_("Mute"), self)
        if shortcut is not None:
            toggle_mute_action.setShortcut(shortcut)
        toggle_mute_action.triggered.connect(self.toggle_mute)

        self.btn_volume = QToolButton()
        self.btn_volume.setDefaultAction(toggle_mute_action)
        self.btn_volume.setShortcutEnabled(True)
        self._update_volume_icon(value)
        self.addWidget(self.btn_volume, 0, alignment=Qt.AlignmentFlag.AlignBottom)

        self.slider_vol = JumpSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 150)
        self.slider_vol.setValue(value)
        self.slider_vol.setMinimumWidth(100)
        self.slider_vol.setProperty("cssClass", "button")
        self.slider_vol.max_glow_size = 2
        self.slider_vol.valueChanged.connect(self._on_value_changed)
        self.slider_vol.setStyle(VolumeSliderStyle())
        self.slider_vol.setSingleStep(5)

        # Shortcut to increase slider
        if shortcut is not None:
            inc_shortcut = QShortcut(QKeySequence("Ctrl+Up"), self)
            inc_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            inc_shortcut.activated.connect(self.increase_volume)

            # Shortcut to decrease slider
            dec_shortcut = QShortcut(QKeySequence("Ctrl+Down"), self)
            dec_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            dec_shortcut.activated.connect(self.decrease_volume)

        self.addWidget(self.slider_vol, 1)

    @Property(int, notify=volume_changed)
    def volume(self):
        return self.slider_vol.value()

    @volume.setter
    def volume(self, value):
        self.slider_vol.setValue(value)
        self._update_volume_icon(self.slider_vol.value())

    def increase_volume(self):
        self.volume = self.slider_vol.value() + self.slider_vol.pageStep()

    def decrease_volume(self, ):
        self.volume = self.slider_vol.value() - self.slider_vol.pageStep()

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
        elif self.last_volume is not None:
            self.slider_vol.setValue(self.last_volume)
        else:
            self.slider_vol.setValue(70)

        self.volume_changed.emit(self.slider_vol.value())

    def _update_volume_icon(self, volume):
        if volume == 0:
            self.btn_volume.setIcon(self.icon_volume_off)
        elif volume < 70:
            self.btn_volume.setIcon(self.icon_volume_down)
        else:
            self.btn_volume.setIcon(self.icon_volume_up)


class RepeatMode(StrEnum):
    NO_REPEAT = "No Repeat"
    REPEAT_SINGLE = "Repeat Single"
    REPEAT_ALL = "Repeat All"


class RepeatButton(QToolButton):
    icon_no_repeat: QIcon = QIcon.fromTheme("no-repeat")
    icon_repeat_1: QIcon = QIcon.fromTheme("repeat")
    icon_repeat_all: QIcon = QIcon.fromTheme("all-repeat")

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

        cycle_action = QAction("Cycle", self)
        cycle_action.setShortcut("Ctrl+R")

        cycle_action.triggered.connect(self.cycle_repeat_mode)
        self.setDefaultAction(cycle_action)
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

class ColorButton(QPushButton):
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