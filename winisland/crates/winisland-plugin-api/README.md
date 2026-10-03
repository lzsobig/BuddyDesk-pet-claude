# winisland-plugin-api

ABI v2 types and SDK for trusted native WinIsland plugins. Plugins are in-process Windows DLLs. The published ABI layouts and opcodes are defined in `src/abi`, `src/types/v2`, and `src/draw/v2.rs`.

License: GPL-3.0-only.

## Start a plugin

Create a Rust `cdylib` with `winisland-plugin-api` as a dependency. Export `winisland_plugin_entry_v2` returning a static `PluginDescriptorV2`. The descriptor declares capabilities and `create`, `shutdown`, and `destroy` callbacks. `on_tick` is optional and belongs to the plugin descriptor.

```toml
[lib]
crate-type = ["cdylib"]

[dependencies]
winisland-plugin-api = "0.8"
```

The host passes a plugin token and an instance-owned `PluginHostV2` table to `create`. Query service tables through the SDK `Host` wrapper or through `PluginHostV2.query_interface`. The eleven interfaces cover context, media, translations, host state, widgets, lyrics, settings, text, images, store, and logging. Each resource belongs to the plugin token that created it.

## Lifecycle and drawing

The host calls `create`, then optional `on_tick` on a plugin worker. The plugin builds a complete ABI v2 draw list and submits it through the widget table. WinIsland validates the entire list before replaying it with the render crate; render callbacks do not enter plugin code. `shutdown` must stop and join plugin-owned threads before returning success. The host then calls `destroy` and unloads the DLL. If shutdown fails, including cleanup after a partial `create`, the DLL and its host service tables remain allocated until process exit. The host cannot detect a plugin that returns success while its own threads are still running.

Borrowed strings and byte slices are valid only for the synchronous call that receives them. Callback data must remain valid until its resource is released and no callback is active. Service methods return `PluginStatus`; stale or foreign resource handles are rejected.

The SDK wraps common calls; the ABI tables in `src/abi` expose the full interface. `Host::from_raw` requires the host table and token passed to `create`, and the wrapper must not outlive plugin shutdown. Query methods on `Host` return an error when a capability or table is unavailable. The returned handles may be used from plugin-owned threads while the instance is active.

| SDK method | Behavior and lifetime |
|---|---|
| `ContextApi::create`, `MediaApi::create_source`, `LyricsApi::register`, `SettingsApi::create_page` / `create_label_page`, `WidgetApi::create` | Return an owned resource on success; the handle releases it on drop. `LyricsApi::register` retains its callback until release is safe; if release fails, the callback allocation is retained to avoid a dangling callback pointer. |
| `Widget::submit` | Copies a complete draw list into the host and returns its status. Validation and frame preparation happen later; a successful submit does not guarantee that the frame will be displayed. |
| `Widget::logical_size` | Returns the current logical dimensions. It returns `(0, 0)` if the host call fails; the plugin should skip drawing that frame. The size follows the configured expanded grid and does not shrink during collapse animation. |
| `Widget::request_redraw`, `LogApi::write` | Best-effort convenience calls that discard host errors. Use the raw ABI table when the status matters. |
| `TextApi::measure` | Measures with weight 400 and upright style in the requested family. Use the raw `TextApiV2` table for other weights or italic text. |
| `ImageApi::decode`, `upload_rgba`, `album_art` | Return an owned image handle, released on drop. An album-art handle keeps its image after the current cover changes. |
| `StoreApi::get`, `set`, `delete` | Operate in the plugin's own persistent namespace. `get` returns `None` for an absent key and may report a size error if the value changes between its length query and read. |

The settings helpers create only a section label. Rich settings items and change callbacks require the raw `SettingsApiV2` table. `WidgetSpec::new` and `title` copy into fixed ABI buffers and truncate long UTF-8 text at a character boundary; choose keys within the 63-byte ASCII limit. The ABI types in `src/abi` define the exact signatures; the host enforces threading, quotas, and failure statuses.

## Package

A package is a ZIP containing `plugin.yml` and the DLL named by its `entry` field. Set `abi-version: 2`. The optional `packager` feature provides `PluginPackager` for building, signing, and zipping a plugin:

```toml
[dev-dependencies]
winisland-plugin-api = { version = "0.8", features = ["packager"] }
```

```rust,no_run
winisland_plugin_api::packager::PluginPackager::from_cargo()
    .unwrap()
    .build()
    .unwrap();
```
