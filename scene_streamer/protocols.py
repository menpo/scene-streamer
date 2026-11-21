"""What scene-streamer needs from the package that owns the scene and the renderer.

scene-streamer knows nothing about meshes or OpenGL. It serves *scenes* to browsers: it forwards the page's camera
gestures to the scene's camera, asks the renderer for a frame, encodes it and sends it. These protocols are the whole
contract; any objects with these methods work (``menpo3d`` provides them for its OpenGL viewer).

The renderer lives on one thread (an OpenGL context belongs to the thread that made it), so every renderer call goes
through a :class:`Worker`.
"""

from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class Camera(Protocol):
    """The camera of a scene. The gestures come from the page (pixels or wheel steps)."""

    fov: float
    azimuth: float
    elevation: float

    def copy(self) -> "Camera":
        """A snapshot to render with on the GL thread while the page keeps moving the live camera."""

    def orbit(self, dx: float, dy: float) -> None: ...

    def pan(self, dx: float, dy: float, height: int) -> None:
        """``height`` is the viewer's height in pixels."""

    def zoom(self, dy: float) -> None: ...

    def get_pose(self) -> dict:
        """JSON-serialisable; passed back to ``set_pose(**pose)``."""

    def set_pose(self, **pose: Any) -> None: ...


@runtime_checkable
class Scene(Protocol):
    """Something to show. Changing it from any thread must call every function in ``listeners`` with the scene."""

    id: str
    version: int
    camera: Camera
    listeners: list[Callable[["Scene"], None]]

    def labels(self) -> list[dict]:
        """Text the page draws itself on top of the frame: ``[{"text": ..., ...}]``, JSON-serialisable."""

    def n_triangles(self) -> int:
        """Shown to the page next to a pick (0 if the scene has no triangles)."""

    def ensure_camera(self) -> None:
        """Frame the content if the camera has not been placed yet."""

    def fit_camera(self) -> None:
        """Re-frame the content (the page's reset button)."""


@runtime_checkable
class Renderer(Protocol):
    """Draws scenes. Only ever called on the worker's thread."""

    def acquire(self, scene: Scene) -> None:
        """A viewer starts showing ``scene``: upload what it needs to the GPU."""

    def release(self, scene: Scene) -> None:
        """A viewer stopped showing ``scene``: free its GPU memory once nobody else holds it."""

    def release_framebuffers(self) -> None:
        """No viewer is connected any more: free the frame buffers."""

    def render(
        self, scene: Scene, camera: Camera, width: int, height: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """``(rgb, matrix)``: an ``(height, width, 3)`` uint8 frame and the 4x4 view-projection matrix it was drawn
        with (row-major, so the page can place its labels and pick rays)."""

    def pick(
        self, scene: Scene, camera: Camera, width: int, height: int, x: float, y: float
    ) -> dict | None:
        """What is under pixel ``(x, y)``: a JSON-serialisable dict (the page shows ``tri`` and ``vertex``), or None."""

    def stats(self) -> dict:
        """For ``/stats``: ``{"gpu": {scene id: number of viewers holding it}, "fbos": number of frame buffers}``."""


@runtime_checkable
class Worker(Protocol):
    """Runs functions on the renderer's thread."""

    def run(self, fn: Callable[..., Any], *args: Any) -> Awaitable[Any]:
        """Await ``fn(renderer, *args)`` run on the GL thread."""


@runtime_checkable
class Figure(Protocol):
    """What the notebook widget and the window need to show a scene."""

    scene: Scene
    size: tuple[int, int]
    persist_still: bool
