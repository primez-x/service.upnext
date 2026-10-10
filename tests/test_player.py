# -*- coding: utf-8 -*-
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)

# pylint: disable=missing-docstring

from __future__ import absolute_import, division, unicode_literals

from api import Api
from player import UpNextPlayer
from state import State


class NoWaitMonitor:
    @staticmethod
    def waitForAbort(timeout=None):  # pylint: disable=invalid-name,unused-argument
        return False


def player_without_waiting():
    player = UpNextPlayer()
    player.monitor = NoWaitMonitor()
    return player


def start_next_file(player):
    """Send the callback Kodi sends when the next file has started playing"""
    # Kodi v18+ uses onAVStarted, older versions (and the test stubs) onPlayBackStarted
    getattr(player, 'onAVStarted', player.onPlayBackStarted)()
    # The service loop runs the episode check once it is due
    player.check_video_due(now=float('inf'))


def test_episode_check_runs_from_the_service_loop_not_the_callback():
    player = player_without_waiting()
    player.state = State()
    player.state.track = False

    getattr(player, 'onAVStarted', player.onPlayBackStarted)()
    assert player.state.track is False  # callback returned at once
    player.check_video_due(now=0)
    assert player.state.track is False  # not due yet
    player.check_video_due(now=float('inf'))
    assert player.state.track is True
    assert player.video_check_at is None


def test_new_file_clears_a_stale_pause():
    player = player_without_waiting()
    player.state = State()
    player.state.pause = True

    start_next_file(player)

    assert player.state.pause is False


def test_end_of_file_during_popup_is_left_to_the_popup():
    player = player_without_waiting()
    api = Api()
    player.state = State()
    player.state.track = True
    player.state.played_in_a_row = 2
    player.state.popup_active = True
    api.data = {'play_url': 'plugin://next'}

    player.onPlayBackEnded()

    assert player.state.ended_during_popup is True
    assert player.state.track is True
    assert player.state.played_in_a_row == 2
    assert api.has_addon_data()


def test_playing_next_is_cleared_when_next_file_starts():
    player = player_without_waiting()
    player.state = State()
    player.state.playing_next = True

    start_next_file(player)

    # NOTE: Don't create State() here, that resets the shared state
    assert player.state.playing_next is False
    assert player.state.track is True


def test_handoff_keeps_state_until_next_file_starts():
    player = player_without_waiting()
    player.state = State()
    player.state.played_in_a_row = 2
    player.state.playing_next = True

    player.onPlayBackEnded()

    assert player.state.played_in_a_row == 2
    assert player.state.playing_next is True


def test_series_finale_end_resets_state_after_handoff():
    player = player_without_waiting()
    api = Api()
    player.state = State()
    # Episode handed off to the series finale
    player.state.played_in_a_row = 3
    player.state.playing_next = True
    start_next_file(player)
    assert player.state.played_in_a_row == 3

    # No next episode for the finale, so Up Next never resets the state;
    # the end of the finale must do it
    api.data = {'next_episode': None}
    player.onPlayBackEnded()

    assert player.state.played_in_a_row == 1
    assert player.state.playing_next is False
    assert not api.has_addon_data()
