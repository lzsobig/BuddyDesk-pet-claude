# Plugin API reference

The ABI v2 host exposes eleven service tables. Pick a task below, then open its page for the methods, inputs, ownership rules, and limits. If you have not loaded a plugin yet, start with the [quickstart](/plugin-dev/quickstart); the tables below only become available after `create` receives a host and token.

Every service call takes the table's `prefix.context` and the host-issued `PluginToken`. It returns `PluginStatus`; created resources belong to that token. Query a table with `PluginHostV2.query(context, IFACE_*, IFACE_VERSION_1)`, check its size and version, then check each function slot you use. The SDK `Host` wrapper performs these table checks for its convenience methods.

| API | What it provides |
|---|---|
| [Context API](/plugin-dev/api/context) | Priority-based activity text for the island |
| [Media API](/plugin-dev/api/media) | Now-playing sources, cover art, timeline, and controls |
| [I18n API](/plugin-dev/api/i18n) | Plugin translation bundles |
| [Host State API](/plugin-dev/api/host-state) | Media and theme snapshots and change notifications |
| [Widget API](/plugin-dev/api/widget) | Grid widgets and validated draw lists |
| [Lyrics Transform API](/plugin-dev/api/lyrics-transform) | Parsed lyric-line transformation |
| [Settings API](/plugin-dev/api/settings) | Declarative plugin settings page |
| [Text API](/plugin-dev/api/text) | Text metrics and host font families |
| [Image API](/plugin-dev/api/image) | Decoded, uploaded, and album-art image handles |
| [Store API](/plugin-dev/api/store) | Plugin-scoped persistent byte values |
| [Log API](/plugin-dev/api/log) | Plugin-tagged diagnostic messages |

## Which APIs work together?

- **A custom now-playing widget:** read [Host State](/plugin-dev/api/host-state), fetch artwork through [Image](/plugin-dev/api/image), optionally measure a title with [Text](/plugin-dev/api/text), then draw it through [Widget](/plugin-dev/api/widget). A widget does not automatically receive the song or the image; you supply the drawing commands.
- **A setting that survives restart:** create controls through [Settings](/plugin-dev/api/settings), write accepted values through [Store](/plugin-dev/api/store), and read those values when recreating the page. Settings describes the UI; Store holds the saved bytes.
- **A controllable media source:** publish it through [Media](/plugin-dev/api/media) with declared controls and an `on_command` callback. The simple SDK `create_source` helper publishes metadata without controls.

## Shared ABI rules

`PluginDescriptorV2.capabilities` must include the matching `CAP_*` bit for every service except Log. A successful table query alone does not grant access. The host rejects stale, foreign, or wrong-kind handles. Borrowed slices and input structures must remain valid until the synchronous call returns; callback data must remain valid until callbacks can no longer run.

The status values are `Ok`, `InvalidArgument`, `StaleHandle`, `CapabilityMissing`, `LimitExceeded`, `UnsupportedVersion`, `IoError`, and `Internal`. For binary output methods, a null buffer with zero capacity can be used to obtain the required byte length; a nonempty result reports `LimitExceeded` until enough capacity is supplied. Consult the method page for exceptions and callback rules.

| If you see… | Check first |
|---|---|
| `CapabilityMissing` | Is the matching `CAP_*` bit in your descriptor? |
| `StaleHandle` | Has the resource been released, or does its ID belong to another token or kind? |
| `InvalidArgument` | Are the structure size, UTF-8 data, flags, lengths, and output pointers valid? |
| `LimitExceeded` | Did you hit a quota, supply too small an output buffer, or try to release a resource during its callback? The method page tells these cases apart. |

The SDK turns these statuses into `sdk::Error` values. It also releases owned resources when their wrappers are dropped. Keep those wrappers in your plugin instance; a local variable dropped at the end of `create` will remove the resource immediately.

These pages describe the current ABI v2 implementation. The [host services overview](/plugin-dev/services) gives a shorter tour, and the [SDK source](https://github.com/WinIslandProject/WinIsland/tree/master/crates/winisland-plugin-api/src) defines the exact Rust layouts.
