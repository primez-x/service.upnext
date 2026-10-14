# -*- coding: utf-8 -*-
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)
# pylint: disable=missing-docstring,protected-access

from __future__ import absolute_import, division, unicode_literals

import api as api_module
from api import Api
from stillwatching import StillWatching
from upnext import UpNext


def make_api(monkeypatch, calls):
    Api._shared_state.clear()
    Api.clear_caches()
    Api.queued_item = None

    def fake_jsonrpc(method=None, id=None, params=None, **_kwargs):  # pylint: disable=redefined-builtin
        calls.append(method)
        if method == 'Player.GetActivePlayers':
            return {'result': [{'playerid': 1, 'type': 'video'}]}
        if method == 'Player.GetProperties':
            return {'result': {'playlistid': 1}}
        return {'result': {}}

    monkeypatch.setattr(api_module, 'jsonrpc', fake_jsonrpc)
    return Api()


def test_playlistid_is_fetched_once_and_cached(monkeypatch):
    calls = []
    make_api(monkeypatch, calls)

    assert Api.get_playlistid() == 1
    assert Api.get_playlistid() == 1
    assert calls == ['Player.GetActivePlayers', 'Player.GetProperties']

    Api.clear_caches()
    assert Api.get_playlistid() == 1
    assert calls == ['Player.GetActivePlayers', 'Player.GetProperties'] * 2


def test_invalid_provider_notification_time_falls_back(monkeypatch):
    api = make_api(monkeypatch, [])
    api.data = {'notification_time': 'at the credits'}
    # Falls through to the configured default instead of raising
    assert api.notification_time(total_time=100) is not None
    api.data = {'notification_time': '45'}
    assert api.notification_time(total_time=100) == 45
    api.data = {'notification_offset': 'bogus'}
    assert api.notification_time(total_time=100) is not None


def run_set_info(page_class, item):
    page = page_class.__new__(page_class)
    page.item = item
    properties = {}
    page.setProperty = lambda key, value: properties.update({key: value})
    page.set_info()
    return properties


def test_set_info_tolerates_minimal_provider_item():
    for page_class in (UpNext, StillWatching):
        props = run_set_info(page_class, {'title': 'Pilot'})
        assert props['title'] == 'Pilot'
        assert props['seasonepisode'] == 'x.'
        props = run_set_info(page_class, {
            'title': 'Pilot', 'season': 1, 'episode': 2,
            'art': {'tvshow.poster': 'poster.jpg'}, 'rating': 'high'})
        assert props['seasonepisode'] == '1x2.'
        assert props['poster'] == 'poster.jpg'
        assert props['rating'] == ''
        props = run_set_info(page_class, None)
        assert props == {}


def test_progress_uses_real_remaining_time():
    for page_class in (UpNext, StillWatching):
        page = page_class.__new__(page_class)
        page.current_progress_percent = 100
        page.progress_step_size = 10
        page.progress_control = None
        page.prepare_progress_control = lambda: None
        page.setProperty = lambda key, value: None
        page.update_progress_control(remaining=25, runtime=None, period=100)
        assert page.current_progress_percent == 25.0
        page.update_progress_control(remaining=10, runtime=None, period=100)
        assert page.current_progress_percent == 10.0
