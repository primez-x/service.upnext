# -*- coding: utf-8 -*-
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)

from __future__ import absolute_import, division, unicode_literals
from xbmc import sleep, Monitor
from api import Api
from demo import DemoOverlay
from player import UpNextPlayer
from playitem import PlayItem
from state import State
from stillwatching import StillWatching
from upnext import UpNext
from utils import addon_path, calculate_progress_steps, clear_property, event, get_setting_bool, get_setting_int, log as ulog, set_property

# Close the popup when playback moved back this many seconds before the notification time
SEEK_BACK_GRACE = 5


class PlaybackManager(object):
    _shared_state = {}
    # Popup dialogs currently shown, see close_popup()
    open_pages = ()
    # Set by launch_popup() when Up Next has to be shown again for the current file
    rearm = False

    def __init__(self, player=None):
        self.__dict__ = self._shared_state
        self.api = Api()
        self.state = State()
        # Share the service's player: every xbmc.Player instance receives all player callbacks
        self.player = player or UpNextPlayer()
        self.play_item = PlayItem(player=self.player)
        self.demo = DemoOverlay(12005)

    def log(self, msg, level=2, *args):  # pylint: disable=keyword-arg-before-vararg
        ulog(msg, *args, name=self.__class__.__name__, level=level)

    def handle_demo(self):
        if get_setting_bool('enableDemoMode'):
            self.log('Up Next DEMO mode enabled, skipping automatically to the end', 0)
            self.demo.show()
            try:
                total_time = self.player.getTotalTime()
                self.player.seekTime(total_time - 15)
            except RuntimeError as exc:
                self.log('Failed to seekTime(): %s', 0, exc)
        else:
            self.demo.hide()

    def launch_up_next(self):
        """Show Up Next for the playing file, return True when it has to be shown again later"""
        self.rearm = False
        # Settings may have changed since the State was created
        self.state.play_mode = get_setting_int('autoPlayMode')
        self.state.include_watched = get_setting_bool('includeWatched')
        enable_playlist = get_setting_bool('enablePlaylist')
        episode, source = self.play_item.get_next()
        self.log('Playlist setting: %s', 2, enable_playlist)
        if source == 'playlist' and not enable_playlist:
            self.log('Playlist integration disabled', 2)
            return False
        if not episode:
            # No episode get out of here
            self.log('Error: no episode could be found to play next...exiting', 1)
            return False
        self.log('episode details %s', 2, episode)
        self.state.ended_during_popup = False
        try:
            play_next, keep_playing = self.launch_popup(episode, source)
        finally:
            self.state.popup_active = False
        if Monitor().abortRequested():
            # Service restart (add-on update) or Kodi exit: never start or
            # leave queued the next episode on the way out
            if self.state.queued:
                self.state.queued = self.api.dequeue_next_item()
            self.state.playing_next = False
            return False
        # When playing next, launch_popup() set playing_next before starting
        # the next file. Don't set it again here: the handoff may already have
        # been consumed (next file started) or cancelled (playback stopped).
        if not play_next:
            self.state.playing_next = False

        # Dequeue and stop playback if not playing next file
        if not play_next and self.state.queued:
            self.state.queued = self.api.dequeue_next_item()

        if self.rearm:
            # Keep tracking and the add-on data, the monitor shows Up Next again
            # once playback reaches the notification time
            self.log('Playback moved back before the notification time, Up Next will be shown again', 2)
            self.state.last_file = None
            return True

        if not keep_playing:
            self.log('Stopping playback', 2)
            self.player.stop()

        self.api.reset_addon_data()
        if self.state.ended_during_popup and not play_next:
            # onPlayBackEnded left the state to us: reset it as it would have
            self.state.__init__()
        return False

    def launch_popup(self, episode, source=None):  # pylint: disable=too-many-locals
        episode_id = episode.get('episodeid')
        no_play_count = episode.get('playcount') is None or episode.get('playcount') == 0
        include_play_count = True if self.state.include_watched else no_play_count
        if not include_play_count or self.state.current_episode_id == episode_id:
            # play_next = False
            # keep_playing = True
            # return play_next, keep_playing
            # Don't play next file, but keep playing current file
            return False, True

        # Add next file to playlist if existing playlist is not being used
        if source != 'playlist':
            queued = self.state.queued = self.api.queue_next_item(episode)
        else:
            queued = False

        # We have a next up episode choose mode
        if get_setting_int('simpleMode') == 0:
            next_up_page = UpNext('script-upnext-upnext-simple.xml', addon_path(), 'default', '1080i')
            still_watching_page = StillWatching('script-upnext-stillwatching-simple.xml', addon_path(), 'default', '1080i')
        else:
            next_up_page = UpNext('script-upnext-upnext.xml', addon_path(), 'default', '1080i')
            still_watching_page = StillWatching('script-upnext-stillwatching.xml', addon_path(), 'default', '1080i')

        self.state.popup_active = True
        (showing_next_up_page,
         showing_still_watching_page,
         countdown_expired,
         seeked_back) = self.show_popup_and_wait(
             episode,
             next_up_page,
             still_watching_page)
        self.state.popup_active = False
        if Monitor().abortRequested():
            self.close_popup()
            return False, True
        if seeked_back:
            # Don't play next file, keep playing current file and show Up Next again later
            self.rearm = True
            return False, True
        should_play_default, should_play_non_default = self.extract_play_info(next_up_page,
                                                                              showing_next_up_page,
                                                                              showing_still_watching_page,
                                                                              still_watching_page)
        if not self.state.track:
            self.log('exit launch_popup early due to disabled tracking', 2)
            # play_next = False
            # keep_playing = showing_next_up_page
            # return play_next, keep_playing
            # Don't play next file
            # Stop if Still Watching? popup was shown to prevent unwanted playback when using FF or skip
            return False, showing_next_up_page

        play_item_option_1 = (should_play_default and self.state.play_mode == 0)
        play_item_option_2 = (should_play_non_default and self.state.play_mode == 1)
        if not play_item_option_1 and not play_item_option_2:
            if countdown_expired:
                # Ask-mode users did not choose Watch Now. Close the bounded
                # prompt but let the current episode continue through credits.
                return False, True
            # play_next = False
            # keep_playing = next_up_page.is_cancel() if showing_next_up_page else still_watching_page.is_cancel()
            # keep_playing = keep_playing and not get_setting_bool('stopAfterClose')
            # return play_next, keep_playing
            # Don't play next file, and stop current file if no playback option selected
            return False, (
                (next_up_page.is_cancel() if showing_next_up_page else still_watching_page.is_cancel())
                and not get_setting_bool('stopAfterClose')
            )

        self.log('playing media episode', 2)
        # Signal to trakt previous episode watched
        event(message='NEXTUPWATCHEDSIGNAL', data={'episodeid': self.state.current_episode_id}, encoding='base64')
        # Set before starting the next file, it is cleared when the next file
        # starts (UpNextPlayer) or the state is reset (playback stopped/failed)
        self.state.playing_next = True
        self._play_episode(
            episode,
            source,
            queued,
            explicit_advance=should_play_non_default or countdown_expired,
            watched_episode=not no_play_count,
        )

        # play_next = True
        # keep_playing = True
        # return play_next, keep_playing
        # Play next file, and keep playing current file
        return True, True

    def _play_episode(self, episode, source, queued, explicit_advance, watched_episode):
        if source == 'playlist' or queued:
            if explicit_advance:
                # Watch Now advances immediately.
                self.player.playnext()
            elif watched_episode:
                # Kodi drops queued watched items at end of stream. Wait until
                # the current stream has fully closed before starting the next
                # episode so its EOF teardown cannot close the new playback.
                self._play_watched_episode_after_end(episode, queued)
        elif self.api.has_addon_data():
            # Play add-on media
            self.api.play_addon_item()
        else:
            # Play local media
            self.api.play_kodi_item(episode)

    def _play_watched_episode_after_end(self, episode, queued):
        self.log('Waiting for watched episode end-of-stream handoff', 0)
        self.state.playing_next = True
        if queued:
            self.state.queued = self.api.dequeue_next_item()

        try:
            current_file = self.player.getPlayingFile()
        except RuntimeError:
            current_file = None

        for _ in range(60):
            if not self.player.isPlaying():
                # Allow a native playlist transition to appear before taking
                # over; Kodi can briefly report no active player between files.
                if self._wait_for_abort(0.25):
                    return
                if not self.player.isPlaying():
                    break
            if current_file:
                try:
                    if self.player.getPlayingFile() != current_file:
                        self.log('Kodi completed watched episode handoff natively', 0)
                        return
                except RuntimeError:
                    break
            if self._wait_for_abort(0.05):
                return

        # onPlayBackStopped/onPlayBackError reset the shared State (clearing
        # playing_next) and the add-on data, whereas onPlayBackEnded keeps it
        # while playing_next is set. Don't start the next episode when the
        # user stopped playback or it failed while we were waiting.
        if not self.state.playing_next:
            self.log('Playback was stopped or failed; not starting watched next episode', 0)
            return

        self.log('Starting watched next episode after end of stream', 0)
        if self.api.has_addon_data():
            self.api.play_addon_item()
        else:
            self.api.play_kodi_item(episode)

    @staticmethod
    def _wait_for_abort(timeout):
        """Wait up to timeout seconds, return True when Kodi requests an abort"""
        return Monitor().waitForAbort(timeout)

    def close_popup(self):
        """Close the popup dialogs when shown and clear the dialog window property"""
        pages, self.open_pages = self.open_pages, ()
        for page in pages:
            page.close()
        clear_property('service.upnext.dialog')

    def show_popup_and_wait(self, episode, next_up_page, still_watching_page):
        """Show the popup and wait for the user or the end of playback

        Return a tuple: (showing_next_up_page, showing_still_watching_page,
        countdown_expired, seeked_back). When seeked_back is True playback
        moved back before the notification time and the popup was closed.
        """
        try:
            return self._show_popup_and_wait(episode, next_up_page, still_watching_page)
        except BaseException:
            # Never leave the popup covering playback after an unexpected error
            self.close_popup()
            raise

    def _show_popup_and_wait(self, episode, next_up_page, still_watching_page):  # pylint: disable=too-many-locals,too-many-branches
        try:
            play_time = self.player.getTime()
            total_time = self.player.getTotalTime()
        except RuntimeError:
            self.log('exit early because player is no longer running', 2)
            return False, False, False, False
        notification_time = self.api.notification_time(total_time=total_time)
        next_up_page.set_item(episode)
        still_watching_page.set_item(episode)
        played_in_a_row_number = get_setting_int('playedInARow')
        self.log('played in a row settings %s', 2, played_in_a_row_number)
        self.log('played in a row %s', 2, self.state.played_in_a_row)
        showing_next_up_page = False
        showing_still_watching_page = False
        if not played_in_a_row_number or int(self.state.played_in_a_row) < int(played_in_a_row_number):
            self.log('showing next up page as played in a row is %s', 2, self.state.played_in_a_row)
            self.open_pages = (next_up_page,)
            next_up_page.show()
            set_property('service.upnext.dialog', 'true')
            showing_next_up_page = True
        else:
            self.log('showing still watching page as played in a row %s', 2, self.state.played_in_a_row)
            self.open_pages = (still_watching_page,)
            still_watching_page.show()
            set_property('service.upnext.dialog', 'true')
            showing_still_watching_page = True

        notification_duration = (
            self.api.notification_duration()
            if showing_next_up_page else None
        )
        if notification_duration is not None:
            self.log(
                'Using provider countdown of %ss from playback position %.3fs',
                0, notification_duration, play_time,
            )
        progress_period = (
            min(notification_duration, total_time - play_time)
            if notification_duration is not None
            else total_time - play_time
        )
        progress_step_size = calculate_progress_steps(progress_period)
        next_up_page.set_progress_step_size(progress_step_size)
        still_watching_page.set_progress_step_size(progress_step_size)
        countdown_start_time = play_time
        countdown_expired = False
        seeked_back = False
        monitor = Monitor()
        while (self.player.isPlaying() and (total_time - play_time > 1)
               and not monitor.abortRequested()
               and not next_up_page.is_cancel() and not next_up_page.is_watch_now()
               and not still_watching_page.is_still_watching() and not still_watching_page.is_cancel()):
            try:
                play_time = self.player.getTime()
                total_time = self.player.getTotalTime()
            except RuntimeError:
                self.close_popup()
                showing_next_up_page = False
                showing_still_watching_page = False
                break

            if total_time - play_time > notification_time + SEEK_BACK_GRACE:
                # Playback moved back out of the notification window (e.g. the
                # user rewinds): don't cover the episode, show Up Next again later
                self.log('Playback moved back to %.3fs, closing popup', 0, play_time)
                self.close_popup()
                showing_next_up_page = False
                showing_still_watching_page = False
                seeked_back = True
                break

            if notification_duration is not None:
                elapsed = max(0, play_time - countdown_start_time)
                remaining = max(0, notification_duration - elapsed)
                if remaining <= 0:
                    self.log('Provider countdown expired; advancing now', 0)
                    countdown_expired = True
                    break
            else:
                remaining = total_time - play_time
            runtime = episode.get('runtime')
            if not self.state.pause:
                if showing_next_up_page:
                    next_up_page.update_progress_control(remaining=remaining, runtime=runtime)
                elif showing_still_watching_page:
                    still_watching_page.update_progress_control(remaining=remaining, runtime=runtime)
            sleep(100)
        return (showing_next_up_page,
                showing_still_watching_page,
                countdown_expired,
                seeked_back)

    def extract_play_info(self, next_up_page, showing_next_up_page, showing_still_watching_page, still_watching_page):
        self.open_pages = ()
        if showing_next_up_page:
            next_up_page.close()
            should_play_default = not next_up_page.is_cancel()
            should_play_non_default = next_up_page.is_watch_now()
        elif showing_still_watching_page:
            still_watching_page.close()
            should_play_default = still_watching_page.is_still_watching()
            should_play_non_default = still_watching_page.is_still_watching()
        else:
            # FIXME: This is a workaround until we handle this better (see comments in #142)
            return False, False

        if next_up_page.is_watch_now() or still_watching_page.is_still_watching():
            self.state.played_in_a_row = 1
        else:
            self.state.played_in_a_row += 1
        clear_property('service.upnext.dialog')
        return should_play_default, should_play_non_default
