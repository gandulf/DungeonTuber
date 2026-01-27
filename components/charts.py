from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, Qt, QEvent, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor

from config.settings import AppSettings, SettingKeys


class RussellEmotionWidget(QWidget):
    """
    A widget that draws a Russell's Circumplex Model of Emotion diagram
    using PySide6 QPainter, allowing users to pick a valence/arousal point.
    """

    valueChanged = Signal(float, float)  # valence, arousal
    mousePressed = Signal()
    mouseReleased = Signal()

    MARGIN_LEFT = 15
    MARGIN_RIGHT = 10
    MARGIN_TOP = 10
    MARGIN_BOTTOM = 15

    def __init__(self, parent=None):
        super().__init__(parent)
        self.valence = 5.0
        self.arousal = 5.0
        self.mouse_down = False
        self.reference_points = []

        self.setMinimumSize(250, 250)
        self.setMouseTracking(True)

        self.bg_color = QColor("#FFFFFF")
        self.fg_color = QColor("#000000")
        self.grid_color = QColor("#CCCCCC")
        self.point_color = QColor("#FF0000")
        self.ref_point_color = QColor("#0000FF")
        self.ref_point_border_color = QColor("#2b2b2b")

        self.update_theme()

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
        super().changeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw background
        painter.fillRect(self.rect(), self.bg_color)

        w = self.width()
        h = self.height()

        plot_rect = QRectF(self.MARGIN_LEFT, self.MARGIN_TOP,
                           w - self.MARGIN_LEFT - self.MARGIN_RIGHT,
                           h - self.MARGIN_TOP - self.MARGIN_BOTTOM)

        # Draw Grid (Center lines)
        painter.setPen(QPen(self.grid_color, 1))
        center_x = plot_rect.left() + plot_rect.width() / 2
        center_y = plot_rect.top() + plot_rect.height() / 2

        painter.drawLine(QPointF(plot_rect.left(), center_y), QPointF(plot_rect.right(), center_y))
        painter.drawLine(QPointF(center_x, plot_rect.top()), QPointF(center_x, plot_rect.bottom()))

        # Draw dashed grid border
        painter.setPen(QPen(self.grid_color, 1, Qt.PenStyle.DashLine))
        painter.drawRect(plot_rect)

        # Draw Labels inside
        painter.setPen(self.fg_color)
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        def map_pt(val, aro):
            x_pos = plot_rect.left() + (val / 10.0) * plot_rect.width()
            y_pos = plot_rect.bottom() - (aro / 10.0) * plot_rect.height()
            return QPointF(x_pos, y_pos)

        labels = [
            (6.5, 8.5, "Excited"), (7.5, 7.5, "Happy"), (8.5, 6.5, "Pleased"),
            (8.5, 3.5, "Relaxed"), (7.5, 2.5, "Peaceful"), (6.5, 1.5, "Calm"),
            (3.5, 1.5, "Sleepy"), (2.5, 2.5, "Bored"), (1.5, 3.5, "Sad"),
            (1.5, 6.5, "Nervous"), (2.5, 7.5, "Angry"), (3.5, 8.5, "Annoying")
        ]

        for val, aro, text in labels:
            self.draw_text_centered(painter, map_pt(val, aro), text)

        # Nuanced labels
        self.draw_text_centered(painter, map_pt(5, 9.8), "Hopeful",
                                align=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.draw_text_centered(painter, map_pt(0.1, 5), "Dark",
                                align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.draw_text_centered(painter, map_pt(9.9, 5), "Dreamy",
                                align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.draw_text_centered(painter, map_pt(5, 0.1), "Tired",
                                align=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)

        # Axis Labels
        x_label = _("unpleasant") + "→" + _("pleasant")
        y_label = _("calm") + "→" + _("excited")

        painter.drawText(QRectF(plot_rect.left(), plot_rect.bottom(), plot_rect.width(), self.MARGIN_BOTTOM),
                         Qt.AlignmentFlag.AlignCenter, x_label)

        painter.save()
        painter.translate(self.MARGIN_LEFT - 10, plot_rect.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-plot_rect.height() / 2, -10, plot_rect.height(), 20),
                         Qt.AlignmentFlag.AlignCenter, y_label)
        painter.restore()

        # Draw Reference Points
        c = QColor(self.ref_point_color)
        c.setAlpha(50)
        painter.setBrush(QBrush(c))
        painter.setPen(QPen(self.ref_point_border_color, 0.5))

        for val, aro in self.reference_points:
            pt = map_pt(val, aro)
            painter.drawEllipse(pt, 3, 3)

        # Draw Current Point
        pt = map_pt(self.valence, self.arousal)
        painter.setBrush(QBrush(self.point_color))
        painter.setPen(QPen(self.ref_point_border_color, 1.5))
        painter.drawEllipse(pt, 6, 6)

    def draw_text_centered(self, painter, pt, text, align=Qt.AlignmentFlag.AlignCenter):
        rect = QRectF(pt.x() - 40, pt.y() - 10, 80, 20)

        if align & Qt.AlignmentFlag.AlignLeft:
            rect = QRectF(pt.x(), pt.y() - 10, 80, 20)
        elif align & Qt.AlignmentFlag.AlignRight:
            rect = QRectF(pt.x() - 80, pt.y() - 10, 80, 20)
        elif align & Qt.AlignmentFlag.AlignTop:
            rect = QRectF(pt.x() - 40, pt.y(), 80, 20)
        elif align & Qt.AlignmentFlag.AlignBottom:
            rect = QRectF(pt.x() - 40, pt.y() - 20, 80, 20)

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
        w = self.width()
        h = self.height()

        plot_width = w - self.MARGIN_LEFT - self.MARGIN_RIGHT
        plot_height = h - self.MARGIN_TOP - self.MARGIN_BOTTOM

        x = pos.x() - self.MARGIN_LEFT
        y = pos.y() - self.MARGIN_TOP

        val = (x / plot_width) * 10.0
        aro = 10.0 - (y / plot_height) * 10.0

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

    def add_reference_points(self, points):
        self.reference_points = self.reference_points + points
        self.update()

    def clear_scatter(self):
        self.reference_points = []
        self.update()

    def update_plot_theme(self, is_dark=True):
        # Kept for compatibility, though is_dark is ignored in favor of AppSettings
        self.update_theme()
