Architecture
============

.. code-block:: text

   your package                          scene-streamer                     the page
   +---------------------------+         +-------------------------+        +----------------+
   | Scene  (+ Camera)         |<--------| Hub (aiohttp thread)    |<-ws--->| viewer.js      |
   | Renderer (GL thread)      |<-Worker-| one Session per viewer  |        | WebCodecs/JPEG |
   +---------------------------+         | JPEG / H.264 encoders   |        | labels, picking|
                                         +-------------------------+        +----------------+

The scene and the renderer belong to the package that uses scene-streamer. The
hub asks them for frames and passes the page's camera gestures to the scene's
camera. Nothing in scene-streamer imports that package; it only calls the
methods of the protocols in :mod:`scene_streamer.protocols`.

An OpenGL context belongs to the thread that made it, so every renderer call
goes through a :class:`~scene_streamer.protocols.Worker`: the hub runs
``worker.run(fn)`` and ``fn`` receives the renderer on its own thread. The
worker is given with :func:`scene_streamer.configure` and is only created when
the first frame is needed, so starting the server never touches the GPU.

What a viewer does
------------------

1. The page opens a websocket to ``/ws`` (with the token), sends ``open`` and
   ``scene`` for each viewer it shows, and ``cfg`` with the codec it can decode.
2. The hub sends ``meta`` (labels, field of view, number of triangles, scene
   version), then renders and encodes frames whenever the scene or the camera
   changes and the viewer is visible.
3. The page acknowledges every frame after decoding it. At most two frames are in
   flight, and the quality moves up and down with the round-trip time.
4. When input stops for 0.2 s the hub sends one lossless still.
5. A hidden viewer (``visible`` false), a frozen page (frames in flight and no
   message for 5 s) or a closed page releases what it held on the GPU. A silent
   connection is closed after ``stale`` seconds (live pages ping every 5 s).

Messages from the page are JSON with a type ``t`` and the viewer id ``v``:

.. list-table::
   :widths: 18 82

   * - ``open``, ``close``
     - start or end a viewer
   * - ``scene``
     - show the scene with this ``id``
   * - ``cfg``
     - ``codec`` (``h264``, ``nvenc`` or ``jpeg``), ``quality``, the window size ``win``, ``adapt``
   * - ``resize``
     - the viewer's size in pixels
   * - ``drag``, ``pan``, ``wheel``
     - camera gestures, forwarded to the scene's camera
   * - ``pose``, ``getpose``
     - set or read the camera pose
   * - ``reset``
     - face the content again
   * - ``pick``
     - ``x``, ``y`` and a ``req`` id; answered with ``picked``
   * - ``visible``
     - ``on`` is false while the viewer is scrolled out of view
   * - ``ack``
     - a frame was decoded
   * - ``ping``
     - keep-alive, answered with ``pong``

Frames are binary websocket messages: a header of 87 bytes (little-endian
``<BHIdff16f``: kind, viewer id, sequence number, the client timestamp of the
input it answers, render and encode time in milliseconds, and the 4x4
view-projection matrix, row-major) followed by the payload. The kind is
``0`` for an H.264 delta frame, ``1`` for a keyframe (Annex B, with SPS and PPS),
``2`` for a JPEG and ``3`` for the lossless still (a JPEG at quality 95).

Routes
------

.. list-table::
   :widths: 40 60

   * - ``/viewer.js``
     - the client module (public code, CORS allowed)
   * - ``/view?scene=...``
     - a page showing one scene
   * - ``/ws``
     - the websocket
   * - ``/snapshot.png?scene=...&w=...&h=...``
     - one frame as a PNG
   * - ``/stats``
     - clients, viewers, scenes and the renderer's own ``stats()``

All routes except ``/viewer.js`` need ``token=`` (a random token made when the
hub is created).

Messages and frames are handled in the order they arrive. Do not replace that
with ``call_later(0)``: on a coarse clock (Windows ticks about every 15 ms) timers
made in the same tick have equal due times and asyncio does not keep those in
order.

The protocols
-------------

.. automodule:: scene_streamer.protocols
   :members:
   :undoc-members:
