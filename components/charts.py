from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Signal, Qt, QEvent, QPointF, QRectF, QSize
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPaintEvent

from config.settings import AppSettings, SettingKeys
from config.theme import app_theme


def _map_pt(plot_rect, val, aro):
    x_pos = plot_rect.left() + (val / 10.0) * plot_rect.width()
    y_pos = plot_rect.bottom() - (aro / 10.0) * plot_rect.height()
    return QPointF(x_pos, y_pos)

class RussellEmotionWidget(QWidget):
    """
    A widget that draws a Russell's Circumplex Model of Emotion diagram
    using PySide6 QPainter, allowing users to pick a valence/arousal point.
    """

    valueChanged = Signal(float, float)  # valence, arousal
    mousePressed = Signal()
    mouseReleased = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.valence = 5.0
        self.arousal = 5.0
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

    def sizeHint(self, /):
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

    def changeEvent(self, event):
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
        if self.valence is not None and self.arousal is not None:
            pt = _map_pt(self.plot_rect, self.valence, self.arousal)
            painter.setBrush(QBrush(self.point_color))
            painter.setPen(QPen(self.ref_point_border_color, 1.5))
            painter.drawEllipse(pt, 6, 6)

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
            self.mouse_down = True
            self.update_from_mouse(event.position())
            self.mousePressed.emit()

    def mouseMoveEvent(self, event):
        if self.mouse_down:
            self.update_from_mouse(event.position())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_down = False
            self.mouseReleased.emit()

    def update_from_mouse(self, pos):
        x = pos.x() - self.plot_rect.left()
        y = pos.y() - self.plot_rect.top()

        val = (x / self.plot_rect.width()) * 10.0
        aro = 10.0 - (y / self.plot_rect.height()) * 10.0

        self.valence = round(max(0.0, min(10.0, val)), 2)
        self.arousal = round(max(0.0, min(10.0, aro)), 2)

        self.valueChanged.emit(self.valence, self.arousal)
        self.update()

    def get_value(self):
        return self.valence, self.arousal

    def set_value(self, valence, arousal, notify=True):
        self.valence = valence
        self.arousal = arousal
        if notify:
            self.valueChanged.emit(self.valence, self.arousal)
        self.update()

    def reset(self, notify=True):
        self.set_value(5, 5, notify)

    def add_reference_points(self, points):
        self.reference_points = self.reference_points + points
        self.update()

    def clear_scatter(self):
        self.reference_points = []
        self.update()

    def update_plot_theme(self, is_dark=True):
        # Kept for compatibility, though is_dark is ignored in favor of AppSettings
        self.update_theme()
