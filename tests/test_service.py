# -*- coding: utf-8 -*-
# GNU General Public License v2.0 (see COPYING or https://www.gnu.org/licenses/gpl-2.0.txt)

from __future__ import absolute_import, division, unicode_literals


def test_script():
    try:
        import script_entry
        test_complete = True
    except ImportError:
        test_complete = False
    
    assert test_complete is True


def test_service():
    # The xbmc.Monitor stub requests an abort only after 90-120 seconds; the
    # service loop does the same work every tick, so let it run a few ticks.
    # NOTE: The abort is global, keep this the last test that waits for abort.
    from threading import Timer
    from xbmc import Monitor
    abort_timer = Timer(5, Monitor._aborted.set)  # pylint: disable=protected-access
    abort_timer.daemon = True
    abort_timer.start()
    try:
        import service_entry
        test_complete = True
    except ImportError:
        test_complete = False
    
    assert test_complete is True
