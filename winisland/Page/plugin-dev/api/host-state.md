# Host State API

`HostStateApiV2` reads WinIsland's current media and theme snapshot or subscribes to changes. Declare `CAP_HOST_STATE` and query `IFACE_HOST_STATE`. The SDK provides `host.host_state()?.get()`; subscriptions use the raw table.

## A typical use

A widget that shows the current track can call `get()` to obtain the title and playing state, then build its draw list. If it should react whenever the state changes, use raw `subscribe` and retain the subscription ID and callback data. Read an initial snapshot with `get` as well; the subscription is for subsequent notifications. Release it before freeing callback data.

```rust
let state = host.host_state()?.get()?;
// Use state.media_title and state.is_playing for the next drawing.
```

## Methods

Each method takes `context, token` first and returns `PluginStatus`.

| Method | Remaining parameters | Result |
|---|---|---|
| `get` | `*mut HostStateV2` | Writes the current snapshot. |
| `subscribe` | `HostStateChangedFnV2`, callback data, `*mut ResourceId` | Registers a callback and writes a subscription ID. |
| `release_subscription` | `ResourceId` | Removes the subscription when no callback is in flight. |

## Snapshot and callback

`HostStateV2` contains `media_title`, `media_artist`, `is_playing`, and `theme` (`light` or `dark`). Its `flags` and `reserved` bytes are reserved. The callback receives a borrowed `*const HostStateV2`; copy anything needed after the call. Keep `callback_data` live until the subscription is safely released. A release attempted during an active callback returns `LimitExceeded`.

The current limit is 16 subscriptions per plugin. This API observes host state; it has no method to change the theme or media player.

See the [snapshot type](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/types/v2/context.rs) and [callback signature](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/types/v2/mod.rs).

[All plugin APIs](/plugin-dev/api)
