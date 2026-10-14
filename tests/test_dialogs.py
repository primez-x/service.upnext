# -*- coding: utf-8 -*-
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)

from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
import script
import stillwatching
import upnext


LAYOUTS = (
    (upnext, upnext.UpNext, 'script-upnext-upnext.xml', 3012),
    (upnext, upnext.UpNext, 'script-upnext-upnext-simple.xml', 20),
    (stillwatching, stillwatching.StillWatching, 'script-upnext-stillwatching.xml', 20),
    (stillwatching, stillwatching.StillWatching, 'script-upnext-stillwatching-simple.xml', 20),
)
SKINS = Path(__file__).resolve().parents[1] / 'resources/skins/default/1080i'


def dialog_with_controls(dialog_class, controls):
    page = dialog_class.__new__(dialog_class)
    page.item = None
    page.progress_control = None
    page.cancel = page.watchnow = page.stillwatching = False
    page.focused = None
    page.closed = False
    page.properties = {}
    page.setProperty = lambda key, value: page.properties.update({key: value})
    page.setFocus = lambda control: setattr(page, 'focused', control.control_id)
    page.close = lambda: setattr(page, 'closed', True)

    def get_control(control_id):
        if control_id not in controls:
            raise RuntimeError('control absent')
        return SimpleNamespace(control_id=control_id, setLabel=lambda label: None,
                               setPercent=lambda percent: None)

    page.getControl = get_control
    return page


@pytest.mark.parametrize('module,dialog_class,layout,autoplay_focus', LAYOUTS)
@pytest.mark.parametrize('play_mode', (0, 1))
def test_default_focus_matches_play_mode_in_every_shipped_layout(
        monkeypatch, module, dialog_class, layout, autoplay_focus, play_mode):
    controls = {int(control.attrib['id']) for control in
                ElementTree.parse(SKINS / layout).iter('control') if 'id' in control.attrib}
    monkeypatch.setattr(module, 'get_setting_int', lambda setting: play_mode, raising=False)
    if module is upnext:
        monkeypatch.setattr(module, 'get_setting_bool', lambda setting: False)
    page = dialog_with_controls(dialog_class, controls)
    page.onInit()
    assert page.focused == (3013 if play_mode == 1 else autoplay_focus)


@pytest.mark.parametrize('module,dialog_class', (
    (upnext, upnext.UpNext), (stillwatching, stillwatching.StillWatching),
    (script, script.TestPopup),
))
@pytest.mark.parametrize('play_mode', (0, 1))
def test_missing_skin_controls_do_not_crash_or_focus_watch_now_in_ask_mode(
        monkeypatch, module, dialog_class, play_mode):
    monkeypatch.setattr(module, 'get_setting_int', lambda setting: play_mode, raising=False)
    if hasattr(module, 'get_setting_bool'):
        monkeypatch.setattr(module, 'get_setting_bool', lambda setting: True)
    page = dialog_with_controls(dialog_class, {3012})
    page.onInit()
    if play_mode == 1:
        assert page.focused is None
        assert page.closed
    else:
        assert page.focused == 3012


@pytest.mark.parametrize('dialog_class', (upnext.UpNext, stillwatching.StillWatching))
def test_back_cancels_without_selecting_next(dialog_class):
    page = dialog_with_controls(dialog_class, {3012, 3013})
    page.onAction(92)
    assert page.closed and page.is_cancel()
    assert not page.watchnow and not page.stillwatching


@pytest.mark.parametrize('dialog_class', (upnext.UpNext, stillwatching.StillWatching))
def test_stop_closes_without_selecting_next(dialog_class):
    page = dialog_with_controls(dialog_class, {3012, 3013})
    page.onAction(13)
    assert page.closed
    assert not page.watchnow and not page.stillwatching


@pytest.mark.parametrize('dialog_class', (upnext.UpNext, stillwatching.StillWatching))
def test_confirm_selects_next_and_close_cancels(monkeypatch, dialog_class):
    monkeypatch.setattr(upnext, 'get_setting_bool', lambda setting: False)
    page = dialog_with_controls(dialog_class, {3012, 3013})
    page.onClick(3012)
    assert page.closed
    assert page.watchnow or page.stillwatching
    page = dialog_with_controls(dialog_class, {3012, 3013})
    page.onClick(3013)
    assert page.closed and page.is_cancel()
    assert not page.watchnow and not page.stillwatching


def test_close_with_stop_setting_stops_the_player(monkeypatch):
    stops = []
    monkeypatch.setattr(upnext, 'get_setting_bool', lambda setting: True)
    monkeypatch.setattr(upnext, 'Player', lambda: SimpleNamespace(stop=lambda: stops.append(True)))
    page = dialog_with_controls(upnext.UpNext, {3012, 3013})
    page.onClick(3013)
    assert stops == [True]
    assert page.is_cancel() and page.closed
