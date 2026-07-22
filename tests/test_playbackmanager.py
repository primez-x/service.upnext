# -*- coding: utf-8 -*-
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)

from __future__ import absolute_import, division, unicode_literals

import playbackmanager
from playbackmanager import PlaybackManager


class RecordingPlayer:
    def __init__(self):
        self.playnext_calls = 0
        self.playing = False

    def playnext(self):
        self.playnext_calls += 1

    def isPlaying(self):
        return self.playing

    def getPlayingFile(self):
        return 'current.mkv'


class RecordingApi:
    def __init__(self, has_addon_data=False):
        self._has_addon_data = has_addon_data
        self.addon_items_played = 0
        self.dequeue_calls = 0
        self.kodi_items_played = []

    def has_addon_data(self):
        return self._has_addon_data

    def play_addon_item(self):
        self.addon_items_played += 1

    def dequeue_next_item(self):
        self.dequeue_calls += 1
        return False

    def play_kodi_item(self, episode):
        self.kodi_items_played.append(episode)


def manager_with_recorders(has_addon_data=False):
    manager = PlaybackManager.__new__(PlaybackManager)
    manager.player = RecordingPlayer()
    manager.api = RecordingApi(has_addon_data=has_addon_data)
    manager.state = type('RecordingState', (object,), {
        'playing_next': False,
        'queued': True,
    })()
    return manager


def test_watched_queued_episode_starts_directly_after_end_of_stream(monkeypatch):
    monkeypatch.setattr(playbackmanager, 'sleep', lambda milliseconds: None)
    manager = manager_with_recorders(has_addon_data=True)

    manager._play_episode(
        {'episodeid': 2},
        source=None,
        queued=True,
        explicit_advance=False,
        watched_episode=True,
    )

    assert manager.player.playnext_calls == 0
    assert manager.api.addon_items_played == 1
    assert manager.api.dequeue_calls == 1
    assert manager.api.kodi_items_played == []
    assert manager.state.playing_next is True
    assert manager.state.queued is False


def test_unwatched_queued_episode_keeps_kodi_end_of_stream_autoplay():
    manager = manager_with_recorders()

    manager._play_episode(
        {'episodeid': 2},
        source=None,
        queued=True,
        explicit_advance=False,
        watched_episode=False,
    )

    assert manager.player.playnext_calls == 0


def test_existing_playlist_explicitly_advances_when_requested():
    manager = manager_with_recorders()

    manager._play_episode(
        {'episodeid': 2},
        source='playlist',
        queued=False,
        explicit_advance=True,
        watched_episode=False,
    )

    assert manager.player.playnext_calls == 1


def test_addon_episode_uses_addon_playback_when_not_queued():
    manager = manager_with_recorders(has_addon_data=True)

    manager._play_episode(
        {'episodeid': 2},
        source=None,
        queued=False,
        explicit_advance=False,
        watched_episode=False,
    )

    assert manager.player.playnext_calls == 0
    assert manager.api.addon_items_played == 1


def test_local_episode_uses_kodi_playback_when_not_queued():
    manager = manager_with_recorders()
    episode = {'episodeid': 2}

    manager._play_episode(
        episode,
        source=None,
        queued=False,
        explicit_advance=False,
        watched_episode=False,
    )

    assert manager.player.playnext_calls == 0
    assert manager.api.kodi_items_played == [episode]
