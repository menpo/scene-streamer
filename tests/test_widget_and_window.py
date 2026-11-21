import pytest

import scene_streamer
from fakes import FakeFigure, FakeWorker
from scene_streamer import hub as hub_module
from scene_streamer import window


@pytest.fixture
def fresh_hub(monkeypatch):
    monkeypatch.setattr(hub_module, "_hub", None)
    monkeypatch.setattr(hub_module, "_config", {})
    scene_streamer.configure(worker=lambda: FakeWorker())
    yield
    if hub_module._hub is not None:
        hub_module._hub.stop()


def test_the_browser_can_be_chosen_with_an_environment_variable(monkeypatch):
    monkeypatch.setenv("SCENE_STREAMER_BROWSER", "/opt/my-chromium")
    assert window.find_browser() == "/opt/my-chromium"


def test_the_window_opens_the_scenes_page(fresh_hub, monkeypatch):
    opened = []
    monkeypatch.setattr(
        window, "open_window", lambda url, size: opened.append((url, size))
    )
    figure = FakeFigure(size=(500, 400))
    assert window.show(figure, block=False) is None
    ((url, size),) = opened
    hub = scene_streamer.get_hub()
    assert url == hub.view_url(figure.scene) and size == (500, 400)
    assert figure.scene.placed  # the camera is framed before the page asks


def test_the_widget_points_the_page_at_the_hub(fresh_hub):
    pytest.importorskip("anywidget")
    from scene_streamer.widget import figure_widget

    figure = FakeFigure(size=(320, 200))
    widget = figure_widget(figure)
    hub = scene_streamer.get_hub()
    assert (widget.url, widget.token, widget.scene) == (
        hub.url,
        hub.token,
        figure.scene.id,
    )
    assert (widget.width, widget.height) == (320, 200)
    assert (
        figure_widget(figure) is widget
    )  # one widget per figure keeps its viewer and camera
    assert figure.scene.id in hub.scenes  # and the scene is registered with the hub


def test_the_widget_keeps_the_last_still_as_an_image(fresh_hub):
    pytest.importorskip("anywidget")
    import base64

    from scene_streamer.widget import _BLANK, figure_widget

    class Handle:
        updated = []

        def update(self, image):
            self.updated.append(image.data)

    widget = figure_widget(FakeFigure())
    widget._handle = Handle()
    png = _BLANK
    widget.still = "data:image/png;base64," + base64.b64encode(png).decode()
    assert Handle.updated == [png]
