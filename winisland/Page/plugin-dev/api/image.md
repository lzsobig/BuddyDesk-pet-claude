# Image API

`ImageApiV2` creates image handles for widget draw lists. Declare `CAP_IMAGE` and query `IFACE_IMAGE`. The SDK exposes `decode`, `upload_rgba`, `album_art`, and an `ImageHandle` that releases its ID on drop.

## A typical use

For a music widget, ask for `album_art()` when the track changes, retain the returned `ImageHandle`, and pass its `id()` to the widget's image drawing command. If no cover is available, `album_art()` returns an error; draw a placeholder instead. Release the old handle when it is no longer referenced by a submitted frame.

```rust
let cover = host.images()?.album_art().ok();
// Keep `cover` while submitted widget frames still use its image ID.
```

For your own PNG/JPEG/WebP asset, call `decode(encoded_bytes)` once and reuse its handle. For generated pixels, call `upload_rgba(width, height, rgba)` with exactly four bytes per pixel. Avoid decoding the same image on every tick: each new handle counts against the image quota.

## Methods

Each method takes `context, token` first and returns `PluginStatus`.

| Method | Remaining parameters | Result |
|---|---|---|
| `decode` | `ByteSlice` encoded image, `*mut ImageId` | Decodes an image and writes its ID. |
| `upload_rgba` | width, height, `ByteSlice` pixels, `*mut ImageId` | Copies RGBA8 pixels into a new image. |
| `album_art` | `*mut ImageId` | Captures the current album art as a handle. |
| `release` | `ImageId` | Releases an owned image. |

## Input and lifetime

`decode` accepts encoded image bytes up to 16 MiB; an undecodable image returns `InvalidArgument`. `upload_rgba` requires nonzero dimensions no larger than 4096 × 4096 and exactly `width × height × 4` bytes. The host copies borrowed bytes during the call. `album_art` returns `IoError` when no cover is available; the returned handle retains its image after the active cover changes.

Image IDs are plugin-owned. Use one in a `DRAW_IMAGE` or related draw-list command, then release it after no submitted frame needs it. The current quota is 64 image handles and 64 MiB of decoded RGBA resource bytes per plugin.

See the [raw table](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/abi/tables.rs) and [widget example](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/examples/minimal_widget.rs).

[All plugin APIs](/plugin-dev/api)
