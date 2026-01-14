from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Signal, Qt, QEvent
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

from config.settings import AppSettings, SettingKeys


class RussellEmotionWidget(FigureCanvas):

    valueChanged = Signal(float, float)  # valence, arousal
    mousePressed = Signal()
    mouseReleased = Signal()

    def __init__(self):
        self.scatter = None

        self.valence = 5.0
        self.arousal = 5.0
        self.mouse_down = False

        # Apply globally
        if AppSettings.value(SettingKeys.THEME,"LIGHT", type=str) == "DARK":
            plt.style.use('dark_background')

        # Matplotlib figure
        self.figure = Figure(figsize=(3, 3), constrained_layout=True)
        self.figure.get_layout_engine().set(w_pad=0, h_pad=0, hspace=0, wspace=0)
        self.ax = self.figure.add_subplot(1, 1, 1)
        self.figure.set_facecolor("#2b2b2b")
        self.ax.set_facecolor("#2b2b2b")

        super().__init__(self.figure)

        self._draw_base()

        # Red point
        self.point, = self.ax.plot([self.valence], [self.arousal], "ro", markersize=8)

        # Mouse events
        self.mpl_connect("button_press_event", self._on_press)
        self.mpl_connect("motion_notify_event", self._on_motion)
        self.mpl_connect("button_release_event", self._on_release)

    # ---------------- Drawing ---------------- #

    def update_plot_theme(self, is_dark=True):
        # 1. Choose the base style
        theme = 'dark_background' if is_dark else 'default'

        # 2. Apply the style parameters to the existing figure
        with plt.style.context(theme):
            # Update the figure and axes colors
            self.figure.set_facecolor(plt.rcParams['figure.facecolor'])

            for ax in self.figure.axes:
                ax.set_facecolor(plt.rcParams['axes.facecolor'])
                # Refresh tick and label colors
                ax.tick_params(colors=plt.rcParams['xtick.color'])
                ax.xaxis.label.set_color(plt.rcParams['xtick.color'])
                ax.yaxis.label.set_color(plt.rcParams['ytick.color'])
                for spine in ax.spines.values():
                    spine.set_color(plt.rcParams['axes.edgecolor'])

                for text_obj in ax.texts:
                    text_obj.set_color(plt.rcParams['xtick.color'])

        # 3. CRITICAL: Redraw the canvas
        self.draw()

    def changeEvent(self, event, /):
        if event.type() == QEvent.Type.PaletteChange and self.ax and self.figure:
            if AppSettings.value(SettingKeys.THEME, "LIGHT", type=str) == "DARK":
                self.update_plot_theme(True)
                #self.figure.set_facecolor("#2b2b2b")
                #self.ax.set_facecolor("#2b2b2b")
            else:
                self.update_plot_theme(False)
                #self.figure.set_facecolor("#FFFFFF")
                #self.ax.set_facecolor("#FFFFFF")


    def clear_scatter(self):
        if self.scatter is not None:
            self.scatter.remove()
            self.scatter = None
        self.draw_idle()

    def add_reference_points(self, valences: list, arousal: list):
        self.clear_scatter()
        self.scatter = self.ax.scatter(
            valences,
            arousal,
            s=20,
            alpha=0.2,
            c="blue",
            edgecolors="none",
            zorder=2,
        )

        self.draw_idle()

    def _draw_base(self):
        self.ax.clear()
        self.ax.set_xlim(0, 10)
        self.ax.set_ylim(0, 10)

        # Axes lines at center
        self.ax.axhline(5, color="gray", linewidth=1, alpha=0.5)
        self.ax.axvline(5, color="gray", linewidth=1, alpha=0.5)

        self.ax.set_xlabel(_("unpleasant")+" → "+_("pleasant"))
        self.ax.set_ylabel(_("calm")+" → "+_("excited"))

        font_size = 8

        # Quadrant labels (with multiple moods)
        # Top Right: Excited Happy, Pleased
        self.ax.text(6.5, 8.5, "Excited", ha="center", va="center", fontsize=font_size)
        self.ax.text(7.5, 7.5, "Happy", ha="center", va="center", fontsize=font_size)
        self.ax.text(8.5, 6.5, "Pleased", ha="center", va="center", fontsize=font_size)

        # Bottom Right: Relaxed, Peaceful, Calm
        self.ax.text(8.5, 3.5, "Relaxed", ha="center", va="center", fontsize=font_size)
        self.ax.text(7.5, 2.5, "Peaceful", ha="center", va="center", fontsize=font_size)
        self.ax.text(6.5, 1.5, "Calm", ha="center", va="center", fontsize=font_size)


        #Bottom Left: Sleepy, Bored, Sad
        self.ax.text(3.5, 1.5, "Sleepy", ha="center", va="center", fontsize=font_size)
        self.ax.text(2.5, 2.5, "Bored", ha="center", va="center", fontsize=font_size)
        self.ax.text(1.5, 3.5, "Sad", ha="center", va="center", fontsize=font_size)

        # Top Left: Nervous, Angry, Annoying
        self.ax.text(1.5, 6.5, "Nervous", ha="center", va="center", fontsize=font_size)
        self.ax.text(2.5, 7.5, "Angry", ha="center", va="center", fontsize=font_size)
        self.ax.text(3.5, 8.5, "Annoying", ha="center", va="center", fontsize=font_size)

        # Optional smaller labels for nuanced moods
        self.ax.text(5, 9.8, "Hopeful", ha="center", va="top", fontsize=font_size)
        self.ax.text(0.1, 5, "Dark", ha="left", va="center", fontsize=font_size)
        self.ax.text(9.9, 5, "Dreamy", ha="right", va="center", fontsize=font_size)
        self.ax.text(5, 0.1, "Tired", ha="center", va="bottom", fontsize=font_size)

        self.ax.grid(True, linestyle="--", alpha=0.5)

    # ---------------- Mouse Events ---------------- #

    def _on_press(self, event):
        if event.button != 1:
            return
        if event.inaxes != self.ax:
            return
        self.mouse_down = True
        self._update_point(event.xdata, event.ydata)
        self.mousePressed.emit()

    def _on_motion(self, event):
        if not self.mouse_down:
            return
        if event.inaxes != self.ax:
            return
        self._update_point(event.xdata, event.ydata)

    def _on_release(self, event):
        if event.button != 1:
            return
        self.mouse_down = False
        self.mouseReleased.emit()

    # ---------------- Update Logic ---------------- #

    def _update_point(self, x, y):
        self.valence = round(max(0, min(10, x)), 2)
        self.arousal = round(max(0, min(10, y)), 2)

        self.point.set_data([self.valence], [self.arousal])

        self.valueChanged.emit(self.valence, self.arousal)
        self.draw_idle()

    def get_value(self):
        return self.valence, self.arousal

    def set_value(self, valence: float, arousal: float, notify:bool=True):
        self.valence = valence
        self.arousal = arousal

        self.point.set_data([self.valence], [self.arousal])

        if notify:
            self.valueChanged.emit(self.valence, self.arousal)
        self.draw_idle()


