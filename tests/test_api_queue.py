# -*- coding: utf-8 -*-
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)
# pylint: disable=missing-docstring,protected-access

from __future__ import absolute_import, division, unicode_literals

import api as api_module
from api import Api


def make_api(monkeypatch, calls, add_result=None, playlist_size=3):
    Api._shared_state.clear()
    Api.clear_caches()
    Api.queued_position = None

    class FakePlaylist(object):
        def __init__(self, _playlist_id):
            pass

        def size(self):
            return playlist_size

    monkeypatch.setattr(api_module, 'PlayList', FakePlaylist)

    def fake_jsonrpc(method=None, id=None, params=None, **_kwargs):  # pylint: disable=redefined-builtin
        calls.append((method, params))
        if method == 'Player.GetActivePlayers':
            return {'result': [{'playerid': 1, 'type': 'video'}]}
        if method == 'Player.GetProperties':
            return {'result': {'playlistid': 1}}
        if method == 'Playlist.Add':
            return add_result or {'result': 'OK'}
        return {'result': {}}

    monkeypatch.setattr(api_module, 'jsonrpc', fake_jsonrpc)
    return Api()


def test_episode_without_valid_id_is_not_added(monkeypatch):
    calls = []
    api = make_api(monkeypatch, calls)

    assert api.queue_next_item({}) is False
    assert Api.queued_position is None
    assert not any(method == 'Playlist.Add' for method, _params in calls)


def test_failed_add_does_not_claim_or_remove_a_playlist_item(monkeypatch):
    calls = []
    api = make_api(monkeypatch, calls, add_result={
        'error': {'code': -1, 'message': 'Playlist.Add failed'},
    })

    assert api.queue_next_item({'episodeid': 12}) is False
    assert Api.queued_position is None
    assert api.dequeue_next_item() is False
    assert not any(method == 'Playlist.Remove' for method, _params in calls)


def test_dequeue_without_owned_item_does_not_remove_a_playlist_entry(monkeypatch):
    calls = []
    api = make_api(monkeypatch, calls)

    assert api.dequeue_next_item() is False
    assert not any(method == 'Playlist.Remove' for method, _params in calls)
