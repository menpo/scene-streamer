"""The streaming hub, driven the way a browser drives it: a websocket carrying JSON requests and binary frames."""

import asyncio
import json
import sys

import numpy as np
import pytest

import aiohttp
from fakes import FakeScene, FakeWorker
from scene_streamer.codecs import have_h264
from scene_streamer.hub import HEADER, JPEG, KEY, STILL, Hub


@pytest.fixture(scope="module")
def hub():
    worker = FakeWorker()
    h = Hub(stale=2.0, worker=lambda: worker)
    h.start()
    h.fake = worker
    yield h
    h.stop()


@pytest.fixture
def scene(hub):
    s = FakeScene()
    hub.register(s)
    return s


def run(coro):
    return asyncio.run(coro)


class Page:
    """What viewer.js does for each viewer on one socket."""

    def __init__(self, ws, hub):
        self.ws, self.hub, self.frames, self.json, self.next_id = ws, hub, [], [], 1

    async def send(self, **msg):
        await self.ws.send_str(json.dumps(msg))

    async def open(self, scene, w=160, h=120, codec="jpeg"):
        vid, self.next_id = self.next_id, self.next_id + 1
        await self.send(t="open", v=vid)
        await self.send(t="scene", v=vid, id=scene.id)
        await self.send(t="cfg", v=vid, codec=codec, adapt=False)
        await self.send(t="resize", v=vid, w=w, h=h)
        await self.send(t="drag", v=vid, dx=1, dy=0, ts=1)
        return vid

    async def pump(self, seconds=0.5, ack=True):
        """Read for a while; acknowledge frames like the page does after decoding them."""
        end = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < end:
            try:
                m = await asyncio.wait_for(self.ws.receive(), 0.1)
            except asyncio.TimeoutError:
                continue
            if m.type == aiohttp.WSMsgType.BINARY:
                head = HEADER.unpack_from(m.data)
                self.frames.append(
                    dict(
                        kind=head[0],
                        vid=head[1],
                        seq=head[2],
                        mvp=np.array(head[6:]).reshape(4, 4),
                        payload=m.data[HEADER.size :],
                    )
                )
                if ack:
                    await self.send(t="ack", v=head[1])
            elif m.type == aiohttp.WSMsgType.TEXT:
                self.json.append(json.loads(m.data))

    def of(self, vid):
        return [f for f in self.frames if f["vid"] == vid]


def connect(hub, token=None):
    async def go():
        session = aiohttp.ClientSession()
        ws = await session.ws_connect(
            f"{hub.url}/ws?token={hub.token if token is None else token}",
            max_msg_size=0,
        )
        return session, ws

    return go()


async def astats(session, hub):
    async with session.get(f"{hub.url}/stats?token={hub.token}") as r:
        return await r.json()


def test_the_token_is_required(hub):
    async def go():
        async with aiohttp.ClientSession() as s:
            for path in ("/stats", "/ws", "/view?scene=x", "/snapshot.png?scene=x"):
                async with s.get(hub.url + path) as r:
                    assert r.status == 403, path
                async with s.get(
                    hub.url + path + ("&" if "?" in path else "?") + "token=wrong"
                ) as r:
                    assert r.status == 403, path
            async with s.get(
                f"{hub.url}/viewer.js"
            ) as r:  # the script itself is public code
                assert (
                    r.status == 200 and r.headers["Access-Control-Allow-Origin"] == "*"
                )

    run(go())


def test_a_viewer_gets_meta_then_frames_tagged_with_its_id_and_the_matrix(hub, scene):

    async def go():
        session, ws = await connect(hub)
        page = Page(ws, hub)
        vid = await page.open(scene)
        await page.pump(1.0)
        await ws.close()
        await session.close()
        return page, vid

    page, vid = run(go())
    meta = [m for m in page.json if m["t"] == "meta"][0]
    assert (
        meta["v"] == vid
        and meta["n_tris"] == scene.n_triangles()
        and [l["text"] for l in meta["labels"]] == ["a", "b"]
    )
    frames = page.of(vid)
    assert (
        frames
        and frames[0]["kind"] in (JPEG, KEY)
        and frames[0]["payload"][:2] == b"\xff\xd8"
    )
    # the renderer's view-projection matrix reaches the page unchanged (it places labels and pick rays)
    assert frames[-1]["mvp"] == pytest.approx(np.eye(4))


def test_h264_frames_start_with_a_keyframe(hub, scene):
    pytest.importorskip("av")

    async def go():
        session, ws = await connect(hub)
        page = Page(ws, hub)
        vid = await page.open(scene, codec="h264")
        await page.pump(1.0)
        await ws.close()
        await session.close()
        return page.of(vid)

    frames = run(go())
    assert frames[0]["kind"] == KEY and frames[0]["payload"][:4] == b"\x00\x00\x00\x01"


def test_a_still_follows_when_the_input_stops(hub, scene):

    async def go():
        session, ws = await connect(hub)
        page = Page(ws, hub)
        vid = await page.open(scene)
        await page.pump(1.0)
        await ws.close()
        await session.close()
        return page.of(vid)

    kinds = [f["kind"] for f in run(go())]
    assert kinds[-1] == STILL and kinds.count(STILL) == 1


def test_ten_viewers_share_one_socket_and_each_gets_its_own_frames(hub, scene):

    async def go():
        session, ws = await connect(hub)
        page = Page(ws, hub)
        ids = [await page.open(scene, w=64, h=48) for _ in range(10)]
        await page.pump(1.5)
        stats = await (await session.get(f"{hub.url}/stats?token={hub.token}")).json()
        await ws.close()
        await session.close()
        return page, ids, stats

    page, ids, stats = run(go())
    assert stats["clients"] == 1 and stats["viewers"] == 10
    assert all(page.of(v) for v in ids)


def test_hidden_viewers_stop_and_give_their_gpu_buffers_back_and_resume_with_a_keyframe(
    hub, scene
):
    errors = []  # an exception inside a hub callback is only logged by asyncio: collect it
    hub.loop.set_exception_handler(lambda loop, context: errors.append(context))

    async def go():
        session, ws = await connect(hub)
        page = Page(ws, hub)
        vid = await page.open(scene, codec="h264")
        await page.pump(0.6)
        live = (await astats(session, hub))["gpu"]
        await page.send(t="visible", v=vid, on=False)
        await page.pump(0.4)
        hidden = (await astats(session, hub))["gpu"]
        n = len(page.of(vid))
        await page.send(
            t="drag", v=vid, dx=5, dy=0, ts=2
        )  # input while hidden must not render
        await page.pump(0.6)
        still_hidden = len(page.of(vid)) == n
        await page.send(t="visible", v=vid, on=True)
        await page.pump(0.8)
        after = page.of(vid)[n:]
        await ws.close()
        await session.close()
        return live, hidden, still_hidden, after

    live, hidden, still_hidden, after = run(go())
    hub.loop.set_exception_handler(None)
    assert not errors
    assert scene.id in live and scene.id not in hidden and still_hidden
    # a fresh encoder starts with a keyframe (JPEG frames are all independent)
    assert after and after[0]["kind"] == (KEY if have_h264() else JPEG)


def test_closing_a_viewer_or_the_socket_releases_everything(hub, scene):

    async def go():
        session, ws = await connect(hub)
        page = Page(ws, hub)
        a = await page.open(scene)
        await page.open(scene)
        await page.pump(0.5)
        both = (await astats(session, hub))["gpu"][scene.id]
        await page.send(t="close", v=a)
        await page.pump(0.3)
        one = (await astats(session, hub))["gpu"][scene.id]
        await ws.close()
        await asyncio.sleep(0.5)
        final = await astats(session, hub)
        await session.close()
        return both, one, final

    both, one, final = run(go())
    assert (
        (both, one) == (2, 1)
        and scene.id not in final["gpu"]
        and final["fbos"] == 0
        and final["clients"] == 0
    )


def test_changing_the_scene_from_python_redraws_attached_viewers(hub, scene):

    async def go():
        session, ws = await connect(hub)
        page = Page(ws, hub)
        vid = await page.open(scene)
        await page.pump(0.8)
        n = len(page.of(vid))
        scene.change()  # from this (another) thread
        await page.pump(0.8)
        await ws.close()
        await session.close()
        return page, vid, n

    page, vid, n = run(go())
    assert len(page.of(vid)) > n
    assert [m for m in page.json if m["t"] == "meta"][-1]["version"] == scene.version


def test_picking_returns_the_triangle_under_the_pixel(hub, scene):

    async def go():
        session, ws = await connect(hub)
        page = Page(ws, hub)
        vid = await page.open(scene)
        await page.pump(0.6)
        await page.send(t="pick", v=vid, x=80.0, y=60.0, req=7)
        await page.send(t="pick", v=vid, x=1.0, y=1.0, req=8)
        await page.pump(0.6)
        await ws.close()
        await session.close()
        return {m["req"]: m["hit"] for m in page.json if m["t"] == "picked"}

    hits = run(go())
    assert hits[7]["tri"] >= 0 and hits[8] is None


def test_pose_round_trips_and_an_unknown_scene_is_reported(hub, scene):

    async def go():
        session, ws = await connect(hub)
        page = Page(ws, hub)
        vid = await page.open(scene)
        pose = {**scene.camera.get_pose(), "azimuth": 1.25}
        await page.send(t="pose", v=vid, pose=pose, ts=3)
        await page.send(t="getpose", v=vid)
        bad = page.next_id
        await page.send(t="open", v=bad)
        await page.send(t="scene", v=bad, id="nope")
        await page.pump(0.6)
        await ws.close()
        await session.close()
        return page

    page = run(go())
    assert [m for m in page.json if m["t"] == "pose"][-1]["pose"]["azimuth"] == 1.25
    assert "unknown scene" in [m for m in page.json if m["t"] == "error"][0]["message"]


def test_a_silent_connection_is_closed_and_its_viewers_released(hub, scene):

    async def go():
        session, ws = await connect(hub)
        page = Page(ws, hub)
        await page.open(scene)
        await page.pump(0.5)
        assert (await astats(session, hub))["clients"] == 1
        for _ in range(60):  # say nothing: no pings, no acks
            await asyncio.sleep(0.1)
            try:
                m = await asyncio.wait_for(ws.receive(), 0.01)
                if m.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSING,
                ):
                    break
            except asyncio.TimeoutError:
                pass
        await asyncio.sleep(0.3)
        final = await astats(session, hub)
        await session.close()
        return final

    final = run(go())
    assert final["clients"] == 0 and scene.id not in final["gpu"]


def test_the_snapshot_route_renders_a_png(hub, scene):

    async def go():
        async with (
            aiohttp.ClientSession() as s,
            s.get(
                f"{hub.url}/snapshot.png?token={hub.token}&scene={scene.id}&w=100&h=80"
            ) as r,
        ):
            return r.status, await r.read()

    status, body = run(go())
    assert status == 200 and body[:8] == b"\x89PNG\r\n\x1a\n"


def jpeg_frames_for(hub, scene, codec="h264"):

    async def go():
        session, ws = await connect(hub)
        page = Page(ws, hub)
        vid = await page.open(scene, codec=codec)
        await page.pump(1.2)
        await ws.close()
        await session.close()
        return page.of(vid)

    return run(go())


def test_without_pyav_a_viewer_that_asks_for_h264_gets_jpeg(hub, scene, monkeypatch):
    monkeypatch.setitem(sys.modules, "av", None)  # import av fails
    frames = jpeg_frames_for(hub, scene)
    assert frames and all(f["payload"][:2] == b"\xff\xd8" for f in frames)
    assert {f["kind"] for f in frames} <= {JPEG, STILL}
    assert any("PyAV is not installed" in m for m in hub._noted)  # and it said so, once


def test_an_ffmpeg_without_the_encoder_falls_back_to_jpeg_for_that_viewer(
    hub, scene, monkeypatch
):
    pytest.importorskip("av")
    from scene_streamer import codecs

    def broken(*args, **kwargs):
        raise RuntimeError("Unknown encoder 'libx264'")

    monkeypatch.setattr(codecs, "H264Encoder", broken)
    frames = jpeg_frames_for(hub, scene)
    assert frames and {f["kind"] for f in frames} <= {JPEG, STILL}
    assert any("encoder is unavailable" in m for m in hub._noted)


def test_without_simplejpeg_pillow_makes_the_jpegs(hub, scene, monkeypatch):
    monkeypatch.setitem(sys.modules, "simplejpeg", None)
    monkeypatch.setattr(hub, "_jpeg", None)  # the encoder is made on first use
    frames = jpeg_frames_for(hub, scene, codec="jpeg")
    assert frames and all(f["payload"][:2] == b"\xff\xd8" for f in frames)
    from io import BytesIO

    from PIL import Image

    assert Image.open(BytesIO(frames[-1]["payload"])).size == (160, 120)


def test_messages_are_handled_in_order_on_a_coarse_clock(hub, scene, monkeypatch):
    """Windows' clock ticks every ~15 ms: timers made in the same tick have equal due times, and asyncio's heap does
    not keep those in order. A page's messages (and a stream's frames) must not depend on that."""
    import time

    monkeypatch.setattr(
        hub.loop, "time", lambda: int(time.monotonic() * 20) / 20, raising=False
    )

    async def go():
        session, ws = await connect(hub)
        page = Page(ws, hub)
        vid = await page.open(scene)
        for i in range(40):  # one burst, far inside a 50 ms tick
            await page.send(t="pose", v=vid, pose=dict(azimuth=float(i), elevation=0.0))
        await page.send(t="getpose", v=vid)
        await page.pump(0.8)
        await ws.close()
        await session.close()
        return page

    page = run(go())
    assert [m for m in page.json if m["t"] == "pose"][-1]["pose"]["azimuth"] == 39.0
    seqs = [f["seq"] for f in page.frames]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)  # frames in order too


def test_a_message_that_fails_does_not_stall_the_connection(hub, scene, monkeypatch):
    errors = []
    hub.loop.set_exception_handler(lambda loop, context: errors.append(context))
    from scene_streamer.hub import Session

    real = Session.handle

    def handle(self, msg):
        if msg["t"] == "wheel":
            raise ValueError("boom")
        return real(self, msg)

    monkeypatch.setattr(Session, "handle", handle)

    async def go():
        session, ws = await connect(hub)
        page = Page(ws, hub)
        vid = await page.open(scene)
        await page.send(t="wheel", v=vid, dy=1)
        await page.send(t="getpose", v=vid)  # still answered after the failure
        await page.pump(0.6)
        await ws.close()
        await session.close()
        return page

    page = run(go())
    hub.loop.set_exception_handler(None)
    assert [m for m in page.json if m["t"] == "pose"]
    assert any(isinstance(e.get("exception"), ValueError) for e in errors)
