# Up Next

Up Next shows an episode countdown near the end of Kodi video playback. The prompt can start the next episode, stop playback, or ask whether you are still watching after several automatic plays.

The add-on manifest imports Kodi's `xbmc.python` API at version `3.0.0`.

## Install

1. Install the [Primez repository ZIP](https://primez-x.github.io/kodi.addons/repository.primez.addons/repository.primez.addons-1.0.0.zip) in Kodi.
2. Open **Add-ons → Install from repository → Primez Kodi Add-ons → Services**.
3. Install **Up Next** and open the add-on settings from Kodi's Services list.

See the [Primez repository site](https://primez-x.github.io/kodi.addons/) and the [central repository guide](https://github.com/primez-x/kodi.addons/blob/main/README.md) for repository setup.

## Playback and provider support

The service watches Kodi's video player for episodes. Kodi's video library can supply the next episode. The **Enable on playlists** setting also permits prompts for existing Kodi video playlist items; the default is off.

Third-party providers must send Kodi's `Other.upnext_data` notification with next-episode data to use the provider path. The service reads `current_episode`, `next_episode`, and optional `notification_time`, `notification_offset`, `play_url`, or `play_info` fields. Provider support depends on each add-on's implementation.

For an existing playlist item, Kodi keeps control of the queue and advances normally. Outside a playlist, Up Next queues a Kodi library episode ID or provider `play_url` when available. If a provider supplies only `play_info`, Up Next sends the play action to that provider. The service records the queued position and removes only that item when playback does not advance.

Up Next stops tracking external players and optical-disc sources. The service does not provide provider playback or guarantee support from every provider add-on.

## Settings

- **Display mode:** Fancy by default; Simple is also available.
- **Close action:** Show **Close** by default, or show **Stop** instead.
- **Default action:** Play the next episode when the countdown ends, or stop playing.
- **Enable on playlists:** Off by default.
- **Include already watched episodes:** Off by default.
- **Still there? prompt:** Ask after 3 automatic episodes by default. Set the count from 0 to 15.
- **Autoplay duration:** Customize by episode length by default. The defaults range from 15 seconds for episodes up to 10 minutes to 60 seconds for episodes over an hour. Turn customization off to use 30 seconds for every episode.
- **Expert:** Disable Up Next or change the log level.
- **Developer:** Enable demo mode and preview the four popup layouts.

## Source layout

- `resources/lib/service_entry.py` starts the background service.
- `resources/lib/monitor.py`, `playbackmanager.py`, and `api.py` track playback, show prompts, and handle provider or Kodi data.
- `resources/settings.xml` defines settings.
- `resources/skins/default/1080i/` contains popup layouts.
- `tests/` contains Python tests with Kodi stubs.

## Tests and maintenance

The configured publish test is:

```sh
PYTHONPATH=resources/lib:tests python3 -m pytest -q -o addopts= tests
```

The tracked branch is `master`. A configured source webhook forwards tracked-branch pushes to the central publish workflow. If the webhook is absent or rejected, use the manual workflow described in the central guide. Enable local publish checks with `git config core.hooksPath .githooks`.

README-only edits do not need an add-on version bump. Changes to shipped behavior need a new `addon.xml` version and a matching first line in `<news>`. Follow the central [versioning rules](https://github.com/primez-x/kodi.addons/blob/main/VERSIONING.md).

Up Next began in [im85288's upstream repository](https://github.com/im85288/service.upnext). The Primez fork is maintained in [primez-x/service.upnext](https://github.com/primez-x/service.upnext) and uses [GPL-2.0-only](LICENSE).

The shared `utils.py` and `statichelper.py` modules are maintained in [`kodi.addons/tools/service_common/`](https://github.com/primez-x/kodi.addons/tree/main/tools/service_common/). From the central repository root, run `python3 tools/sync_service_common.py --check` to compare the copies. Run `python3 tools/sync_service_common.py` to copy changed masters to both source trees.
