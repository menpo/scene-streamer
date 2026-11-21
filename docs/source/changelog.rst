.. _changelog:

Changelog
#########

0.1.0 (2026/11/21)
------------------

The first release. scene-streamer was extracted from the interactive viewer of
`menpo3d <https://github.com/menpo/menpo3d>`_ so that anything with an OpenGL
scene renderer can be shown in a browser, a Jupyter notebook or an app window.

- The **hub**: a small ``aiohttp`` server in a thread of the process that owns
  the scene. A page connects with one websocket for any number of viewers, sends
  camera gestures (rotate, pan, zoom, pick) and receives frames: H.264 while the
  camera moves (with the optional ``scene-streamer[h264]`` extra), JPEG
  otherwise, and a lossless still when the input stops. The quality follows the
  speed of the link. Viewers that are scrolled out of view or frozen are not
  rendered, and everything a viewer held on the GPU is released when its page
  goes away.
- The **page** (``viewer.js``): decodes with WebCodecs where available and falls
  back to JPEG; draws labels and does picking itself from the frame's
  view-projection matrix.
- ``scene_streamer.widget.FigureWidget``: a Jupyter widget (``anywidget``;
  install ``scene-streamer[notebook]``) that keeps a still in the saved
  notebook.
- ``scene_streamer.window.show``: a Chromium app window on the same page.
- ``scene_streamer.protocols``: the whole contract with the package that owns
  the scene and the renderer (``Scene``, ``Camera``, ``Renderer``, ``Worker``),
  given with ``scene_streamer.configure(worker=...)``. scene-streamer imports
  nothing from that package, and its tests run against a fake renderer.
- A page's messages and the frames sent back are handled in the order they
  arrive, also on Windows' coarse clock (timers made in the same tick have equal
  due times, and asyncio does not keep those in order).

Every route except ``/viewer.js`` needs the hub's token, and the server binds to
127.0.0.1 unless ``configure(host=...)`` says otherwise.
