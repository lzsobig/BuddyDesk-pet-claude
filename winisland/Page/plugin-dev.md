# Plugin development

WinIsland plugins are Windows DLLs loaded through ABI v2. A plugin asks WinIsland for a service, then uses that service to add content such as activity text, a media source, a widget, or a settings page. The current `winisland-plugin-api` crate is `0.8`; ABI v1 DLLs cannot be loaded by the current host.

> Plugins run inside WinIsland without a sandbox. A panic in an `extern "C"` callback can terminate the app.

## Guides

| Guide | What it covers |
|---|---|
| [Quickstart](/plugin-dev/quickstart) | Build, load, and package an ABI v2 plugin |
| [ABI and lifecycle](/plugin-dev/abi-lifecycle) | Descriptor validation, ownership, callbacks, shutdown, and migration |
| [Host services](/plugin-dev/services) | All eleven service tables, drawing, settings, and limits |
| [API reference](/plugin-dev/api) | One page per public service table, with methods, data contracts, and limits |
| [Packaging and installation](/plugin-dev/packaging) | `plugin.yml`, ZIPs, signing, installation, and updates |
| [API changelog](/api-changelog) | Historical published crate release notes |

See the [SDK README](https://github.com/WinIslandProject/WinIsland/tree/master/crates/winisland-plugin-api) and [ABI definitions](https://github.com/WinIslandProject/WinIsland/tree/master/crates/winisland-plugin-api/src/abi) for exact Rust signatures.

## Start with what you want to build

| I want to… | Start here | What to expect |
|---|---|---|
| Put a short status or alert on the island | [Context API](/plugin-dev/api/context) | Publish text, then update or remove it. |
| Supply a song or playback controls | [Media API](/plugin-dev/api/media) | Publish track data; controls need a command callback. |
| Draw my own content in the expanded island | [Widget API](/plugin-dev/api/widget) | Submit a complete drawing for a grid widget. |
| Add options to WinIsland settings | [Settings API](/plugin-dev/api/settings) and [Store API](/plugin-dev/api/store) | Describe controls and save their values separately. |
| React to the current song or theme | [Host State API](/plugin-dev/api/host-state) | Read a snapshot or subscribe to changes. |
| Change displayed lyric text | [Lyrics Transform API](/plugin-dev/api/lyrics-transform) | Transform parsed lines before display. |

Build the [one-context example](/plugin-dev/quickstart) first if you have not loaded a plugin before. The [API reference](/plugin-dev/api) covers the other services and their exact call contracts.

## Three ideas to keep in mind

1. **Capability:** a bit in the plugin descriptor declaring which service you intend to use. Log is the only service here without a capability bit.
2. **Service table:** the set of functions WinIsland provides for that capability. The SDK wraps common calls; raw tables expose the full API.
3. **Resource:** something you create, such as a context, widget, or settings page. Keep its ID or SDK wrapper while it is needed, then release it before shutdown completes.

The current API adds content through defined extension points. It does not provide a general way to replace arbitrary WinIsland UI, intercept all input, or change the host's internals. In particular, widgets can draw but have no pointer or keyboard callback yet. See each API page for its current boundary.

## Runtime model

```text
DLL exports winisland_plugin_entry_v2() -> static PluginDescriptorV2
    -> host validates ABI, capabilities, callbacks, and metadata
    -> host calls create(PluginCreateInfoV2) with token and PluginHostV2
    -> plugin queries versioned service tables and creates resources
    -> optional descriptor.on_tick runs on a plugin worker
    -> widget submits a complete draw list; host validates and replays it
    -> host calls shutdown(handle), then destroy(handle), then unloads DLL
```

`PluginDescriptorV2.capabilities` declares access to services. Every resource belongs to a host-issued `PluginToken`. Service tables use `PluginHostV2.query` and `IFACE_VERSION_1`, a separate version from `ABI_VERSION_2`.

| Capability | Table | Purpose |
|---|---|---|
| `CAP_CONTEXT` | `ContextApiV2` | Activity text |
| `CAP_MEDIA` | `MediaApiV2` | Now-playing source, cover, and controls |
| `CAP_I18N` | `I18nApiV2` | Translation bundles |
| `CAP_HOST_STATE` | `HostStateApiV2` | Media/theme snapshot and subscriptions |
| `CAP_WIDGET` | `WidgetApiV2` | Widgets and draw-list submission |
| `CAP_LYRICS` | `LyricsTransformApiV2` | Parsed lyric transforms |
| `CAP_SETTINGS` | `SettingsApiV2` | Declarative settings pages |
| `CAP_TEXT` | `TextApiV2` | Text measurement and font families |
| `CAP_IMAGE` | `ImageApiV2` | Images and current album art |
| `CAP_STORE` | `StoreApiV2` | Plugin-scoped persistent bytes |

`LogApiV2` is available without a capability bit. Declare only what the plugin uses.

## Development flow

1. Create a Rust `cdylib` with the `winisland-plugin-api` dependency shown in the [quickstart](/plugin-dev/quickstart).
2. Export `winisland_plugin_entry_v2` with a static `PluginDescriptorV2`.
3. Validate `PluginCreateInfoV2` in `create` and use SDK `Host::from_raw` or raw service tables.
4. Keep resource handles until `shutdown`; release them while host tables are valid.
5. Stop and join plugin workers before successful `shutdown`; free the opaque instance in `destroy`.
6. Package a ZIP with root-level `plugin.yml`, `abi-version: 2`, and the declared DLL. Drop it onto the island to install or update.

The SDK wraps common calls and builds draw lists. Advanced controls and settings changes use the raw ABI. Plugin drawing does not run on the render thread.

## Compatibility

Crate `0.8`, top-level `ABI_VERSION_2`, and service-table `IFACE_VERSION_1` are different version numbers. Check `struct_size` and `version` before reading a table. ABI v1 DLLs require source migration and repackaging; changing `plugin.yml` alone cannot convert one.
