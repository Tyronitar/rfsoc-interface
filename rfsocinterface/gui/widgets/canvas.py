import warnings
from typing import Callable, Concatenate
from pathlib import Path
from enum import Enum


import matplotlib as mpl
mpl.use('QtAgg')
mpl.rcParams['toolbar'] = 'toolbar2'

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QWheelEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt import FigureManagerQT, NavigationToolbar2QT
from matplotlib.backend_bases import _Mode
from matplotlib.backend_tools import ToolToggleBase, Cursors, ToolBase, ConfigureSubplotsBase
from matplotlib.figure import Figure

from rfsocinterface.gui.blit_manager import BlitManager
from rfsocinterface.gui.widgets.utils import layout_widgets
from rfsocinterface.core.utils import P
from rfsocinterface.gui.uic import icons_rc

# with warnings.catch_warnings():
#     warnings.simplefilter('ignore')
#     # Set the default toolbar to use the tool manager
#     plt.rcParams['toolbar'] = 'toolmanager'


class EditTool(ToolToggleBase):
    default_keymap = 'e'
    description = 'Edit the plot'
    default_toggled = False
    image = ':/icons/edit.svg'
    radio_group = 'default'

class AddTool(ToolBase):
    description = 'Add a vertical line to the plot'
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

    def replot_figure(self, plotting_function: Callable[Concatenate[Figure, P], None], *args: P.args, **kwargs: P.kwargs):
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
            add_group: bool=False,
            add_edit_button: bool=False,
            add_function: Callable=None,
            remove_function: Callable=None,
            undo_function: Callable=None,
            redo_function: Callable=None,
            ):
        self.add_function = add_function
        self.remove_function = remove_function
        self.undo_function = undo_function
        self.redo_function = redo_function
        add_group = add_group or add_edit_button or \
            (add_function is not None) or \
            (remove_function is not None) or \
            (undo_function is not None) or \
            (redo_function is not None)
        new_group = []
        if add_group:
            new_group.append((None, None, None, None))
        if add_edit_button:
            new_group.append(('Edit', EditTool.description, EditTool.image, 'toggle_edit'))
        if add_function is not None:
            new_group.append(('Add', AddTool.description, AddTool.image, 'add'))
        if remove_function is not None:
            new_group.append(('Remove', RemoveTool.description, RemoveTool.image, 'remove'))
        if undo_function is not None:
            new_group.append(('Undo', UndoTool.description, UndoTool.image, 'undo'))
        if redo_function is not None:
            new_group.append(('Redo', RedoTool.description, RedoTool.image, 'redo'))

        # Insert new group after 'customize'
        toolitems = [*NavigationToolbar2QT.toolitems]
        i = [name for name, *_ in toolitems].index("Customize") + 1
        for item in new_group:
            toolitems.insert(i, item)
            i += 1
        self.toolitems = toolitems


        super().__init__(canvas, parent, coordinates)
        if add_edit_button:
            self._actions['toggle_edit'].setCheckable(True)
    
    def _icon(self, name: str):
        if name[0] == ':':
            # We're attempting to access a QResource File
            name = name[:-4]  # get rid of the .png added by the parent class
            return QIcon(QPixmap(name))

        return super()._icon(name)
    
    @property
    def editing(self) -> bool:
        return self.mode == EditMode.EDIT
    
    def toggle_edit(self):
        if self.editing:
            self.mode = _Mode.NONE
        else:
            self.mode = EditMode.EDIT
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
            fig: Figure | None=None,
            add_edit: bool=False,
            coordinates: bool=True,
            add_function: Callable=None,
            remove_function: Callable=None,
            undo_function: Callable=None,
            redo_function: Callable=None,
            ):
        """Initialize a ResonatorCanvas."""
        super().__init__(parent)
        if fig is None:
            fig = Figure(figsize=(8, 5))
        self.scrollable_canvas = ScrollableCanvas(self)
        self.scrollable_canvas.set_figure(fig)
        self.nav = EditToolBar(
            self.figure_canvas,
            parent,
            coordinates=coordinates,
            add_edit_button=add_edit,
            add_function=add_function,
            remove_function=remove_function,
            undo_function=undo_function,
            redo_function=redo_function,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        layout.addWidget(self.nav)
        layout.addWidget(self.scrollable_canvas)
    
    @property
    def editing(self) -> bool:
        return self.nav.editing

    @property
    def figure(self) -> Figure:
        return self.scrollable_canvas.figure

    @property
    def figure_canvas(self) -> FigureCanvas:
        return self.scrollable_canvas.canvas
    
    def update_figure(self):
        """Update the figure of this widget."""
        self.update()

    def set_figure(self, fig: Figure | None):
        """Set the figure of this widget."""
        self.scrollable_canvas.set_figure(fig)
        layout = self.layout()
        print(f'Before removal: {layout_widgets(layout)}')
        # layout.removeWidget(self.nav)
        # print(f'After removal: {layout_widgets(layout)}')

        old_nav = self.nav
        self.manager = FigureManagerQT(self.scrollable_canvas, 1)
        self.scrollable_canvas.manager = self.manager
        self.nav = self.manager.toolbar
        layout.replaceWidget(old_nav, self.nav)
        print(f'End Result: {layout_widgets(layout)} total = {layout.count()}')
        print(self.scrollable_canvas)
    
    def replot_figure(self, plotting_function: Callable[Concatenate[Figure, P], None], *args: P.args, **kwargs: P.kwargs):
        self.scrollable_canvas.replot_figure(plotting_function, *args, **kwargs)
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

    def replot_figure(self, plotting_function: Callable[Concatenate[Figure, P], None], *args: P.args, **kwargs: P.kwargs):
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

    def select_axis(self, axes: plt.Axes | None):
        """Select the provided axes.

        Draws a blue highlight around the axes and deselects the previous axes if there
        was one.
        """
        fig = self.canvas.figure
        # Deselect previous axes
        if self.selected_axes is not None:
            ax = self.selected_axes
            # Clear the blue outline by drawing a white outline over it
            ax.patch.set_linewidth(6)
            ax.patch.set_edgecolor('w')
            fig.draw_artist(ax.patch)

            ax.patch.set_linewidth(0)
            self.bm.update_artists([
                (ax.patch, ax.patch.get_tightbbox()),
                (ax, ax.bbox),
            ])
        # Select new axes
        if axes is not None:
            axes.patch.set_linewidth(5)
            axes.patch.set_edgecolor('cornflowerblue')
            self.bm.update_artists([
                (axes.patch, axes.patch.get_clip_box()),
                (axes, axes.bbox),
            ])
        self.selected_axes = axes
        self.canvas.blit()
        self.canvas.flush_events()


if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication, QMainWindow
    import sys

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