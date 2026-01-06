from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QSizePolicy, QSlider, QVBoxLayout

from components.QJumpSlider import QJumpSlider
from config.settings import get_category_description


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

