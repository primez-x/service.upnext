# -*- coding: utf-8 -*-
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)

# pylint: disable=missing-docstring

from __future__ import absolute_import, division, unicode_literals

import utils


class Unformattable:
    def __str__(self):
        raise AssertionError('suppressed log message was formatted')


def test_log_settings_are_cached_and_suppressed_messages_not_formatted(monkeypatch):
    reads = []
    logged = []
    monkeypatch.setattr(utils, 'get_setting_int', lambda key, default=None: reads.append(key) or 0)
    monkeypatch.setattr(utils, 'get_global_setting', lambda key: reads.append(key) or False)
    monkeypatch.setattr(utils, 'set_property', lambda key, value: None)
    monkeypatch.setattr(utils, 'xlog', lambda msg, level: logged.append(msg))
    monkeypatch.setattr(utils, 'get_kodi_version', lambda: 19.0)
    utils.clear_setting_cache()

    for _ in range(10):
        utils.log('suppressed %s', Unformattable(), name='Test', level=2)
    utils.log('logged %(key)s', {'key': 'mapping'}, name='Test', level=0)
    utils.log('logged %d %s', 1, 'two', name='Test', level=0)

    assert reads == ['logLevel', 'debug.showloginfo']
    assert len(logged) == 2
    assert logged[0].endswith('Test -> logged mapping')
    assert logged[1].endswith('Test -> logged 1 two')

    # Settings are read again after a settings change
    utils.clear_setting_cache()
    utils.log('suppressed', name='Test', level=2)
    assert reads == ['logLevel', 'debug.showloginfo'] * 2
    utils.clear_setting_cache()


def test_cached_settings_are_read_once_per_playback(monkeypatch):
    reads = []

    class CountingAddon:
        @staticmethod
        def getSettingInt(key):  # pylint: disable=invalid-name
            reads.append(key)
            return 30

    monkeypatch.setattr(utils, 'Addon', CountingAddon)
    utils.clear_setting_cache()

    assert utils.get_setting_int('autoPlaySeasonTime', cache=True) == 30
    assert utils.get_setting_int('autoPlaySeasonTime', cache=True) == 30
    assert reads == ['autoPlaySeasonTime']

    # Uncached reads always reflect the current setting
    assert utils.get_setting_int('autoPlaySeasonTime') == 30
    assert reads == ['autoPlaySeasonTime'] * 2

    utils.clear_setting_cache()
    utils.get_setting_int('autoPlaySeasonTime', cache=True)
    assert reads == ['autoPlaySeasonTime'] * 3
    utils.clear_setting_cache()
