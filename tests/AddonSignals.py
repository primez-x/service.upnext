# -*- coding: utf-8 -*-
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)
''' Minimal stub of script.module.addon.signals (AddonSignals) for testing the payload encoding '''

# pylint: disable=invalid-name

from __future__ import absolute_import, division, unicode_literals

import json
from base64 import b64decode, b64encode


def _encodeData(data):
    ''' Encode data like AddonSignals: base64 encoded JSON '''
    return b64encode(json.dumps(data).encode('utf-8')).decode('ascii')


def _decodeData(data):
    ''' Decode data like AddonSignals: a JSON list holding base64 encoded JSON '''
    data = json.loads(data)
    if data:
        return json.loads(b64decode(data[0]).decode('utf-8'))
    return None
