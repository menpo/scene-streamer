# scene-streamer

Stream frames from an OpenGL scene renderer to a browser, a Jupyter notebook widget or an app window.

The renderer runs in your Python process (on a machine with a GPU, or a software OpenGL). scene-streamer runs a small
web server in a thread of the same process. A page connects with a websocket, sends camera gestures (rotate, pan, zoom,
pick) and receives frames: H.264 while the camera moves, a lossless still when it stops. Because the scene lives in
your process, changing it from Python redraws every attached viewer.

* one websocket carries any number of viewers, so ten notebook widgets cost one connection;
* viewers that are scrolled out of view or frozen are not rendered, and everything a viewer held on the GPU is
  released when its page goes away;
* quality follows the speed of the link, so it works over SSH or a jupyter-server-proxy;
* labels and picking are done by the page from the frame's view-projection matrix, so the server never draws text.

It knows nothing about meshes or OpenGL. The package that owns the scene and the renderer supplies them by following
the protocols in [`scene_streamer/protocols.py`](scene_streamer/protocols.py).
[menpo3d](https://github.com/menpo/menpo3d) is the first such package (`mesh.view()`).

## Install

```
pip install scene-streamer                  # the hub and a browser page
pip install "scene-streamer[notebook]"      # + the Jupyter widget (anywidget)
pip install "scene-streamer[h264]"          # + H.264 video (PyAV, which bundles ffmpeg)
pip install "scene-streamer[all]"
```

Without PyAV, frames are sent as JPEG (and Python warns once that a viewer asked for H.264). Browsers without
WebCodecs (Firefox, Safari) always get JPEG. PyAV's wheels bundle x264, which is GPL: install the extra only if that
is acceptable for what you distribute.

## Use

```python
import scene_streamer

scene_streamer.configure(
    worker=get_worker
)  # once: how to reach the renderer's GL thread
hub = scene_streamer.get_hub()
hub.register(scene)
print(hub.view_url(scene))  # open in any browser
```

```python
from scene_streamer.window import (
    show,
)  # a Chromium "app" window; blocks until it is closed
from scene_streamer.widget import (
    figure_widget,
)  # a notebook widget (needs the `notebook` extra)
```

`configure(host="0.0.0.0", public_url="https://box/proxy/8765")` before the first viewer makes the server reachable
from another machine. Every route except `/viewer.js` needs the hub's token, which is part of the URLs it hands out.
The server binds to 127.0.0.1 by default.

## Develop

```
uv sync
uv run pytest
```

The tests use a fake scene and renderer (`tests/fakes.py`), so they need no GPU.

## Releasing

Push a `vX.Y.Z` tag. The `release` workflow builds the sdist and wheel, checks them, and publishes to PyPI by trusted
publishing (environment `pypi`). A manual run with `publish: testpypi` is a dry run.

BSD 3-clause licence.
