"""Stream frames from an OpenGL scene renderer to a browser, a notebook widget or an app window.

The package that owns the scene and the renderer gives the hub a worker with
``scene_streamer.configure(worker=...)`` (see :mod:`scene_streamer.protocols`); after that

* ``get_hub().view_url(scene)`` is a page to open in any browser,
* :func:`scene_streamer.window.show` opens it in an app window,
* :class:`scene_streamer.widget.FigureWidget` embeds it in a Jupyter notebook (``pip install "scene-streamer[notebook]"``).
"""

from .hub import Hub, configure, get_hub

try:
    from ._version import __version__
except ImportError:  # running from a source tree without a build
    from importlib.metadata import PackageNotFoundError, version

    try:
        __version__ = version("scene-streamer")
    except PackageNotFoundError:
        __version__ = "0+unknown"

__all__ = ["Hub", "configure", "get_hub", "__version__"]
