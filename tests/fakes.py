"""A scene, a camera, a renderer and a worker that satisfy scene_streamer.protocols without OpenGL."""

import asyncio
import itertools
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

_ids = itertools.count(1)


class FakeCamera:
    def __init__(self):
        self.azimuth, self.elevation, self.fov, self.zoomed = 0.0, 0.0, 35.0, 0.0

    def copy(self):
        other = FakeCamera()
        other.__dict__.update(self.__dict__)
        return other

    def orbit(self, dx, dy):
        self.azimuth += dx * 0.01
        self.elevation += dy * 0.01

    def pan(self, dx, dy, height):
        pass

    def zoom(self, dy):
        self.zoomed += dy

    def get_pose(self):
        return dict(azimuth=self.azimuth, elevation=self.elevation, fov=self.fov)

    def set_pose(self, azimuth, elevation, fov=35.0, **_):
        self.azimuth, self.elevation, self.fov = azimuth, elevation, fov


class FakeScene:
    def __init__(self, n_triangles=12, labels=("a", "b")):
        self.id = f"scene{next(_ids)}"
        self.version, self.camera, self.listeners = 0, FakeCamera(), []
        self._labels, self._n = list(labels), n_triangles
        self.placed = False

    def labels(self):
        return [dict(text=t, x=0.0, y=0.0, z=0.0) for t in self._labels]

    def n_triangles(self):
        return self._n

    def ensure_camera(self):
        self.placed = True

    def fit_camera(self):
        self.camera.zoomed = 0.0

    def change(self):
        """What a real scene does when its content changes, from whatever thread."""
        self.version += 1
        for listener in list(self.listeners):
            listener(self)


class FakeRenderer:
    """Draws a flat colour that depends on the camera and the scene's version, so frames differ."""

    def __init__(self):
        self.held, self.fbos, self.thread = {}, set(), None

    def acquire(self, scene):
        self._on_gl_thread()
        self.held[scene.id] = self.held.get(scene.id, 0) + 1

    def release(self, scene):
        self._on_gl_thread()
        n = self.held.get(scene.id, 0) - 1
        if n > 0:
            self.held[scene.id] = n
        else:
            self.held.pop(scene.id, None)

    def release_framebuffers(self):
        self.fbos.clear()

    def render(self, scene, camera, width, height):
        self._on_gl_thread()
        self.fbos.add((width, height))
        rng = np.random.RandomState(int(abs(camera.azimuth * 100)) + scene.version)
        rgb = np.empty((height, width, 3), np.uint8)
        rgb[:] = rng.randint(0, 255, 3)
        rgb[::7] //= 2  # not a flat image, so the codecs have something to code
        return rgb, np.eye(4, dtype=np.float32)

    def pick(self, scene, camera, width, height, x, y):
        self._on_gl_thread()
        if abs(x - width / 2) < width / 4 and abs(y - height / 2) < height / 4:
            return dict(tri=3, vertex=7)
        return None

    def stats(self):
        return dict(gpu=dict(self.held), fbos=len(self.fbos))

    def _on_gl_thread(self):
        """Every call must come from one thread, like an OpenGL context."""
        me = threading.get_ident()
        if self.thread is None:
            self.thread = me
        assert self.thread == me, "the renderer was used from two threads"


class FakeWorker:
    def __init__(self):
        self.renderer = FakeRenderer()
        self.pool = ThreadPoolExecutor(1, thread_name_prefix="fake-gl")

    def run(self, fn, *args):
        return asyncio.get_running_loop().run_in_executor(
            self.pool, fn, self.renderer, *args
        )


class FakeFigure:
    def __init__(self, scene=None, size=(320, 240)):
        self.scene, self.size, self.persist_still = scene or FakeScene(), size, True
