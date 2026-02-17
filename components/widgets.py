import math

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSpacerItem, QPushButton
from PySide6.QtCore import QPointF, QSize, Qt, QRect, Signal, QPropertyAnimation, QEasingCurve, Property, QEvent, \
    QPoint, QSortFilterProxyModel, QObject, QModelIndex, QPersistentModelIndex
from PySide6.QtGui import QIcon, QPolygonF, QPainterStateGuard, QBrush, QPainter, QPalette, QMouseEvent, QColor, \
    QPaintEvent

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


class FileFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent : QObject=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # 0 is usually the 'Name' column in QFileSystemModel
        self.setFilterKeyColumn(0)

    def lessThan(self, left: QModelIndex | QPersistentModelIndex, right: QModelIndex | QPersistentModelIndex):
        # 1. Get a reference to the source model (QFileSystemModel)
        source_model = self.sourceModel()

        # 2. Check if the items are directories
        is_left_dir = source_model.isDir(left)
        is_right_dir = source_model.isDir(right)

        # 3. Logic: If one is a directory and the other isn't,
        # the directory is always "less than" (appears first)
        if is_left_dir and not is_right_dir:
            return self.sortOrder() == Qt.SortOrder.AscendingOrder

        if not is_left_dir and is_right_dir:
            return self.sortOrder() == Qt.SortOrder.DescendingOrder

        # 4. If both are the same type (both dirs or both files),
        # fall back to standard sorting (alphabetical, size, etc.)
        return super().lessThan(left, right)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex):
        # This ensures that if a file matches, its parent folders remain visible
        # Otherwise, the file would be hidden because its parent is filtered out
        if super().filterAcceptsRow(source_row, source_parent):
            return True

        # Check if any children match the filter
        source_model = self.sourceModel()
        source_index = source_model.index(source_row, 0, source_parent)
        for i in range(source_model.rowCount(source_index)):
            if self.filterAcceptsRow(i, source_index):
                return True
        return False