from PySide6.QtCore import QPointF, QRect, QSize, Property, QEasingCurve, QPropertyAnimation
from PySide6.QtGui import QBrush, QColor, Qt, QPalette, QPen, QPainter
from PySide6.QtWidgets import QCheckBox


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

