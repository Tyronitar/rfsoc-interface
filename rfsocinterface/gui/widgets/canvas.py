from collections.abc import Callable
from enum import Enum
from typing import Concatenate

import matplotlib as mpl

mpl.use('QtAgg')
mpl.rcParams['toolbar'] = 'toolbar2'

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from matplotlib.backend_bases import _Mode
from matplotlib.backend_tools import (
    ToolBase,
    ToolToggleBase,
)
from matplotlib.backends.backend_qt import FigureManagerQT, NavigationToolbar2QT
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QIcon, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from rfsocinterface.core.utils import (
    EDITED_RESONANCE_COLOR,
    SELECTED_RESONANCE_COLOR,
    P,
)
from rfsocinterface.gui.blit_manager import BlitManager


class EditTool(ToolToggleBase):
    default_keymap = 'e'
    description = 'Edit the plot'
    default_toggled = False
    image = ':/icons/edit.svg'
    radio_group = 'default'


class AddTool(ToolBase):
    description = 'Add an artist to the plot'
    image = ':/icons/plus.svg'

    def __init__(self, toolmanager, name, fn: Callable):
        super().__init__(toolmanager, name)
        self.fn = fn

    def trigger(self, sender, event, data=None):
        self.fn(sender, event, data)


class RemoveTool(ToolBase):
    description = 'Remove the currently selected artist from the plot'
    image = ':/icons/minus.svg'

    def __init__(self, toolmanager, name, fn: Callable):
        super().__init__(toolmanager, name)
        self.fn = fn

    def trigger(self, sender, event, data=None):
        self.fn(sender, event, data)


class UndoTool(ToolBase):
    description = 'Undo the last action'
    image = ':/icons/undo.svg'

    def __init__(self, toolmanager, name, fn: Callable):
        super().__init__(toolmanager, name)
        self.fn = fn

    def trigger(self, sender, event, data=None):
        self.fn(sender, event, data)


class RedoTool(ToolBase):
    description = 'Redo the last action'
    image = ':/icons/redo.svg'

    def __init__(self, toolmanager, name, fn: Callable):
        super().__init__(toolmanager, name)
        self.fn = fn

    def trigger(self, sender, event, data=None):
        self.fn(sender, event, data)


class ScrollableCanvas(QScrollArea):
    """Widget for displating a Matplotlib canvas in a scroll area."""

    def __init__(self, parent=None):
        """Initialize a ScrollableCanvas."""
        super().__init__(parent)

        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setStyleSheet('QScrollArea {background-color:white;}')

        self.set_figure(Figure(figsize=(5, 5)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        self.layout().addWidget(self.canvas)
        self.layout().installEventFilter(self)

    @property
    def figure(self) -> Figure:
        return self.canvas.figure

    def set_figure(self, fig: Figure):
        """Set the figure for this widget's canvas."""
        self.canvas = FigureCanvas(fig)
        self.canvas.sizePolicy().setHorizontalPolicy(QSizePolicy.Policy.Minimum)
        self.setWidget(self.canvas)
        self.widget().setStyleSheet('background-color:white;')
        self.bm = BlitManager(self.canvas)

    def eventFilter(self, obj: QObject, event: QEvent):
        """Filter all mouse scroll events inside the canvas."""
        if isinstance(event, QWheelEvent):
            vangle = event.angleDelta().y()
            hangle = event.angleDelta().x()
            vbar = self.verticalScrollBar()
            hbar = self.verticalScrollBar()
            # Vertical scrolling
            if vangle > 0:
                vbar.setValue(max(vbar.minimum(), vbar.value() - vangle / 2))
            else:
                vbar.setValue(min(vbar.maximum(), vbar.value() - vangle / 2))

            # Horizontal scrolling
            if hangle > 0:
                hbar.setValue(max(hbar.minimum(), hbar.value() - hangle / 2))
            else:
                hbar.setValue(min(hbar.maximum(), hbar.value() - hangle / 2))
            return True
        return super().eventFilter(obj, event)

    def replot_figure(
        self,
        plotting_function: Callable[Concatenate[Figure, P], None],
        *args: P.args,
        **kwargs: P.kwargs,
    ):
        self.figure.clf()
        plotting_function(*args, fig=self.figure, **kwargs)


class EditMode(str, Enum):
    EDIT = 'edit'

    def __str__(self):
        return self.value


class EditToolBar(NavigationToolbar2QT):
    toolitems = NavigationToolbar2QT.toolitems

    def __init__(
        self,
        canvas,
        parent=None,
        coordinates=True,
        add_group: bool = False,
        add_edit_button: bool = False,
        edit_description: str = EditTool.description,
        add_function: Callable = None,
        add_description: str = AddTool.description,
        remove_function: Callable = None,
        remove_description: str = RemoveTool.description,
        undo_function: Callable = None,
        undo_description: str = UndoTool.description,
        redo_function: Callable = None,
        redo_description: str = RedoTool.description,
    ):
        self.add_function = add_function
        self.remove_function = remove_function
        self.undo_function = undo_function
        self.redo_function = redo_function
        add_group = (
            add_group
            or add_edit_button
            or (add_function is not None)
            or (remove_function is not None)
            or (undo_function is not None)
            or (redo_function is not None)
        )
        new_group = []
        if add_group:
            new_group.append((None, None, None, None))
        if add_edit_button:
            new_group.append(('Edit', edit_description, EditTool.image, 'toggle_edit'))
        if add_function is not None:
            new_group.append(('Add', add_description, AddTool.image, 'add'))
        if remove_function is not None:
            new_group.append(('Remove', remove_description, RemoveTool.image, 'remove'))
        if undo_function is not None:
            new_group.append(('Undo', undo_description, UndoTool.image, 'undo'))
        if redo_function is not None:
            new_group.append(('Redo', redo_description, RedoTool.image, 'redo'))

        # Insert new group after 'customize'
        toolitems = [*NavigationToolbar2QT.toolitems]
        i = [name for name, *_ in toolitems].index('Customize') + 1
        for item in new_group:
            toolitems.insert(i, item)
            i += 1
        self.toolitems = toolitems

        super().__init__(canvas, parent, coordinates)

        if add_edit_button:
            self._actions['toggle_edit'].setCheckable(True)
        self.set_edit_actions_enabled(False)

    def _icon(self, name: str):
        if name[0] == ':':
            # We're attempting to access a QResource File
            name = name[:-4]  # get rid of the .png added by the parent class
            return QIcon(QPixmap(name))

        return super()._icon(name)

    @property
    def editing(self) -> bool:
        return self.mode == EditMode.EDIT

    def set_edit_actions_enabled(self, enabled: bool):
        for action in ['add', 'remove', 'undo', 'redo']:
            if action in self._actions:
                self._actions[action].setVisible(enabled)

    def pan(self, *args):
        super().pan(*args)
        self.set_edit_actions_enabled(False)

    def zoom(self, *args):
        super().zoom(*args)
        self.set_edit_actions_enabled(False)

    def toggle_edit(self):
        if self.mode in [_Mode.PAN, _Mode.ZOOM]:
            # Need to release the lock in order to draw on the canvas
            self.canvas.widgetlock.release(self)

        if self.editing:
            self.mode = _Mode.NONE
            self.set_edit_actions_enabled(False)
        else:
            self.mode = EditMode.EDIT
            self.set_edit_actions_enabled(True)
        self._update_buttons_checked()

    def add(self):
        self.add_function()

    def remove(self):
        self.remove_function()

    def undo(self):
        self.undo_function()

    def redo(self):
        self.redo_function()

    def _update_buttons_checked(self):
        super()._update_buttons_checked()
        if 'toggle_edit' in self._actions:
            self._actions['toggle_edit'].setChecked(self.mode.name == 'EDIT')


class ToolbarCanvas(QWidget):
    """Widget canvas that contains the navbar."""

    def __init__(
        self,
        parent=None,
        fig: Figure | None = None,
        scrollable: bool = False,
        add_edit: bool = False,
        edit_description: str = EditTool.description,
        coordinates: bool = True,
        add_function: Callable = None,
        add_description: str = AddTool.description,
        remove_function: Callable = None,
        remove_description: str = RemoveTool.description,
        undo_function: Callable = None,
        undo_description: str = UndoTool.description,
        redo_function: Callable = None,
        redo_description: str = RedoTool.description,
    ):
        """Initialize a ResonatorCanvas."""
        super().__init__(parent)
        if fig is None:
            fig = Figure(figsize=(8, 5))
        if scrollable:
            self.canvas = ScrollableCanvas(self)
            self.canvas.set_figure(fig)
        else:
            self.canvas = FigureCanvas(fig)
        self.nav = EditToolBar(
            self.figure_canvas,
            parent,
            coordinates=coordinates,
            add_edit_button=add_edit,
            edit_description=edit_description,
            add_function=add_function,
            add_description=add_description,
            remove_function=remove_function,
            remove_description=remove_description,
            undo_function=undo_function,
            undo_description=undo_description,
            redo_function=redo_function,
            redo_description=redo_description,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        layout.addWidget(self.nav)
        layout.addWidget(self.canvas)

    @property
    def editing(self) -> bool:
        return self.nav.editing

    @property
    def figure(self) -> Figure:
        return self.canvas.figure

    @property
    def figure_canvas(self) -> FigureCanvas:
        if isinstance(self.canvas, ScrollableCanvas):
            return self.canvas.canvas
        return self.canvas

    def update_figure(self):
        """Update the figure of this widget."""
        self.update()

    def set_figure(self, fig: Figure | None):
        """Set the figure of this widget."""
        self.canvas.set_figure(fig)
        layout = self.layout()

        old_nav = self.nav
        self.manager = FigureManagerQT(self.canvas, 1)
        self.canvas.manager = self.manager
        self.nav = self.manager.toolbar
        layout.replaceWidget(old_nav, self.nav)

    def replot_figure(
        self,
        plotting_function: Callable[Concatenate[Figure, P], None],
        *args: P.args,
        **kwargs: P.kwargs,
    ):
        if isinstance(self.canvas, ScrollableCanvas):
            self.canvas.replot_figure(plotting_function, *args, **kwargs)
        else:
            self.figure.clf()
            plotting_function(*args, fig=self.figure, **kwargs)
        self.nav.update()


class ResonatorCanvas(QWidget):
    """Widget for displaying the data for a single resonator and adjusting the fit."""

    def __init__(self, parent=None, fig: Figure | None = None):
        """Initialize a ResonatorCanvas."""
        super().__init__(parent)
        if fig is None:
            fig = Figure(figsize=(8, 5))
        self.canvas = ToolbarCanvas(parent=self, fig=fig, add_edit=True)
        self.line = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        layout.addWidget(self.nav)
        layout.addWidget(self.canvas)

    @property
    def manager(self) -> FigureManagerQT:
        return self.canvas.manager

    @property
    def nav(self) -> NavigationToolbar2QT:
        return self.canvas.nav

    @property
    def figure(self) -> Figure:
        return self.canvas.figure

    @property
    def figure_canvas(self) -> FigureCanvas:
        return self.canvas.figure_canvas

    def update_figure(self):
        """Update the figure of this widget."""
        self.update()

    def replot_figure(
        self,
        plotting_function: Callable[Concatenate[Figure, P], None],
        *args: P.args,
        **kwargs: P.kwargs,
    ):
        self.canvas.replot_figure(plotting_function, *args, **kwargs)
        self.line = self.figure.axes[0].get_lines()[1]

    def set_figure(self, fig: Figure | None):
        """Set the figure of this widget."""
        self.canvas.set_figure(fig)
        self.canvas.figure = fig
        if fig is not None:
            ax = fig.get_axes()[0]
            self.line = ax.get_lines()[1]


class DiagnosticsCanvas(ScrollableCanvas):
    """Widget for displaying all the resonator plots from an LO sweep."""

    def __init__(self, parent=None):
        """Initialize a DiagnosticsCanvas."""
        super().__init__(parent)
        self.selected_axes: plt.Axes | None = None
        self.edited_axes = set()

    def set_figure(self, fig: Figure):
        """Set the figure of this canvas."""
        self.unflagged = fig.axes.copy()
        super().set_figure(fig)
        # All of the axes need to be animated, so add them to the blit manager
        for ax in self.canvas.figure.axes:
            self.bm.add_artist(fig, ax.patch)
            self.bm.add_artist(fig, ax)

    def set_flagged(self, flagged: npt.NDArray):
        """Update the list of flagged plots."""
        self.unflagged = np.delete(self.canvas.figure.axes, flagged)

    def show_all(self):
        """Show all axes."""
        for ax in self.unflagged:
            ax.set_visible(True)
            ax.patch.set_visible(True)
        self.bm.update()

    def hide_unflagged(self):
        """Hide all the unflagged axes."""
        for ax in self.unflagged:
            if self.selected_axes == ax:
                self.select_axis(None)
            ax.set_visible(False)
            ax.patch.set_visible(False)
        self.bm.update()

    def get_ax_by_index(self, idx: int) -> plt.Axes:
        return self.figure.get_axes()[idx]

    def is_edited(self, ax: plt.axes) -> bool:
        return self.figure.get_axes().index(ax) in self.edited_axes

    def select_axis(self, axes: plt.Axes | None):
        """Select the provided axes.

        Draws a highlight around the axes and deselects the previous axes if there
        was one.
        """
        fig = self.canvas.figure
        # Deselect previous axes
        if self.selected_axes is not None:
            ax = self.selected_axes
            # Clear the outline by drawing a white outline over it
            ax.patch.set_linewidth(6)
            ax.patch.set_edgecolor('w')
            fig.draw_artist(ax.patch)

            ax.patch.set_linewidth(0)
            self.bm.update_artists(
                [
                    (ax.patch, ax.patch.get_tightbbox()),
                    (ax, ax.bbox),
                ]
            )

            if self.is_edited(ax):
                self.add_edited_marker(ax)
        # Select new axes
        if axes is not None:
            axes.patch.set_linewidth(5)
            axes.patch.set_edgecolor(SELECTED_RESONANCE_COLOR)
            self.bm.update_artists(
                [
                    (axes.patch, axes.patch.get_clip_box()),
                    (axes, axes.bbox),
                ]
            )
        self.selected_axes = axes
        self.canvas.blit()
        self.canvas.flush_events()

    def add_edited_marker(self, ax: plt.Axes):
        """Draw a rectangle around an axes indicating it has been edited."""
        ax.patch.set_linewidth(5)
        ax.patch.set_edgecolor(EDITED_RESONANCE_COLOR)

        self.bm.update_artists(
            [
                (ax.patch, ax.patch.get_tightbbox()),
                (ax, ax.bbox),
            ]
        )

    def set_edited(self, idx: int):
        self.edited_axes.add(idx)
        ax = self.get_ax_by_index(idx)
        if ax != self.selected_axes:
            self.add_edited_marker(ax)


if __name__ == '__main__':
    import sys

    from PySide6.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)
    fig = plt.figure()
    ax = plt.subplot()
    canvas = ResonatorCanvas()
    ax.plot(np.random.rand(10))
    ax.axvline(0.5, color='red')
    canvas.set_figure(fig)
    win = QMainWindow()
    win.setCentralWidget(canvas)
    win.show()
    sys.exit(app.exec())
