# -*- coding: utf-8 -*-
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)

from __future__ import absolute_import, division, unicode_literals

import playbackmanager
from api import Api
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
    def __init__(self, has_addon_data=False, notification_duration=None):
        self._has_addon_data = has_addon_data
        self._notification_duration = notification_duration
        self.addon_items_played = 0
        self.dequeue_calls = 0
        self.kodi_items_played = []
        self.queue_calls = 0

    def has_addon_data(self):
        return self._has_addon_data

    def play_addon_item(self):
        self.addon_items_played += 1

    def dequeue_next_item(self):
        self.dequeue_calls += 1
        return False

    def queue_next_item(self, episode):
        self.queue_calls += 1
        return True

    def play_kodi_item(self, episode):
        self.kodi_items_played.append(episode)

    def notification_duration(self):
        return self._notification_duration


def manager_with_recorders(has_addon_data=False, notification_duration=None):
    manager = PlaybackManager.__new__(PlaybackManager)
    manager.player = RecordingPlayer()
    manager.api = RecordingApi(
        has_addon_data=has_addon_data,
        notification_duration=notification_duration,
    )
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


def test_provider_countdown_expiry_advances_queued_watched_episode():
    manager = manager_with_recorders(has_addon_data=True)

    manager._play_episode(
        {'episodeid': 2},
        source=None,
        queued=True,
        explicit_advance=True,
        watched_episode=True,
    )

    assert manager.player.playnext_calls == 1
    assert manager.api.addon_items_played == 0


def test_launch_popup_treats_provider_countdown_expiry_as_explicit_advance(
        monkeypatch):
    monkeypatch.setattr(playbackmanager, 'get_setting_int', lambda setting: 1)
    monkeypatch.setattr(playbackmanager, 'UpNext',
                        lambda *args, **kwargs: RecordingPage())
    monkeypatch.setattr(playbackmanager, 'StillWatching',
                        lambda *args, **kwargs: RecordingPage())
    monkeypatch.setattr(playbackmanager, 'event',
                        lambda *args, **kwargs: None)
    manager = manager_with_recorders(has_addon_data=True)
    manager.state.include_watched = True
    manager.state.current_episode_id = 1
    manager.state.track = True
    manager.state.play_mode = 0
    manager.show_popup_and_wait = (
        lambda episode, next_page, still_page: (True, False, True)
    )
    manager.extract_play_info = (
        lambda next_page, showing_next, showing_still, still_page:
        (True, False)
    )
    captured = {}

    def record_play(episode, source, queued, explicit_advance,
                    watched_episode):
        captured.update(
            explicit_advance=explicit_advance,
            watched_episode=watched_episode,
            queued=queued,
        )

    manager._play_episode = record_play

    assert manager.launch_popup({
        'episodeid': 2,
        'playcount': 1,
    }) == (True, True)
    assert captured == {
        'explicit_advance': True,
        'watched_episode': True,
        'queued': True,
    }


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


class TimedPlayer:
    def __init__(self, times, total_time=200):
        self.times = list(times)
        self.last_time = self.times[-1]
        self.total_time = total_time

    def getTime(self):
        if self.times:
            self.last_time = self.times.pop(0)
        return self.last_time

    def getTotalTime(self):
        return self.total_time

    def isPlaying(self):
        return True


class RecordingPage:
    def __init__(self):
        self.shown = False
        self.closed = False
        self.progress_step_size = None
        self.remaining_updates = []

    def set_item(self, episode):
        self.episode = episode

    def set_progress_step_size(self, progress_step_size):
        self.progress_step_size = progress_step_size

    def show(self):
        self.shown = True

    def close(self):
        self.closed = True

    def is_cancel(self):
        return False

    def is_watch_now(self):
        return False

    def is_still_watching(self):
        return False

    def update_progress_control(self, remaining=None, runtime=None):
        self.remaining_updates.append(remaining)


def test_provider_countdown_starts_at_popup_and_expires_after_ten_playback_seconds(
        monkeypatch):
    monkeypatch.setattr(playbackmanager, 'get_setting_int', lambda setting: 0)
    monkeypatch.setattr(playbackmanager, 'set_property',
                        lambda key, value: None)
    monkeypatch.setattr(playbackmanager, 'sleep', lambda milliseconds: None)
    manager = manager_with_recorders(notification_duration=10)
    manager.player = TimedPlayer([100, 100, 102, 109, 110])
    manager.state.played_in_a_row = 1
    manager.state.pause = False
    next_up_page = RecordingPage()
    still_watching_page = RecordingPage()

    result = manager.show_popup_and_wait(
        {'runtime': 1200},
        next_up_page,
        still_watching_page,
    )

    assert result == (True, False, True)
    assert next_up_page.shown is True
    assert still_watching_page.shown is False
    assert next_up_page.remaining_updates == [10, 8, 1]
    assert next_up_page.progress_step_size == 1


def test_provider_notification_duration_is_validated_and_capped():
    api = Api()
    cases = (
        (None, None),
        ('invalid', None),
        (0, None),
        (10, 10),
        (120, 60),
    )

    for configured, expected in cases:
        api.data = {'notification_duration': configured}
        assert api.notification_duration() == expected
