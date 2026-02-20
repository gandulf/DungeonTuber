import math

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSpacerItem, QPushButton
from PySide6.QtCore import QPointF, QSize, Qt, QRect, Signal, QPropertyAnimation, QEasingCurve, Property, QEvent, \
    QPoint,  QObject, QRectF
from PySide6.QtGui import QIcon, QPolygonF, QPainterStateGuard, QBrush, QPainter, QPalette, QMouseEvent, QColor, \
    QPaintEvent, QPen, QAction
from config.settings import AppSettings, SettingKeys

from config.theme import app_theme

PAINTING_SCALE_FACTOR = 20

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

    def paint(self, painter: QPainter, filled: bool, rect: QRect, palette: QPalette, brush: QBrush = None):
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
            x_offset = (rect.width() - PAINTING_SCALE_FACTOR) / 2
            painter.translate(rect.x()+x_offset, rect.y() + y_offset)
            painter.scale(PAINTING_SCALE_FACTOR, PAINTING_SCALE_FACTOR)

            if filled:
                painter.drawPolygon(self._star_polygon, Qt.FillRule.WindingFill)
            else:
                painter.drawPolygon(self._star_polygon, Qt.FillRule.OddEvenFill)



class IconLabel(QWidget):

    icon_size = QSize(16, 16)
    horizontal_spacing = 2

    clicked = Signal()

    def mousePressEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def __init__(self, icon: QIcon, text:str, final_stretch:bool=True, parent:QWidget= None):
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
            self.icon_label.setContentsMargins(0,0,4,0)
        else:
            self.icon_label.setVisible(False)

        self.layout.addWidget(self.icon_label)
        self.layout.addSpacing(self.horizontal_spacing)

        self.text_label = QLabel(text, self)
        self.text_label.setOpenExternalLinks(True)
        self.layout.addWidget(self.text_label)

        if final_stretch:
            self.layout.addStretch()

    def set_icon_size(self, size:QSize):
        self.icon_label.setPixmap(self.icon.pixmap(size))

    def add_widget(self, widget:QWidget, stretch: int = 0):
        self.layout.addWidget(widget,stretch)

    def insert_widget(self,index: int, widget:QWidget, stretch: int = 0):
        self.layout.insertWidget(index, widget,stretch)

    def set_alignment(self, alignment: Qt.AlignmentFlag):
        self.text_label.setAlignment(alignment)

        if alignment == Qt.AlignmentFlag.AlignCenter:
            if not isinstance(self.layout.itemAt(0), QSpacerItem):
                self.layout.insertStretch(0)
        elif isinstance(self.layout.itemAt(0), QSpacerItem):
            spacer = self.layout.takeAt(0)

    def set_style_sheet(self, stylesheet: str):
        self.text_label.setStyleSheet(stylesheet)

    def set_text(self, text:str):
        self.text_label.setText(text)

    def set_icon(self, icon:QIcon):
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
        self.label.setContentsMargins(8,8,8,8)
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
            self.label.move(highlight_rect.right() +label_padding, highlight_rect.top() )
        elif position == Qt.AlignmentFlag.AlignLeft:
            if highlight_rect.left() - self.label.width() < parent_rect.left():
                self.update_label_button(Qt.AlignmentFlag.AlignTop)
                return
            self.label.move(highlight_rect.left()- self.label.width() - label_padding, highlight_rect.top())
        else:
            self.label.move(highlight_rect.left(), highlight_rect.top() - self.label.height() - label_padding - self.next_button.height() - label_padding)

        # Position button below label
        self.next_button.move( self.label.geometry().right() - self.next_button.width(), self.label.geometry().bottom() + label_padding)
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
        painter.drawRoundedRect(self._highlight_rect,8,8)
        painter.restore()

        # Rounded border around highlight
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(QColor(255, 255, 255))
        painter.drawRoundedRect(self._highlight_rect, 8, 8)

        painter.setBrush(QBrush(QColor(0, 0, 0, 150)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.label.geometry(), 8.0,8.0 )

    def eventFilter(self, obj: QObject, event: QEvent):
        # Update highlight if parent resizes or moves
        if obj == self.parent() and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self.setGeometry(self.parent().geometry())
            self.show_step(initial=True)
        return super().eventFilter(obj, event)


def _map_pt(plot_rect, val, aro):
    x_pos = plot_rect.left() + (val / 10.0) * plot_rect.width()
    y_pos = plot_rect.bottom() - (aro / 10.0) * plot_rect.height()
    return QPointF(x_pos, y_pos)

class RussellEmotionWidget(QWidget):
    """
    A widget that draws a Russell's Circumplex Model of Emotion diagram
    using PySide6 QPainter, allowing users to pick a valence/arousal point.
    """

    value_changed = Signal(float, float, bool)  # valence, arousal, in_progress

    def __init__(self, parent: QWidget | None=None):
        super().__init__(parent)
        self.valence = -1
        self.arousal = -1
        self.mouse_down = False
        self.reference_points = []

        self.setMinimumSize(20 * app_theme.font_size, 20 * app_theme.font_size)
        self.setMouseTracking(True)

        self.bg_color = QColor("#FFFFFF")
        self.fg_color = QColor("#000000")
        self.grid_color = QColor("#CCCCCC")
        self.point_color = QColor("#FF0000")
        self.ref_point_color = QColor("#0000FF")
        self.ref_point_border_color = QColor("#2b2b2b")

        self.update_theme()

    def sizeHint(self, /) -> QSize:
        return QSize(22 * app_theme.font_size, 22 * app_theme.font_size)

    def update_theme(self):
        is_dark = AppSettings.value(SettingKeys.THEME, "LIGHT", type=str) == "DARK"
        if is_dark:
            self.bg_color = QColor("#2b2b2b")
            self.fg_color = QColor("#dddddd")
            self.grid_color = QColor("#555555")
            self.point_color = QColor("#00FF00")  # Neon Green
            self.ref_point_color = QColor("#00FF00")
            self.ref_point_border_color = QColor("#FFFFFF")
        else:
            self.bg_color = QColor("#FFFFFF")
            self.fg_color = QColor("#555555")
            self.grid_color = QColor("#CCCCCC")
            self.point_color = QColor("#0000FF")  # Blue
            self.ref_point_color = QColor("#0000FF")
            self.ref_point_border_color = QColor("#2b2b2b")
        self.update()

    def changeEvent(self, event: QEvent):
        if event.type() == QEvent.Type.PaletteChange:
            self.update_theme()
        elif event.type() == QEvent.Type.FontChange:
            self.setMinimumSize(20 * app_theme.font_size, 20 * app_theme.font_size)

        super().changeEvent(event)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = painter.font()
        font.setPointSizeF(app_theme.font_size)
        painter.setFont(font)

        MARGIN_LEFT = self.contentsMargins().left() + painter.fontMetrics().height()
        MARGIN_BOTTOM = self.contentsMargins().bottom() + painter.fontMetrics().height()
        MARGIN_TOP = self.contentsMargins().top()
        MARGIN_RIGHT = self.contentsMargins().right()

        # Draw background
        painter.fillRect(event.rect(), self.bg_color)

        self.plot_rect = event.rect().adjusted(MARGIN_LEFT, MARGIN_TOP, -MARGIN_RIGHT,-MARGIN_BOTTOM)

        # Draw Grid (Center lines)
        painter.setPen(QPen(self.grid_color, 1))
        center_x = self.plot_rect.center().x()
        center_y = self.plot_rect.center().y()

        painter.drawLine(QPointF(self.plot_rect.left(), center_y), QPointF(self.plot_rect.right(), center_y))
        painter.drawLine(QPointF(center_x, self.plot_rect.top()), QPointF(center_x, self.plot_rect.bottom()))

        # Draw dashed grid border
        painter.setPen(QPen(self.grid_color, 1, Qt.PenStyle.DashLine))
        painter.drawRect(self.plot_rect)

        # Draw Labels inside
        painter.setPen(self.fg_color)

        if app_theme.font_size_small > 11:
            labels = [
                (7.5, 7.5, "Happy"),
                (7.5, 2.5, "Peaceful"),
                (2.5, 2.5, "Bored"),
                (2.5, 7.5, "Angry")
            ]
        else:
            labels = [
                (6.5, 8.5, "Excited"), (7.5, 7.5, "Happy"), (8.5, 6.5, "Pleased"),
                (8.5, 3.5, "Relaxed"), (7.5, 2.5, "Peaceful"), (6.5, 1.5, "Calm"),
                (3.5, 1.5, "Sleepy"), (2.5, 2.5, "Bored"), (1.5, 3.5, "Sad"),
                (1.5, 6.5, "Nervous"), (2.5, 7.5, "Angry"), (3.5, 8.5, "Annoying")
            ]

        for val, aro, text in labels:
            self.draw_text_centered(painter, _map_pt(self.plot_rect, val, aro), text)

        # Nuanced labels
        self.draw_text_centered(painter, _map_pt(self.plot_rect, 5, 9.8), "Hopeful",
                                align=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.draw_text_centered(painter, _map_pt(self.plot_rect, 0.1, 5), "Dark",
                                align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.draw_text_centered(painter, _map_pt(self.plot_rect, 9.9, 5), "Dreamy",
                                align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.draw_text_centered(painter, _map_pt(self.plot_rect, 5, 0.1), "Tired",
                                align=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)

        # Axis Labels
        x_label = _("unpleasant") + "→" + _("pleasant")
        y_label = _("calm") + "→" + _("excited")

        painter.drawText(QRectF(self.plot_rect.left(), self.plot_rect.bottom(), self.plot_rect.width(), MARGIN_BOTTOM),
                         Qt.AlignmentFlag.AlignCenter, x_label)

        bounding_rect = painter.fontMetrics().boundingRect(y_label).adjusted(-2, -2, 2, 2)
        h = bounding_rect.height()

        painter.save()
        painter.translate(MARGIN_LEFT - h/2, self.plot_rect.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-self.plot_rect.height() / 2, - h/2, self.plot_rect.height(), h),
                         Qt.AlignmentFlag.AlignCenter, y_label)
        painter.restore()

        # Draw Reference Points
        c = QColor(self.ref_point_color)
        c.setAlpha(50)
        painter.setBrush(QBrush(c))
        painter.setPen(QPen(self.ref_point_border_color, 0.5))

        for val, aro in self.reference_points:
            if val is not None and aro is not None:
                pt = _map_pt(self.plot_rect, val, aro)
                painter.drawEllipse(pt, 3, 3)

        # Draw Current Point
        if self.valence is not None and self.arousal is not None and self.valence>=0 and self.arousal>=0:
            pt = _map_pt(self.plot_rect, self.valence, self.arousal)
            painter.setBrush(QBrush(self.point_color))
            painter.setPen(QPen(self.ref_point_border_color, 1.5))
            painter.drawEllipse(pt, 6, 6)


        # draw clear X
        self.clear_rect : QRect = self.rect().marginsAdded(self.contentsMargins())
        self.clear_rect.setWidth(16)
        self.clear_rect.setY(self.clear_rect.bottom()-16)
        self.clear_rect.setHeight(16)
        QIcon.fromTheme(QIcon.ThemeIcon.EditClear).paint(painter, self.clear_rect, alignment=Qt.AlignmentFlag.AlignCenter)

    def draw_text_centered(self, painter, pt, text, align=Qt.AlignmentFlag.AlignCenter):
        bounding_rect = painter.fontMetrics().boundingRect(text).adjusted(-2, -2, 2, 2)
        w = bounding_rect.width()
        h = bounding_rect.height()

        if align & Qt.AlignmentFlag.AlignLeft:
            rect = QRectF(pt.x(), pt.y() - h / 2, w, h)
        elif align & Qt.AlignmentFlag.AlignRight:
            rect = QRectF(pt.x() - w, pt.y() - h / 2, w, h)
        elif align & Qt.AlignmentFlag.AlignTop:
            rect = QRectF(pt.x() - w / 2, pt.y(), w, h)
        elif align & Qt.AlignmentFlag.AlignBottom:
            rect = QRectF(pt.x() - w / 2, pt.y() - h, w, h)
        else:
            rect = QRectF(pt.x() - w / 2, pt.y() - h / 2, w, h)

        painter.drawText(rect, align, text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.clear_rect.contains(event.position().toPoint()):
                self.reset(True)
            else:
                self.mouse_down = True
                self.update_from_mouse(event.position())

    def mouseMoveEvent(self, event):
        if self.mouse_down:
            self.update_from_mouse(event.position())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_down = False
            self.value_changed.emit(self.valence, self.arousal, False)

    def update_from_mouse(self, pos):
        x = pos.x() - self.plot_rect.left()
        y = pos.y() - self.plot_rect.top()

        val = (x / self.plot_rect.width()) * 10.0
        aro = 10.0 - (y / self.plot_rect.height()) * 10.0

        self.valence = round(max(0.0, min(10.0, val)), 2)
        self.arousal = round(max(0.0, min(10.0, aro)), 2)

        self.value_changed.emit(self.valence, self.arousal, True)
        self.update()

    def get_value(self):
        return self.valence, self.arousal

    def set_value(self, valence, arousal, notify=True):
        self.valence = valence
        self.arousal = arousal
        if notify:
            self.value_changed.emit(self.valence, self.arousal, False)
        self.update()

    def reset(self, notify=True):
        self.set_value(-1, -1, notify)

    def set_reference_points(self, points):
        if isinstance(points,list):
            self.reference_points = points
        else:
            self.reference_points = list(points)
        self.update()

    def add_reference_points(self, points):
        self.reference_points.extend(points)
        self.update()

    def clear_scatter(self):
        self.reference_points = []
        self.update()

    def update_plot_theme(self, is_dark=True):
        # Kept for compatibility, though is_dark is ignored in favor of AppSettings
        self.update_theme()
