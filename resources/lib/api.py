# -*- coding: utf-8 -*-
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)

from __future__ import absolute_import, division, unicode_literals
from xbmc import sleep, Monitor, PLAYLIST_VIDEO, PLAYLIST_MUSIC
from utils import event, get_int, get_setting_bool, get_setting_int, jsonrpc, log as ulog


class Api:  # pylint: disable=too-many-public-methods
    """Main API class"""
    _shared_state = {}

    PLAYER_PLAYLIST = {
        'video': PLAYLIST_VIDEO,  # 1
        'audio': PLAYLIST_MUSIC   # 0
    }

    def __init__(self):
        """Constructor for Api class"""
        self.__dict__ = self._shared_state
        self.data = {}
        self.encoding = 'base64'

    def log(self, msg, level=2, *args):  # pylint: disable=keyword-arg-before-vararg
        """Log wrapper"""
        ulog(msg, *args, name=self.__class__.__name__, level=level)

    def has_addon_data(self):
        return self.data

    def reset_addon_data(self):
        self.data = {}

    def addon_data_received(self, data, encoding='base64'):
        self.log('addon_data_received called with data %s', 2, data)
        self.data = data
        self.encoding = encoding

    @staticmethod
    def play_kodi_item(episode):
        jsonrpc(method='Player.Open', id=0, params={'item': {'episodeid': episode.get('episodeid')}})

    @staticmethod
    def _get_playerid(playerid_cache=[None]):  # pylint: disable=dangerous-default-value
        """Function to get active player playerid"""

        # We don't need to actually get playerid everytime, cache and reuse instead
        if playerid_cache[0] is not None:
            return playerid_cache[0]

        # Sometimes Kodi gets confused and uses a music playlist for video content,
        # so get the first active player instead, default to video player.
        result = jsonrpc(method='Player.GetActivePlayers')
        result = [
            player for player in result.get('result', [{}])
            if player.get('type', 'video') in Api.PLAYER_PLAYLIST
        ]

        playerid = get_int(result[0], 'playerid') if result else -1

        if playerid == -1:
            return None

        playerid_cache[0] = playerid
        return playerid

    @staticmethod
    def get_playlistid(playlistid_cache=[None]):  # pylint: disable=dangerous-default-value
        """Function to get playlistid of active player"""

        # We don't need to actually get playlistid everytime, cache and reuse instead
        if playlistid_cache[0] is not None:
            return playlistid_cache[0]

        result = jsonrpc(
            method='Player.GetProperties',
            params={
                'playerid': Api._get_playerid(playerid_cache=[None]),
                'properties': ['playlistid'],
            }
        )
        result = get_int(
            result.get('result', {}), 'playlistid', Api.PLAYER_PLAYLIST['video']
        )

        return result

    def queue_next_item(self, episode):
        next_item = {}
        if not self.data:
            next_item.update(episodeid=episode.get('episodeid'))
        elif self.data.get('play_url'):
            next_item.update(file=self.data.get('play_url'))

        if next_item:
            jsonrpc(
                method='Playlist.Add',
                id=0,
                params={
                    'playlistid': Api.get_playlistid(),
                    'item': next_item
                }
            )

        return bool(next_item)

    @staticmethod
    def dequeue_next_item():
        """Remove unplayed next item from video playlist"""
        jsonrpc(
            method='Playlist.Remove',
            id=0,
            params={
                'playlistid': Api.get_playlistid(),
                'position': 1
            }
        )
        return False

    @staticmethod
    def reset_queue():
        """Remove previously played item from video playlist"""
        jsonrpc(
            method='Playlist.Remove',
            id=0,
            params={
                'playlistid': Api.get_playlistid(),
                'position': 0
            }
        )

    def get_next_in_playlist(self, position):
        result = jsonrpc(method='Playlist.GetItems', params={
            'playlistid': Api.get_playlistid(),
            # limits are zero indexed, position is one indexed
            'limits': {'start': position, 'end': position + 1},
            'properties': ['art', 'dateadded', 'episode', 'file', 'firstaired', 'lastplayed',
                           'playcount', 'plot', 'rating', 'resume', 'runtime', 'season',
                           'showtitle', 'streamdetails', 'title', 'tvshowid', 'writer'],
        })

        item = result.get('result', {}).get('items')

        # Don't check if next item is an episode, just use it if it is there
        if not item:  # item.get('type') != 'episode':
            self.log('Error: no next item found in playlist', 1)
            return None
        item = item[0]

        # Playlist item may not have had video info details set
        # Try and populate required details if missing
        if not item.get('title'):
            item['title'] = item.get('label', '')
        item['episodeid'] = get_int(item, 'id')
        item['tvshowid'] = get_int(item, 'tvshowid')
        # If missing season/episode, change to empty string to avoid episode
        # formatting issues ("S-1E-1") in UpNext popup
        if get_int(item, 'season') == -1:
            item['season'] = ''
        if get_int(item, 'episode') == -1:
            item['episode'] = ''

        self.log('Next item in playlist: %s', 2, item)
        return item

    def play_addon_item(self):
        if self.data.get('play_url'):
            self.log('Playing the next episode directly: %(play_url)s', 2, self.data)
            jsonrpc(method='Player.Open', params={'item': {'file': self.data.get('play_url')}})
        else:
            self.log('Sending %s data to add-on to play: %s', 2, self.encoding, self.data.get('play_info'))
            event(message=self.data.get('id'), data=self.data.get('play_info'), sender='upnextprovider', encoding=self.encoding)

    def handle_addon_lookup_of_next_episode(self):
        if not self.data:
            return None
        self.log('handle_addon_lookup_of_next_episode episode returning data %(next_episode)s', 2, self.data)
        return self.data.get('next_episode')

    def handle_addon_lookup_of_current_episode(self):
        if not self.data:
            return None
        self.log('handle_addon_lookup_of_current episode returning data %(current_episode)s', 2, self.data)
        return self.data.get('current_episode')

    def notification_time(self, total_time=None):
        # Alway use metadata, when available
        if self.data.get('notification_time'):
            return int(self.data.get('notification_time'))

        # Some consumers send the offset when the credits start (e.g. Netflix)
        if total_time and self.data.get('notification_offset'):
            return total_time - int(self.data.get('notification_offset'))

        # Use a customized notification time, when configured
        # This is called every service tick, so the settings are cached per playback
        if total_time and get_setting_bool('customAutoPlayTime', cache=True):
            if total_time > 60 * 60:
                return get_setting_int('autoPlayTimeXL', cache=True)
            if total_time > 40 * 60:
                return get_setting_int('autoPlayTimeL', cache=True)
            if total_time > 20 * 60:
                return get_setting_int('autoPlayTimeM', cache=True)
            if total_time > 10 * 60:
                return get_setting_int('autoPlayTimeS', cache=True)
            return get_setting_int('autoPlayTimeXS', cache=True)

        # Use one global default, regardless of episode length
        return get_setting_int('autoPlaySeasonTime', cache=True)

    def notification_duration(self):
        """Return a provider-requested bounded popup duration, if any."""
        duration = self.data.get('notification_duration')
        if duration is None:
            return None
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            self.log('Ignoring invalid notification duration: %s', 1, duration)
            return None
        if duration <= 0:
            return None
        # Keep a malformed provider payload from recreating a multi-minute
        # overlay. Native notifications do not send this field.
        return min(duration, 60)

    def get_now_playing(self, max_tries=20):
        """Return Player.GetItem details for the active player, or {} if none becomes active"""
        # The player can take a moment to become active, so poll a bounded
        # number of times instead of busy-looping forever.
        monitor = Monitor()
        result = {}
        for attempt in range(max_tries):
            result = jsonrpc(method='Player.GetActivePlayers') or {}
            self.log('Got active player %s', 2, result)
            if result.get('result'):
                break
            if attempt < max_tries - 1 and monitor.waitForAbort(0.1):
                return {}

        if not result.get('result'):
            self.log('No active player found after %d tries', 1, max_tries)
            return {}

        playerid = result.get('result')[0].get('playerid')

        # Get details of the playing media
        self.log('Getting details of now playing media', 2)
        result = jsonrpc(method='Player.GetItem', params={
            'playerid': playerid,
            'properties': ['episode', 'genre', 'playcount', 'plotoutline', 'season', 'showtitle', 'tvshowid'],
        })
        self.log('Got details of now playing media %s', 2, result)
        return result

    def handle_kodi_lookup_of_episode(self, tvshowid, current_file, include_watched, current_episode_id):
        result = jsonrpc(method='VideoLibrary.GetEpisodes', params={
            'tvshowid': tvshowid,
            'properties': ['art', 'dateadded', 'episode', 'file', 'firstaired', 'lastplayed',
                           'playcount', 'plot', 'rating', 'resume', 'runtime', 'season',
                           'showtitle', 'streamdetails', 'title', 'tvshowid', 'writer'],
            'sort': {'method': 'episode'},
        })

        if not result.get('result'):
            return None

        self.log('Got details of next up episode %s', 2, result)
        sleep(100)

        # Find the next unwatched and the newest added episodes
        return self.find_next_episode(result, current_file, include_watched, current_episode_id)

    def handle_kodi_lookup_of_current_episode(self, tvshowid, current_episode_id):
        result = jsonrpc(method='VideoLibrary.GetEpisodes', params={
            'tvshowid': tvshowid,
            'properties': ['art', 'dateadded', 'episode', 'file', 'firstaired', 'lastplayed',
                           'playcount', 'plot', 'rating', 'resume', 'runtime', 'season',
                           'showtitle', 'streamdetails', 'title', 'tvshowid', 'writer'],
            'sort': {'method': 'episode'},
        })

        if not result.get('result'):
            return None

        self.log('Find current episode called', 2)
        sleep(100)

        # Find the next unwatched and the newest added episodes
        episodes = result.get('result', {}).get('episodes', [])
        for idx, episode in enumerate(episodes):
            # Find position of current episode
            if current_episode_id == episode.get('episodeid'):
                self.log('Find current episode found episode in position: %d', 2, idx)
                return episode

        # No next episode found
        self.log('No next episode found', 1)
        return None

    @staticmethod
    def showtitle_to_id(title):
        result = jsonrpc(method='VideoLibrary.GetTVShows', id='libTvShows', params={'properties': ['title']})

        for tvshow in result.get('result', {}).get('tvshows', []):
            if tvshow.get('label') == title:
                return tvshow.get('tvshowid')
        return '-1'

    @staticmethod
    def get_episode_id(showid, show_season, show_episode):
        show_season = int(show_season)
        show_episode = int(show_episode)
        result = jsonrpc(method='VideoLibrary.GetEpisodes', params={
            'properties': ['episode', 'season'],
            'tvshowid': int(showid),
        })

        episodeid = 0
        for episode in result.get('result', {}).get('episodes', []):
            if episode.get('episodeid') and episode.get('season') == show_season and episode.get('episode') == show_episode:
                episodeid = episode.get('episodeid')

        return episodeid

    def find_next_episode(self, result, current_file, include_watched, current_episode_id):
        found_match = False
        current_library_file = current_file
        episodes = result.get('result', {}).get('episodes', [])
        for episode in episodes:
            # Find position of current episode
            episode_library_file = episode.get('file')
            if current_episode_id == episode.get('episodeid'):
                found_match = True
                current_library_file = episode_library_file
                continue
            # Check if it may be a multi-part episode
            if episode_library_file in (current_file, current_library_file):
                continue
            # Skip already watched episodes?
            if not include_watched and episode.get('playcount') > 0:
                continue
            if found_match:
                return episode

        # No next episode found
        self.log('No next episode found', 1)
        return None
