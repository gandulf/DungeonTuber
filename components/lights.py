from PySide6.QtCore import Qt, QSize, QEvent, Signal
from PySide6.QtGui import QIcon, QColor
from PySide6.QtWidgets import QFrame, QVBoxLayout, QListWidget, QListView, QListWidgetItem, QCheckBox, QSizePolicy, QLabel, QToolButton, QComboBox
from pywizlight import SCENES

from logic.lightengine import LightManager, Light, LightSetting
from config.theme import app_theme
from config.settings import AppSettings, SettingKeys
from components.widgets import IconLabel, JumpSlider, ColorButton, ToggleSlider

class LightSettingsWidget(QFrame):
    temperature_changed = Signal(int) # 1000-10000
    brightness_changed = Signal(int) # 0-255
    color_changed = Signal(QColor) # color
    scene_changed = Signal(str)  # scene_id

    def __init__(self,settings: LightSetting = None, parent=None):
        super(LightSettingsWidget, self).__init__(parent)

        form_layout = QVBoxLayout(self)

        brightness_title = IconLabel(icon=QIcon.fromTheme("light-brightness"), text=_("Brightness"))
        brightness_title.setObjectName("sub")

        self.brightness_label = QLabel()
        brightness_title.add_widget(self.brightness_label)
        form_layout.addSpacing(app_theme.spacing)
        form_layout.addWidget(brightness_title)
        self.brightness_slider = JumpSlider()
        self.brightness_slider.setDisabled(settings is None)
        self.brightness_slider.setMaximum(255)
        self.brightness_slider.setMinimum(0)
        self.brightness_slider.setValue(255)
        self.brightness_slider.valueChanged.connect(self.on_brightness_changed)
        self.brightness_slider.setObjectName("brightness")

        form_layout.addWidget(self.brightness_slider)

        temperature_title = IconLabel(icon=QIcon.fromTheme("light-temperature"), text=_("Temperature"))
        temperature_title.setObjectName("sub")

        self.temperature_label = QLabel()
        temperature_title.add_widget(self.temperature_label)
        form_layout.addSpacing(app_theme.spacing)
        form_layout.addWidget(temperature_title)
        self.temperature_slider = JumpSlider()
        self.temperature_slider.setDisabled(settings is None)
        self.temperature_slider.setMaximum(10000)
        self.temperature_slider.setMinimum(1000)
        self.temperature_slider.valueChanged.connect(self.on_temperature_changed)
        self.temperature_slider.setObjectName("temperature")

        form_layout.addWidget(self.temperature_slider)

        form_layout.addSpacing(app_theme.spacing)
        color_title = IconLabel(icon=QIcon.fromTheme("color-picker"), text=_("Color"))
        color_title.setObjectName("sub")
        form_layout.addWidget(color_title)
        self.color_edit = ColorButton()
        self.color_edit.setDisabled(settings is None)
        self.color_edit.colorChanged.connect(self.on_color_changed)
        self.color_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form_layout.addWidget(self.color_edit)

        form_layout.addSpacing(app_theme.spacing)
        scene_title = IconLabel(icon=QIcon.fromTheme("scene"), text=_("Scene"))
        scene_title.setObjectName("sub")
        form_layout.addWidget(scene_title)

        self.scene_combo = QComboBox(editable=False)
        self.scene_combo.addItem(_("None"), None)
        self.scene_combo.setCurrentIndex(0)
        for scene in SCENES.values():
            self.scene_combo.addItem(_(scene), scene)
        self.scene_combo.setDisabled(settings is None)
        self.scene_combo.currentIndexChanged.connect(self.on_scene_changed)
        form_layout.addWidget(self.scene_combo)

        if settings:
            self.update_light(settings)

    def setDisabled(self, value, /):
        super().setDisabled(value)
        self.scene_combo.setDisabled(value)
        self.brightness_slider.setDisabled(value)
        self.temperature_slider.setDisabled(value)
        self.color_edit.setDisabled(value)

    def get_settings(self):
        return LightSetting(color=self.get_color(), temperature=self.get_temperature(), brightness=self.get_brightness(), scene=self.get_scene())

    def update_light(self, light: LightSetting):
        self.blockSignals(True)

        if light.brightness:
            self.brightness_slider.setValue(light.brightness)
            self.brightness_label.setText(f"{round(light.brightness / 255 * 100)}%")

        scenes = SCENES.values()
        if isinstance(light, Light):
            if light.temperature_min and light.temperature_max:
                self.temperature_slider.setMinimum(light.temperature_min)
                self.temperature_slider.setMaximum(light.temperature_max)



            if light.scenes:
                scenes = light.scenes

            # stop0 = kelvin_to_rgb(light.temperature_min)
            # stop05 = kelvin_to_rgb((light.temperature_max - light.temperature_min) //2 + light.temperature_min)
            # stop1 = kelvin_to_rgb(light.temperature_max)
            #
            # self.temperature_slider.setStyleSheet(f"""
            # background: qlineargradient(x1:0, y1: 0, x2: 1, y2: 0,
            #     stop: 0  {stop0},
            #     stop: 0.5  {stop05},
            #     stop: 1  {stop1})
            # """);

        self.scene_combo.clear()
        self.scene_combo.addItem(_("None"), None)
        for scene in scenes:
            self.scene_combo.addItem(_(scene), scene)
            if light.scene == scene:
                self.scene_combo.setCurrentText(scene)

        if light.temperature:
            self.temperature_slider.setValue(light.temperature)
            self.temperature_label.setText(f"{light.temperature // 1000}K")
        else:
            self.temperature_slider.setValue(self.temperature_slider.minimum())
            self.temperature_label.setText("")

        if light.color:
            self.color_edit.setColor(light.color)
        else:
            self.color_edit.setColor(None)

        self.blockSignals(False)

    def get_scene(self)-> str:
        return self.scene_combo.itemData(self.scene_combo.currentIndex(), Qt.ItemDataRole.UserRole)

    def get_temperature(self):
        return self.temperature_slider.value()

    def get_brightness(self):
        return self.brightness_slider.value()

    def get_color(self):
        return self.color_edit.color()

    def blockSignals(self, b, /):
        super().blockSignals(b)

        for widget in [self.brightness_slider,self.temperature_slider,self.color_edit,self.scene_combo]:
            widget.blockSignals(b)

    def _reset_color_values(self, skip:str = None):
        if skip != "color":
            self.color_edit.blockSignals(True)
            self.color_edit.setColor(None)
            self.color_edit.blockSignals(False)

        if skip != "scene":
            self.scene_combo.blockSignals(True)
            self.scene_combo.setCurrentIndex(0)
            self.scene_combo.blockSignals(False)

        if skip != "temperature":
            self.temperature_slider.blockSignals(True)
            self.temperature_slider.setValue(self.temperature_slider.minimum())
            self.temperature_label.setText("")
            self.temperature_slider.blockSignals(False)

    def on_brightness_changed(self, new_value :int):
        self.brightness_label.setText(f"{round(new_value / 255 * 100)}%")
        self.brightness_changed.emit(new_value)

    def on_scene_changed(self, new_index:int):
        self._reset_color_values("scene")

        new_value = self.scene_combo.itemData(new_index, Qt.ItemDataRole.UserRole)
        self.scene_changed.emit(new_value if new_value !='' else None)

    def on_temperature_changed(self, new_value :int):
        self._reset_color_values("temperature")

        self.temperature_label.setText(f"{new_value // 1000}K")

        self.temperature_changed.emit(new_value)

    def on_color_changed(self, new_value :QColor):
        self._reset_color_values("color")
        self.color_changed.emit(new_value)


class LightsWidget(QFrame):
    lights_manager: LightManager

    def __init__(self, parent=None):
        super(LightsWidget, self).__init__(parent)

        self.setAutoFillBackground(True)
        self.setGraphicsEffect(app_theme.drop_shadow(self))
        self.setContentsMargins(app_theme.margin)

        self.directory_layout = QVBoxLayout(self)
        self.directory_layout.addStretch(1)
        self.directory_layout.setSpacing(0)
        self.directory_layout.setContentsMargins(0, 0, app_theme.spacing, 0)

        self.headerLabel = IconLabel(QIcon.fromTheme("light"), _("Lights"), parent=self)
        self.headerLabel.set_icon_size(app_theme.icon_size)
        self.headerLabel.set_alignment(Qt.AlignmentFlag.AlignCenter)
        self.headerLabel.text_label.setProperty("cssClass", "header")

        self.directory_layout.addWidget(self.headerLabel)

        self.lights_list = QListWidget()
        self.lights_list.setObjectName("lights")
        self.lights_list.setSpacing(app_theme.spacing)
        self.lights_list.setIconSize(QSize(64, 64))
        self.lights_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.lights_list.setWordWrap(False)
        self.lights_list.setMaximumHeight(64 + app_theme.spacing)
        self.lights_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.lights_list.setViewMode(QListView.ViewMode.IconMode)
        self.lights_list.currentItemChanged.connect(self.current_item_changed)

        self.directory_layout.addWidget(self.lights_list)

        form_layout = QVBoxLayout()

        self.light_title = IconLabel(icon=QIcon.fromTheme("light-full"), text="")
        self.light_title.text_label.setProperty("cssClass", "header")

        self.light_toggle = ToggleSlider()
        self.light_toggle.setDisabled(True)
        self.light_toggle.setChecked(True)
        self.light_toggle.setFixedSize(QSize(32, 16))
        self.light_toggle.checkStateChanged.connect(self.state_changed)

        self.edit_name = QToolButton(icon=QIcon.fromTheme("pencil"))
        self.edit_name.setProperty("cssClass", "mini")
        self.edit_name.clicked.connect(self.change_name)
        self.edit_name.setDisabled(True)
        self.light_title.add_widget(self.edit_name)
        self.light_title.add_widget(self.light_toggle)

        form_layout.addWidget(self.light_title)
        form_layout.addSpacing(app_theme.spacing)

        self.light_settings = LightSettingsWidget(parent = self)
        self.light_settings.scene_changed.connect(self.scene_changed)
        self.light_settings.temperature_changed.connect(self.temperature_changed)
        self.light_settings.brightness_changed.connect(self.brightness_changed)
        self.light_settings.color_changed.connect(self.color_changed)

        form_layout.addWidget(self.light_settings)

        form_layout.addSpacing(app_theme.spacing*2)

        self.scenable_edit = QCheckBox()
        self.scenable_edit.setText(_("Controlled by songs"))
        self.scenable_edit.setDisabled(True)
        self.scenable_edit.setChecked(True)
        self.scenable_edit.checkStateChanged.connect(self.scenable_changed)
        form_layout.addWidget(self.scenable_edit)

        self.directory_layout.addLayout(form_layout)

        self.lights_manager = LightManager()
        self.lights_manager.lights_found.connect(self.on_lights_found)
        self.lights_manager.lookup()

    def refresh(self):
        self.lights_manager.lookup()

    def changeEvent(self, event, /):
        if event.type() in [QEvent.Type.FontChange, QEvent.Type.ApplicationFontChange ]:
            self.headerLabel.set_icon_size(app_theme.icon_size)

    def change_name(self):
        light = self.lights_list.currentItem().data(Qt.ItemDataRole.UserRole)

        from components.dialogs import NameDialog
        save_preset_dialog = NameDialog()
        save_preset_dialog.set_name(light.name)
        save_preset_dialog.setWindowIcon(QIcon.fromTheme("pencil"))
        save_preset_dialog.setWindowTitle(_("Name"))
        if save_preset_dialog.exec():
            light.name = save_preset_dialog.get_name()
            self.update_light(light)
            self.refresh_lights_list()

    def apply_settings(self, settings:LightSetting):
        for i in range(self.lights_list.count()):
            item = self.lights_list.item(i)
            light = item.data(Qt.ItemDataRole.UserRole)
            if light.scenable:
                light.apply_settings(settings)

                if item in self.lights_list.selectedItems():
                    self.update_light(light)

    def state_changed(self, state: Qt.CheckState):
        for item in self.lights_list.selectedItems():
            light = item.data(Qt.ItemDataRole.UserRole)
            light.state = state != Qt.CheckState.Unchecked

        self.refresh_lights_list()

    def brightness_changed(self, new_value: int):
        for item in self.lights_list.selectedItems():
            light = item.data(Qt.ItemDataRole.UserRole)
            light.set_brightness(new_value)

    def temperature_changed(self, new_value: int):
        for item in self.lights_list.selectedItems():
            light = item.data(Qt.ItemDataRole.UserRole)
            light.set_temperature(new_value)

    def color_changed(self, new_value: QColor):
        for item in self.lights_list.selectedItems():
            light = item.data(Qt.ItemDataRole.UserRole)
            light.set_color(new_value)

    def scene_changed(self, new_value: str):
        for item in self.lights_list.selectedItems():
            light = item.data(Qt.ItemDataRole.UserRole)
            light.set_scene_id(new_value if new_value !='' else None)

    def current_item_changed(self, listItem: QListWidgetItem):
        light = listItem.data(Qt.ItemDataRole.UserRole)
        self.update_light(light)

    def scenable_changed(self, state: Qt.CheckState):
        for item in self.lights_list.selectedItems():
            light = item.data(Qt.ItemDataRole.UserRole)
            light.scenable = state != Qt.CheckState.Unchecked

    def refresh_lights_list(self):
        for i in range(self.lights_list.count()):
            list_item = self.lights_list.item(i)
            light = list_item.data(Qt.ItemDataRole.UserRole)
            list_item.setText(light.name)
            list_item.setIcon(QIcon.fromTheme("light-full" if light.state else "light"))

        self.lights_list.doItemsLayout()

    def on_lights_found(self, lights: list[Light]):
        self.lights_list.clear()

        for light in lights:
            list_item = QListWidgetItem(light.name)
            list_item.setData(Qt.ItemDataRole.UserRole, light)
            list_item.setIcon(QIcon.fromTheme("light-full" if light.state else "light"))
            self.lights_list.addItem(list_item)

        if len(lights) == 0:
            self.setVisible(False)
        else:
            self.lights_list.setCurrentRow(0)

            self.light_toggle.setDisabled(False)

            self.scenable_edit.setDisabled(False)
            self.edit_name.setDisabled(False)
            self.light_settings.setDisabled(False)

            self.setVisible(AppSettings.value(SettingKeys.LIGHTS_WIDGET, True, type=bool))

    def blockSignals(self, b, /):
        super().blockSignals(b)

        for widget in [self.light_toggle,self.scenable_edit, self.light_settings]:
            widget.blockSignals(b)


    def update_light(self, light: Light):
        self.blockSignals(True)

        self.light_toggle.setChecked(light.state)
        self.scenable_edit.setChecked(light.scenable)

        if light.name:
            self.light_title.set_text(light.name)

        self.light_settings.update_light(light)

        self.blockSignals(False)



