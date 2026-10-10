# -*- coding: utf-8 -*-
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)

from __future__ import absolute_import, division, unicode_literals
from time import time
from xbmc import getCondVisibility, Player, Monitor
from api import Api
from state import State
from utils import clear_setting_cache


# Kodi sets videoplayer.content() a moment after playback starts
VIDEO_CHECK_DELAY = 5


class UpNextPlayer(Player):
    """Service class for playback monitoring"""
    last_file = None
    track = False
    # When to check whether the started file is an episode (see check_video_due)
    video_check_at = None

    def __init__(self):
        self.api = Api()
        self.state = State()
        self.monitor = Monitor()
        Player.__init__(self)

    def set_last_file(self, filename):
        self.state.last_file = filename

    def get_last_file(self):
        return self.state.last_file

    def is_tracking(self):
        return self.state.track

    def disable_tracking(self):
        self.state.track = False

    def enable_tracking(self):
        self.state.track = True

    def reset_queue(self):
        if self.state.queued:
            self.api.reset_queue()
            self.state.queued = False

    def _check_video(self):
        if not getCondVisibility('videoplayer.content(episodes)'):
            return
        self.state.track = True

    def check_video_due(self, now=None):
        """Run the episode check scheduled at playback start once it is due.

        Called from the service loop: waiting inside the player callback would
        block every other callback and a popup still on screen for seconds.
        """
        if self.video_check_at is None or (now or time()) < self.video_check_at:
            return
        self.video_check_at = None
        self._check_video()

    def _playback_started(self):
        """Handle the start of a new video or audio stream"""
        # A pending Up Next handoff is consumed once the next file plays, so
        # the end of this file must reset the state again (e.g. when it is a
        # series finale for which no Up Next popup will reset it).
        self.state.playing_next = False
        # A file started from a paused popup plays without onPlayBackResumed
        self.state.pause = False
        # Settings read every service tick are cached per playback
        clear_setting_cache()
        self.video_check_at = time() + VIDEO_CHECK_DELAY

    if callable(getattr(Player, 'onAVStarted', None)):
        def onAVStarted(self):  # pylint: disable=invalid-name
            """Will be called when Kodi has a video or audiostream"""
            self._playback_started()

        def onPlayBackStarted(self):  # pylint: disable=invalid-name
            """Will be called when kodi starts playing a file"""
            self.reset_queue()
    else:
        def onPlayBackStarted(self):  # pylint: disable=invalid-name
            """Will be called when kodi starts playing a file"""
            self.reset_queue()
            self._playback_started()

    def onPlayBackPaused(self):  # pylint: disable=invalid-name
        self.state.pause = True

    def onPlayBackResumed(self):  # pylint: disable=invalid-name
        self.state.pause = False

    def onPlayBackStopped(self):  # pylint: disable=invalid-name
        """Will be called when user stops playing a file"""
        self.reset_queue()
        self.api.reset_addon_data()
        self.state = State()  # Reset state

    def onPlayBackEnded(self):  # pylint: disable=invalid-name
        """Will be called when Kodi has ended playing a file"""
        if self.state.popup_active:
            # The stream ended before the popup's countdown did: let the popup
            # finish the handoff as at a regular end (PlaybackManager resets
            # the state afterwards when nothing is played next).
            self.state.ended_during_popup = True
            return
        self.reset_queue()
        # Only reset state if not playing the next episode
        if not self.state.playing_next:
            self.api.reset_addon_data()
            self.state = State()  # Reset state

    def onPlayBackError(self):  # pylint: disable=invalid-name
        """Will be called when when playback stops due to an error"""
        self.reset_queue()
        self.api.reset_addon_data()
        self.state = State()  # Reset state
