import math

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import QPointF, QSize, Qt, QRectF, QRect, Signal
from PySide6.QtGui import QIcon, QPolygonF, QPainterStateGuard, QBrush, QPainter, QPalette, QMouseEvent

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

    def paint(self, painter, filled: bool, rect: QRect, palette: QPalette, brush: QBrush = None):
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
                painter.drawPolygon(self._star_polygon, Qt.FillRule.WindingFill)
            else:
                painter.drawPolygon(self._star_polygon, Qt.FillRule.OddEvenFill)



class IconLabel(QWidget):

    icon_size = QSize(16, 16)
    horizontal_spacing = 2

    clicked = Signal()

    def mousePressEvent(self, ev: QMouseEvent):
        if (ev.button() == Qt.MouseButton.LeftButton):
            self.clicked.emit()

    def __init__(self, icon: QIcon, text, final_stretch=True):
        super(IconLabel, self).__init__()

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.icon_label = QLabel()
        if icon is not None:
            self.icon_label.setPixmap(icon.pixmap(self.icon_size))
            self.icon_label.setVisible(True)
        else:
            self.icon_label.setVisible(False)

        layout.addWidget(self.icon_label)
        layout.addSpacing(self.horizontal_spacing)

        self.text_label = QLabel(text)
        self.text_label.setOpenExternalLinks(True)
        layout.addWidget(self.text_label)

        if final_stretch:
            layout.addStretch()

    def set_text(self, text:str):
        self.text_label.setText(text)

    def set_icon(self, icon:QIcon):
        if icon is not None:
            self.icon_label.setPixmap(icon.pixmap(self.icon_size))
            self.icon_label.setVisible(True)
        else:
            self.icon_label.setVisible(False)
