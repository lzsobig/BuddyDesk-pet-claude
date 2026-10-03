# Settings API

`SettingsApiV2` contributes one declarative settings page to WinIsland. Declare `CAP_SETTINGS` and query `IFACE_SETTINGS`. SDK helpers can create a simple section or label page; interactive items require the raw table.

## A typical use

Start with a read-only page to confirm the plugin appears in Settings:

```rust
let page = host.settings()?.create_label_page("sample", "Sample settings", "Plugin is ready")?;
// Keep `page` in the plugin instance.
```

For an interactive switch, read its saved value from [Store](/plugin-dev/api/store), put that value in the page data, and create the page with raw `SettingsApiV2`. When `on_change` receives a new value, validate it, save it to Store, and return `Ok` only if you accept it. Settings does not save values automatically. Keep the page key and item keys stable so existing choices can be restored after restart.

## Methods

Each method takes `context, token` first and returns `PluginStatus`.

| Method | Remaining parameters | Result |
|---|---|---|
| `create` | `*const SettingsPageDataV2`, `*mut ResourceId` | Adds a page and writes its ID. |
| `update` | `ResourceId`, `*const SettingsPageDataV2` | Replaces the page while keeping the same page key. |
| `release` | `ResourceId` | Removes the page when no change callback is in flight. |

## Page and items

`SettingsPageDataV2` supplies a stable ASCII `key`, title, optional copied PNG/JPEG/WebP icon, an item array, and optional `on_change`. A page has 1–64 items. Item kinds are section, group start/end, label, switch, select, stepper, and button. Labels and controls go inside a group; groups cannot nest. Interactive item keys must be unique ASCII letters, digits, `_`, or `-`. A switch value is `true` or `false`; a select value must match one of its options; a stepper needs finite value, bounds, and positive step.

The host copies the icon, items, and select options during `create` or `update`. A page with interactive items must supply `on_change`. The callback runs on a plugin worker with `SettingsChangeV2 { key, value }`; button presses send an empty value. Return an error status to reject a change. Persist accepted values with the [Store API](/plugin-dev/api/store), then supply them again when creating the page. Updating or releasing while a callback is in flight returns `LimitExceeded`.

The current quota is one settings page and 2 MiB of page resource bytes per plugin. The icon is limited to 1 MiB. See the [settings example](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/examples/settings_page.rs) and [item types](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/types/v2/settings.rs).

[All plugin APIs](/plugin-dev/api)
