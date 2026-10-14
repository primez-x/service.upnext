# -*- coding: utf-8 -*-
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)
# pylint: disable=missing-docstring,protected-access

from __future__ import absolute_import, division, unicode_literals

import json
import unittest
import api as api_module
import utils


class QueueTransport:
    """Capture Kodi requests and apply Kodi playlist response shapes."""
    def __init__(self, playlistid, media_type):
        self.playlistid = playlistid
        self.media_type = media_type
        self.active_playlistid = playlistid
        self.playlists = {playlistid: [
            {'file': 'first'}, {'file': 'second'}, {'file': 'current'},
        ], 1 - playlistid: [{'file': 'other-player'}]}
        self.calls = []
        self.counts = {}
        self.responses = {}
        self.before_add = None
        self.after_add = None

    @property
    def items(self):
        return self.playlists[self.playlistid]

    @items.setter
    def items(self, value):
        self.playlists[self.playlistid] = value

    def execute(self, payload):
        request = json.loads(payload)
        method = request['method']
        params = request.get('params', {})
        self.calls.append((method, params))
        count = self.counts.get(method, 0) + 1
        self.counts[method] = count
        override = self.responses.get((method, count))
        if override is not None:
            if isinstance(override, Exception):
                raise override
            return json.dumps(override)
        if method == 'Player.GetActivePlayers':
            result = [{'playerid': self.active_playlistid,
                       'type': 'video' if self.active_playlistid else 'audio'}]
        elif method == 'Player.GetProperties':
            result = {'playlistid': self.active_playlistid}
        elif method == 'Playlist.GetItems':
            items = self.playlists[params['playlistid']]
            limits = params.get('limits', {})
            start = limits.get('start', 0)
            end = min(limits.get('end', len(items)), len(items))
            result = {'limits': {'start': start, 'end': end, 'total': len(items)}}
            if items[start:end]:
                result['items'] = items[start:end]
        elif method == 'Playlist.Add':
            if self.before_add:
                self.before_add()
            item = params['item']
            if 'file' in item:
                entry = {'file': item['file'], 'type': 'unknown', 'label': 'Next'}
            else:
                entry = {'id': item[self.media_type + 'id'],
                         'type': self.media_type, 'file': 'owned', 'label': 'Next'}
            self.playlists[params['playlistid']].append(entry)
            if self.after_add:
                self.after_add()
            result = 'OK'
        elif method == 'Playlist.Remove':
            items = self.playlists[params['playlistid']]
            if not 0 <= params['position'] < len(items):
                return json.dumps({'error': {'code': -32602, 'message': 'Invalid position'}})
            items.pop(params['position'])
            result = 'OK'
        elif method == 'Settings.GetSettingValue':
            result = {'value': True}
        else:
            result = {}
        return json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result})

    def removals(self):
        return [params for method, params in self.calls if method == 'Playlist.Remove']


class QueueOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.configure_api()
        self.api_module.Api._shared_state.clear()
        self.api_module.Api.clear_caches()
        self.api = self.api_module.Api()
        self.transport = QueueTransport(self.playlistid, self.media_type)
        self.original_execute = self.utils.executeJSONRPC
        self.original_playlist = getattr(self.api_module, 'PlayList', None)
        self.utils.clear_setting_cache()
        self.utils.executeJSONRPC = self.transport.execute
        transport = self.transport

        class NativePlaylist:
            def __init__(self, playlistid):
                self.playlistid = playlistid

            def size(self):
                return len(transport.playlists[self.playlistid])

        self.api_module.PlayList = NativePlaylist
        self.item = {self.input_id: 42}

    def tearDown(self):
        self.utils.executeJSONRPC = self.original_execute
        self.utils.clear_setting_cache()
        self.api_module.PlayList = self.original_playlist
        self.api_module.Api._shared_state.clear()
        self.api_module.Api.clear_caches()

    def queue(self):
        self.assertTrue(self.api.queue_next_item(self.item))

    def cancel(self, expected):
        self.assertFalse(self.api.dequeue_next_item())
        self.assertEqual(self.transport.items, expected)

    def test_invalid_library_ids_are_not_added(self):
        for item in ({}, {self.input_id: None}, {self.input_id: -1}):
            with self.subTest(item=item):
                self.assertFalse(self.api.queue_next_item(item))
        self.assertFalse(any(method == 'Playlist.Add' for method, _ in self.transport.calls))

    def test_provider_without_url_is_not_added(self):
        self.api.data = {'next_item': {}}
        self.assertFalse(self.api.queue_next_item(self.item))
        self.assertFalse(any(method == 'Playlist.Add' for method, _ in self.transport.calls))

    def test_dequeue_without_ownership_preserves_playlist(self):
        self.cancel([{'file': 'first'}, {'file': 'second'}, {'file': 'current'}])
        self.assertEqual(self.transport.removals(), [])

    def test_successful_add_removes_only_appended_library_item_once(self):
        self.queue()
        expected = [{'file': 'first'}, {'file': 'second'}, {'file': 'current'}]
        self.cancel(expected)
        self.cancel(expected)
        self.assertEqual(self.transport.removals(), [
            {'playlistid': self.playlistid, 'position': 3},
        ])

    def test_user_insert_before_owned_item_is_preserved(self):
        self.transport.items = [{'file': 'current'}]
        self.queue()
        self.transport.items.insert(1, {'file': 'user-selected-next'})
        self.cancel([{'file': 'current'}, {'file': 'user-selected-next'}])

    def test_user_removal_before_owned_item_changes_removal_position(self):
        self.queue()
        self.transport.items.pop(0)
        self.cancel([{'file': 'second'}, {'file': 'current'}])

    def test_user_reorder_moves_owned_item(self):
        self.queue()
        self.transport.items.insert(0, self.transport.items.pop())
        self.cancel([{'file': 'first'}, {'file': 'second'}, {'file': 'current'}])

    def test_active_player_switch_preserves_other_playlist(self):
        self.queue()
        self.transport.active_playlistid = 1 - self.playlistid
        self.api_module.Api.clear_caches()
        self.cancel([{'file': 'first'}, {'file': 'second'}, {'file': 'current'}])
        self.assertEqual(self.transport.playlists[1 - self.playlistid],
                         [{'file': 'other-player'}])
        self.assertEqual(self.transport.removals(), [
            {'playlistid': self.playlistid, 'position': 3},
        ])

    def test_absent_owned_item_preserves_replacement(self):
        self.queue()
        self.transport.items[-1] = {'file': 'user-selected-next'}
        self.cancel([{'file': 'first'}, {'file': 'second'}, {'file': 'current'},
                     {'file': 'user-selected-next'}])
        self.assertEqual(self.transport.removals(), [])

    def test_duplicate_after_add_preserves_both_entries(self):
        self.queue()
        self.transport.items.append(dict(self.transport.items[-1]))
        expected = [dict(entry) for entry in self.transport.items]
        self.cancel(expected)
        self.assertEqual(self.transport.removals(), [])

    def test_preexisting_duplicate_is_preserved_after_appended_entry_disappears(self):
        existing = {'id': 42, 'type': self.media_type, 'file': 'owned', 'label': 'Next'}
        self.transport.items = [{'file': 'current'}, existing]
        self.queue()
        self.transport.items.pop()
        self.transport.items.insert(1, {'file': 'user-selected-next'})
        self.cancel([{'file': 'current'}, {'file': 'user-selected-next'}, existing])
        self.assertEqual(self.transport.removals(), [])

    def test_provider_file_identity_preserves_different_path_with_same_label(self):
        self.api.data = {'play_url': 'plugin://provider/owned'}
        self.transport.items = [{'file': 'plugin://provider/user',
                                 'type': 'unknown', 'label': 'Next'}]
        self.queue()
        self.transport.items.reverse()
        self.cancel([{'file': 'plugin://provider/user', 'type': 'unknown', 'label': 'Next'}])

    def test_provider_preexisting_duplicate_is_never_claimed(self):
        existing = {'file': 'plugin://provider/owned', 'type': 'unknown', 'label': 'Next'}
        self.api.data = {'play_url': 'plugin://provider/owned'}
        self.transport.items = [existing]
        self.queue()
        self.transport.items.pop()
        self.cancel([existing])
        self.assertEqual(self.transport.removals(), [])

    def test_other_media_type_with_same_library_id_is_preserved(self):
        existing = {'id': 42, 'type': 'movie', 'file': 'user-selected-next'}
        self.transport.items = [existing]
        self.queue()
        self.transport.items.reverse()
        self.cancel([existing])

    def test_failed_or_unconfirmed_add_never_claims_ownership(self):
        responses = ({'error': {'code': -1, 'message': 'Add failed'}}, {},
                     {'result': False}, {'result': None},
                     {'result': 'OK', 'error': {'code': -1}}, RuntimeError('transport failed'))
        for response in responses:
            with self.subTest(response=response):
                self.api_module.Api._shared_state.clear()
                self.api = self.api_module.Api()
                count = self.transport.counts.get('Playlist.Add', 0) + 1
                self.transport.responses[('Playlist.Add', count)] = response
                self.assertFalse(self.api.queue_next_item(self.item))
                self.cancel([{'file': 'first'}, {'file': 'second'}, {'file': 'current'}])
        self.assertEqual(self.transport.removals(), [])

    def test_unreadable_snapshot_before_add_preserves_playlist(self):
        self.transport.responses[('Playlist.GetItems', 1)] = {
            'error': {'code': -1, 'message': 'GetItems failed'},
        }
        self.assertFalse(self.api.queue_next_item(self.item))
        self.assertFalse(any(method == 'Playlist.Add' for method, _ in self.transport.calls))

    def test_unreadable_confirmation_does_not_claim_successful_add(self):
        self.transport.responses[('Playlist.GetItems', 2)] = {
            'error': {'code': -1, 'message': 'GetItems failed'},
        }
        self.queue()
        expected = [dict(entry) for entry in self.transport.items]
        self.cancel(expected)
        self.assertEqual(self.transport.removals(), [])

    def test_successful_add_without_observed_identity_is_not_claimed(self):
        self.transport.after_add = lambda: self.transport.items.pop()
        self.queue()
        self.transport.items.append({'file': 'user-selected-next'})
        self.cancel([{'file': 'first'}, {'file': 'second'}, {'file': 'current'},
                     {'file': 'user-selected-next'}])
        self.assertEqual(self.transport.removals(), [])

    def test_unreadable_or_incomplete_snapshot_at_dequeue_never_removes(self):
        responses = (
            {'error': {'code': -1, 'message': 'GetItems failed'}}, {},
            {'result': {'items': None}}, {'result': 'OK'},
            {'result': {'items': [None], 'limits': {'start': 0, 'end': 1, 'total': 1}}},
            {'result': {'items': [], 'limits': None}},
            {'result': {'items': [{'id': 42, 'type': self.media_type}],
                        'limits': {'start': 3, 'end': 4, 'total': 4}}},
            {'result': {'items': [{'id': 42, 'type': self.media_type}],
                        'limits': {'start': 0, 'end': 1, 'total': 4}}},
            RuntimeError('transport failed'), ValueError('invalid JSON'),
        )
        for response in responses:
            with self.subTest(response=response):
                self.api_module.Api._shared_state.clear()
                self.api = self.api_module.Api()
                self.transport.items = [{'file': 'current'}]
                self.queue()
                expected = [dict(entry) for entry in self.transport.items]
                count = self.transport.counts.get('Playlist.GetItems', 0) + 1
                self.transport.responses[('Playlist.GetItems', count)] = response
                self.cancel(expected)
        self.assertEqual(self.transport.removals(), [])

    def test_empty_playlist_can_add_and_remove_owned_item(self):
        self.transport.items = []
        self.queue()
        self.cancel([])

    def test_duplicate_insert_during_add_confirmation_is_preserved(self):
        self.transport.after_add = lambda: self.transport.items.append(
            dict(self.transport.items[-1]))
        self.queue()
        expected = [dict(entry) for entry in self.transport.items]
        self.transport.items.pop()
        self.cancel(expected[:-1])
        self.assertEqual(self.transport.removals(), [])

    def test_user_insert_during_add_uses_confirmed_identity(self):
        self.transport.before_add = lambda: self.transport.items.insert(
            0, {'file': 'user-selected-next'})
        self.queue()
        self.cancel([{'file': 'user-selected-next'}, {'file': 'first'},
                     {'file': 'second'}, {'file': 'current'}])

    def test_another_api_instance_can_remove_shared_owned_entry(self):
        self.queue()
        self.api = self.api_module.Api()
        self.transport.items.insert(0, {'file': 'user-selected-next'})
        self.cancel([{'file': 'user-selected-next'}, {'file': 'first'},
                     {'file': 'second'}, {'file': 'current'}])

    def test_remove_rpc_failure_never_retries_stale_position(self):
        self.queue()
        self.transport.responses[('Playlist.Remove', 1)] = {
            'error': {'code': -1, 'message': 'Remove failed'},
        }
        expected = [dict(entry) for entry in self.transport.items]
        self.cancel(expected)
        self.transport.items.insert(0, {'file': 'user-selected-next'})
        self.cancel([{'file': 'user-selected-next'}] + expected)
        self.assertEqual(len(self.transport.removals()), 1)

    def configure_api(self):
        self.api_module = api_module
        self.utils = utils
        self.playlistid = 1
        self.media_type = 'episode'
        self.input_id = 'episodeid'
