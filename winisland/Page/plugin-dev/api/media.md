# Media API

`MediaApiV2` lets a plugin supply its own now-playing source. Declare `CAP_MEDIA` and query `IFACE_MEDIA`. The SDK `host.media()?.create_source(title, artist)` creates a basic source without controls; use the raw table for timeline, cover bytes, playback state, and control callbacks.

## A typical use

For an internet radio plugin, publish the station and current track with `create`, then call `update` when the track or playback position changes. If you advertise a play/pause or seek button, provide `on_command` and handle that action in your player. The host shows the button; it does not operate your player for you. Release the source when the stream stops or the plugin shuts down.

The SDK shortcut is enough for static title and artist text:

```rust
let source = host.media()?.create_source("Sample track", "Sample artist")?;
// Keep `source` alive while this track should be available.
```

## Methods

Each method takes `context, token` first and returns `PluginStatus`.

| Method | Remaining parameters | Result |
|---|---|---|
| `create` | `*const MediaSourceDataV2`, `*mut ResourceId` | Publishes a source and writes its ID. |
| `update` | `ResourceId`, `*const MediaSourceDataV2` | Replaces source data. |
| `release` | `ResourceId` | Removes the source. |
| `current_title` | `*mut u8`, capacity, `*mut u32` required | Copies the active media title as UTF-8 bytes. |

## Source and command contract

`MediaSourceDataV2` contains a required title, optional artist and album, `duration_ms`, `position_ms`, `MEDIA_FLAG_PLAYING`, declared `MEDIA_CONTROL_*` bits, and optional JPEG or PNG cover bytes. The host copies the cover during `create` and `update`; one cover is limited to 16 MiB. A nonzero control mask requires `on_command` and live `callback_data`.

The callback receives `MediaCommandV2` on a plugin worker. Its command is toggle play, previous, next, or seek; only seek uses `position_ms`. Keep callback data alive until the source can be released. Updating or releasing a source while its command callback is in flight returns `LimitExceeded`. The current quota is four media sources and 32 MiB of source resource bytes per plugin.

`current_title` uses a required-length output parameter. Query with a zero-capacity buffer, allocate the reported length, then call again. A title can change between calls.

See the [media source example](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/examples/media_source.rs) and [data types](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/types/v2/context.rs).

[All plugin APIs](/plugin-dev/api)
