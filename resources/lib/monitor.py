# -*- coding: utf-8 -*-
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)

from __future__ import absolute_import, division, unicode_literals
from traceback import format_exc
from xbmc import Monitor
from api import Api
from playbackmanager import PlaybackManager
from player import UpNextPlayer
from statichelper import to_unicode
from utils import clear_setting_cache, decode_json, get_property, get_setting_bool, kodi_version_major, log as ulog


class UpNextMonitor(Monitor):
    """Service monitor for Kodi"""

    def __init__(self):
        """Constructor for Monitor"""
        # Use a single player instance: every xbmc.Player instance receives
        # (and handles) all player callbacks on the service thread
        self.player = UpNextPlayer()
        self.api = Api()
        self.playback_manager = PlaybackManager(player=self.player)
        Monitor.__init__(self)

    def log(self, msg, level=1, *args):  # pylint: disable=keyword-arg-before-vararg
        """Log wrapper"""
        ulog(msg, *args, name=self.__class__.__name__, level=level)

    def run(self):
        """Main service loop"""
        self.log('Service started', 0)

        while not self.abortRequested():
            # check every 1 sec
            if self.waitForAbort(1):
                # Abort was requested while waiting. We should exit
                break

            try:
                self._check_playback()
            except Exception:  # pylint: disable=broad-except
                # Never let an unexpected error kill the service: log it,
                # stop tracking the current playback and keep monitoring.
                self.log('Unexpected error in service loop:\n%s', 0, format_exc())
                self._reset_after_error()

        self.log('Service stopped', 0)

    def _reset_after_error(self):
        """Best-effort cleanup after an unexpected error in the service loop"""
        for cleanup in (self.player.disable_tracking,
                        self.playback_manager.demo.hide,
                        self.playback_manager.close_popup,
                        self.player.reset_queue,
                        self.api.reset_addon_data):
            try:
                cleanup()
            except Exception:  # pylint: disable=broad-except
                self.log('Cleanup after error failed:\n%s', 0, format_exc())

    def _check_playback(self):  # pylint: disable=too-many-branches,too-many-return-statements
        """Check the current playback and launch Up Next when due"""
        if not self.player.is_tracking():
            return

        if bool(get_property('PseudoTVRunning') == 'True'):
            self.player.disable_tracking()
            self.playback_manager.demo.hide()
            return

        if get_setting_bool('disableNextUp', cache=True):
            # Next Up is disabled
            self.player.disable_tracking()
            self.playback_manager.demo.hide()
            return

        # Method isExternalPlayer() was added in Kodi v18 onward
        if kodi_version_major() >= 18 and self.player.isExternalPlayer():
            self.log('Up Next tracking stopped, external player detected', 2)
            self.player.disable_tracking()
            self.playback_manager.demo.hide()
            return

        last_file = self.player.get_last_file()
        try:
            current_file = to_unicode(self.player.getPlayingFile())
        except RuntimeError:
            self.log('Up Next tracking stopped, failed player.getPlayingFile()', 2)
            self.player.disable_tracking()
            self.playback_manager.demo.hide()
            return

        if (current_file.startswith((
                'bluray://', 'dvd://', 'udf://', 'iso9660://', 'cdda://'))
                or current_file.endswith((
                    '.bdmv', '.iso', '.ifo'))):
            self.log('Up Next tracking stopped, Blu-ray/DVD/CD playing', 2)
            self.player.disable_tracking()
            self.playback_manager.demo.hide()
            return

        if last_file and last_file == current_file:
            # Already processed this playback before
            return

        try:
            total_time = self.player.getTotalTime()
        except RuntimeError:
            self.log('Up Next tracking stopped, failed player.getTotalTime()', 2)
            self.player.disable_tracking()
            self.playback_manager.demo.hide()
            return

        if total_time == 0:
            self.log('Up Next tracking stopped, no file is playing', 2)
            self.player.disable_tracking()
            self.playback_manager.demo.hide()
            return

        try:
            play_time = self.player.getTime()
        except RuntimeError:
            self.log('Up Next tracking stopped, failed player.getTime()', 2)
            self.player.disable_tracking()
            self.playback_manager.demo.hide()
            return

        notification_time = self.api.notification_time(total_time=total_time)
        if total_time - play_time > notification_time:
            # Media hasn't reach notification time yet, waiting a bit longer...
            return

        self.player.set_last_file(current_file)
        self.log('Show notification as episode (of length %d secs) ends in %d secs', 2, total_time, notification_time)
        if self.playback_manager.launch_up_next():
            # Playback moved back before the notification time, keep tracking
            return
        self.log('Up Next style autoplay succeeded', 2)
        self.player.disable_tracking()

    def onSettingsChanged(self):  # pylint: disable=invalid-name
        """Settings changed event handler, re-read the cached settings"""
        clear_setting_cache()

    def onNotification(self, sender, method, data):  # pylint: disable=invalid-name
        """Notification event handler for accepting data from add-ons"""
        if not method.endswith('upnext_data'):  # Method looks like Other.upnext_data
            return

        decoded_data, encoding = decode_json(data)
        if decoded_data is None:
            self.log('Received data from sender %s is not JSON: %s', 2, sender, data)
            return

        self.playback_manager.handle_demo()
        decoded_data.update(id='%s_play_action' % sender.replace('.SIGNAL', ''))
        self.api.addon_data_received(decoded_data, encoding=encoding)
        self.player.enable_tracking()
        self.player.reset_queue()
