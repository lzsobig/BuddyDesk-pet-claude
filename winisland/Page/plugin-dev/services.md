# Host services

ABI v2 exposes eleven versioned service tables through `PluginHostV2.query`. This page is a tour; the [API reference](/plugin-dev/api) documents each table's methods and data contract. The SDK `Host` wrapper covers common operations; the raw tables in `winisland_plugin_api::abi` expose every function. Each raw table starts with `TablePrefix` and currently uses `IFACE_VERSION_1`. Validate required function slots before calling them. Except for Log, declare the matching `CAP_*` bit in `PluginDescriptorV2`.

Think of a service as an entry point into one part of WinIsland. A capability bit says your plugin needs it; querying the table gives you its functions; calling `create` or `register` gives you an owned resource. Keep the returned SDK object or raw ID for as long as the content should exist.

| Capability | Raw table | SDK access | Main operations |
|---|---|---|---|
| `CAP_CONTEXT` | `ContextApiV2` | `host.context()?` | Create, update, release activity text |
| `CAP_MEDIA` | `MediaApiV2` | `host.media()?` | Publish a media source and read current title |
| `CAP_I18N` | `I18nApiV2` | `host.i18n()?` (query only) | Register and release translation bundles |
| `CAP_HOST_STATE` | `HostStateApiV2` | `host.host_state()?` | Read or subscribe to media/theme state |
| `CAP_WIDGET` | `WidgetApiV2` | `host.widgets()?` | Create, update, release, draw, and size widgets |
| `CAP_LYRICS` | `LyricsTransformApiV2` | `host.lyrics()?` | Register/release a lyric transformer |
| `CAP_SETTINGS` | `SettingsApiV2` | `host.settings()?` | Create/update/release a settings page |
| `CAP_TEXT` | `TextApiV2` | `host.text()?` | Measure text and query font family |
| `CAP_IMAGE` | `ImageApiV2` | `host.images()?` | Decode, upload, use album art, release |
| `CAP_STORE` | `StoreApiV2` | `host.store()?` | Get, set, delete plugin-scoped bytes |
| None | `LogApiV2` | `host.log()` | Write plugin log messages |

## Context and Media

`ContextDataV2` has a priority, compact flag, timeout, title, body, and compact text. Zero timeout keeps it until release. Update the same resource rather than creating a new one on each refresh. The SDK's `host.context()?.create(title, body)` returns an owned `Resource`.

Use Context for a short-lived message such as “Export complete” or a persistent activity such as “Timer running.” Use Media when the plugin itself supplies the active track. `MediaSourceDataV2` carries title, artist, album, duration/position in milliseconds, playing flag, optional PNG/JPEG cover bytes, declared controls, and an optional command callback. The SDK `create_source(title, artist)` publishes metadata without controls; use `MediaApiV2` directly for cover, timeline, or controls. Releasing or disabling a plugin media source lets WinIsland fall back to another source or SMTC. Keep callback data valid until release is safe.

## Widget drawing

`host.widgets()?.create(WidgetSpec::new("key").span(2, 1))` creates a layout-managed widget. Stable keys identify placement across restarts. `Widget::logical_size()` returns the current logical dimensions; skip a frame if it returns `(0, 0)`. The size follows the expanded grid even while the island collapses.

Build a complete list with `DrawListBuilder::new(Size::new(width, height))`, add commands such as `fill_round_rect`, `text`, `text_runs`, or `image`, then call `widget.submit(list.finish())`. The draw protocol supports clips, transforms, alpha, shapes, gradients, strokes, shadows, images, and UTF-8 text with a font-family field. The host copies the list and validates it before replay. Submission success does not guarantee display; malformed frames can eventually disable that widget. No plugin callback runs on the render thread.

The draw list is limited to 4 MiB, 4096 commands, and 64 KiB of text per command. `Widget::request_redraw` is best effort. `PluginDescriptorV2.on_tick` receives `WidgetId` and elapsed seconds on a plugin worker.

## Lyrics, i18n, and Host State

A lyric transformer runs after lyrics are parsed. It uses a size query and then a write pass. Preserve the same Unicode character count on word-synchronised lines to keep timing boundaries. The SDK `host.lyrics()?.register` accepts a `Send + Sync` transformation closure and retains its callback storage while registered.

`I18nApiV2` registers a language-tagged bundle of key/value pairs. `HostStateApiV2.get` returns media title, artist, playing state, and light/dark theme. `subscribe` registers a callback; release the subscription before unloading.

## Settings, Text, Image, Store, and Log

`SettingsApiV2` accepts a declarative `SettingsPageDataV2` with a stable page key, title, optional icon, and items: section, group, label, switch, select, stepper, and button. Its `on_change` callback can accept or reject a user action. SDK `create_label_page` creates a simple label page; use the raw table for interactive items and callbacks. Persist values explicitly with Store, then repopulate item values on create.

`TextApiV2.measure` accepts `TextStyleV2` with size, weight, italic flag, and UTF-8 font family; `font_family` reports host families. The SDK `measure` convenience call uses weight 400 and upright style. `ImageApiV2` can decode PNG/JPEG/WebP, upload RGBA pixels, or capture current album art; image IDs remain owned until release. A captured album-art handle keeps its image after the cover changes.

`StoreApiV2` stores bytes under plugin-local keys across restarts; a value is limited to 1 MiB. `LogApiV2.write` uses a numeric level and has no capability gate. SDK `LogApi::write` and `Widget::request_redraw` discard errors; use raw tables if the status matters.

For a setting such as “show seconds,” read its Store value during `create`, put that value into the Settings page, and update Store after `on_change` accepts a new choice. Recreating the page alone does not persist the choice. For a widget that shows the song title, combine Host State or Media with Text/Image and Widget; Widget does not supply content on its own.

## Resource limits and errors

Current per-plugin resource limits are 64 Contexts, 4 Media sources (32 MiB total), 16 i18n bundles (4 MiB), 8 Widgets (4 MiB), 4 lyric transformers, 1 Settings page (2 MiB), 64 Images (64 MiB), and 16 Host State subscriptions. The host rejects stale or foreign handles and quota overflows using `PluginStatus`. Releases should occur before successful shutdown; the host revokes remaining resources afterward.
