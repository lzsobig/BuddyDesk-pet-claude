# Store API

`StoreApiV2` keeps plugin-scoped byte values across WinIsland restarts. Declare `CAP_STORE` and query `IFACE_STORE`. The SDK provides `host.store()?.get(key)`, `set(key, bytes)`, and `delete(key)`.

## A typical use

To remember a setting, read it during `create`, use a default when the key is absent, then write the new value after the user changes it. Store accepts bytes; it does not know whether they represent text, JSON, or a boolean. Pick an encoding and use it consistently.

```rust
let store = host.store()?;
let show_seconds = store.get("show-seconds")?.as_deref() == Some(&b"true"[..]);
store.set("show-seconds", b"true")?;
```

`None` means no value was saved. `Some(Vec::new())` means a value exists but is empty. Deleting a key resets it to the absent state. Each plugin has its own key space through this API.

## Methods

Each method takes `context, token` first and returns `PluginStatus`.

| Method | Remaining parameters | Result |
|---|---|---|
| `get` | `Utf8Slice` key, byte buffer, capacity, required length output, found output | Reads bytes or reports that the key is absent. |
| `set` | `Utf8Slice` key, `ByteSlice` value | Writes or replaces a value. |
| `delete` | `Utf8Slice` key | Removes a value; an absent key is still `Ok`. |

## Keys and reads

Keys are nonempty UTF-8 strings of at most 255 bytes. Values are arbitrary bytes, including empty values, and are limited to 1 MiB each. The host stores them under a directory scoped to the plugin ID; different plugins cannot address each other's Store values through this API.

`get` writes `found = 0` and `required = 0` for an absent key. For a present nonempty value, call first with zero capacity, allocate `required` bytes, then call again. The first call returns `LimitExceeded` when the buffer is too small. A value can change between the two calls, so handle a second size error. The SDK returns `None` for an absent key and `Some(Vec<u8>)` for a present value.

See the [raw table](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/abi/tables.rs) and [SDK implementation](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/sdk/resources.rs).

[All plugin APIs](/plugin-dev/api)
