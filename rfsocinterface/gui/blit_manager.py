from typing import Iterable

import matplotlib as mpl

mpl.use('QtAgg')
import matplotlib.pyplot as plt
from matplotlib.artist import Artist
from matplotlib.backend_bases import DrawEvent
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.transforms import Bbox


class BlitManager:
    """Manager for handling drawing and blitting of animated artists."""

    def __init__(self, canvas: FigureCanvas, animated_artists: Iterable[Artist] = ()):
        """Initialize a BlitManager.

        Arguments:
            canvas (FigureCanvasAgg): The canvas to work with, this only works for
                subclasses of the Agg canvas which have the
                `~FigureCanvasAgg.copy_from_bbox` and `~FigureCanvasAgg.restore_region`
                methods.
            animated_artists (Iterable[Artist]): List of artists to manage. Defaults
                to ().
        """
        self.canvas = canvas
        self._bg = None
        self._artists = []

        for a in animated_artists:
            self.add_artist(a)
        # Grab the background on every draw
        self.cid = canvas.mpl_connect('draw_event', self.on_draw)

    def on_draw(self, event: DrawEvent):
        """Callback to register with 'draw_event'."""
        cv = self.canvas
        if event is not None:
            if event.canvas != cv:
                raise RuntimeError
        # Copy the background before drawing
        self._bg = cv.copy_from_bbox(cv.figure.bbox)
        self._draw_animated()

    def add_artist(self, parent: Figure | plt.Axes, art: Artist):
        """Add an artist to be managed.

        Arguments:
            parent (Figure | plt.Axes): The parent responsible for drawing the artist.
            art (Artist): The artist to be added.  Will be set to 'animated' (just to be
                safe).  *art* must be in the figure associated with the canvas this
                class is managing.
        """
        if art.figure != self.canvas.figure:
            raise RuntimeError
        art.set_animated(True)
        self._artists.append((parent, art))

    def update_artists(self, artists: list[tuple[Artist, Bbox]]):
        """Update the screen around each of the artists in the provided list."""
        cv = self.canvas
        for a, bbox in artists:
            cv.restore_region(cv.copy_from_bbox(bbox))
            cv.figure.draw_artist(a)

    def _draw_animated(self):
        """Draw all of the animated artists."""
        for p, a in self._artists:
            p.draw_artist(a)

    def update(self):
        """Update the screen with animated artists."""
        cv = self.canvas
        fig = cv.figure
        # Paranoia in case we missed the draw event,
        if self._bg is None:
            self.on_draw(None)
        else:
            # Restore the background
            cv.restore_region(self._bg)
            # Draw all of the animated artists
            self._draw_animated()
            # Update the GUI state
            cv.blit(fig.bbox)
        # Let the GUI event loop process anything it has to do
        cv.flush_events()
