from PySide6.QtWidgets import QLayout, QWidget
from PySide6.QtCore import QPoint, QRect, QSize, Qt

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

    def heightForWidth(self, width: int) ->int:
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect:QRect):
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
