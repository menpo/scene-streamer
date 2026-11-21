"""Wiring: the hub gets its renderer from the package that owns it, and says so when there is none."""

import asyncio

import pytest

import aiohttp
import scene_streamer
from fakes import FakeScene, FakeWorker
from scene_streamer import hub as hub_module


@pytest.fixture
def fresh_hub(monkeypatch):
    """A new global hub per test (the module keeps one)."""
    monkeypatch.setattr(hub_module, "_hub", None)
    monkeypatch.setattr(hub_module, "_config", {})
    yield
    if hub_module._hub is not None:
        hub_module._hub.stop()


def test_a_hub_without_a_renderer_says_how_to_give_it_one(fresh_hub):
    hub = scene_streamer.get_hub()
    with pytest.raises(RuntimeError, match=r"configure\(worker="):
        hub.worker


def test_configure_worker_is_used_by_the_hub_made_afterwards(fresh_hub):
    worker = FakeWorker()
    scene_streamer.configure(worker=lambda: worker)
    assert scene_streamer.get_hub().worker is worker


def test_configure_worker_replaces_it_on_a_hub_that_already_runs(fresh_hub):
    first, second = FakeWorker(), FakeWorker()
    scene_streamer.configure(worker=lambda: first)
    hub = scene_streamer.get_hub()
    assert hub.worker is first
    scene_streamer.configure(worker=lambda: second)
    assert hub.worker is second


def test_the_worker_is_only_made_when_the_first_frame_is_needed(fresh_hub):
    made = []
    scene_streamer.configure(worker=lambda: made.append(1) or FakeWorker())
    hub = scene_streamer.get_hub()
    hub.start()
    assert made == []  # starting the server does not touch the GPU
    hub.worker, hub.worker
    assert made == [1]  # and it is made once


def test_listening_options_cannot_change_once_the_server_runs(fresh_hub):
    scene_streamer.configure(worker=lambda: FakeWorker())
    scene_streamer.get_hub().start()
    with pytest.raises(RuntimeError, match="already running"):
        scene_streamer.configure(port=1234)


def test_stats_come_from_the_renderer(fresh_hub):
    scene_streamer.configure(worker=lambda: FakeWorker())
    hub = scene_streamer.get_hub()
    scene = FakeScene()
    hub.register(scene)

    async def go():
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{hub.url}/stats?token={hub.token}") as r:
                return await r.json()

    stats = asyncio.run(go())
    assert stats["gpu"] == {} and stats["fbos"] == 0 and stats["scenes"] == 1


def test_the_package_has_a_version():
    assert scene_streamer.__version__
