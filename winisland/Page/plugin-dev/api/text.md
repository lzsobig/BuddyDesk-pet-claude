# Text API

`TextApiV2` measures text using WinIsland's font manager and reads host font-family names. Declare `CAP_TEXT` and query `IFACE_TEXT`. The SDK `host.text()?.measure(text, size, family)` uses weight 400 and upright style; use the raw table for other styles.

## A typical use

Before drawing a title in a [widget](/plugin-dev/api/widget), measure it at the same font size and family you plan to draw. Use the returned width to decide how much room to leave for album art or whether to shorten the title. Measurements are in the host's logical drawing units, so they pair with widget `logical_size()`.

```rust
let metrics = host.text()?.measure("Now playing", 14.0, "Segoe UI")?;
let title_width = metrics.width;
```

This API measures text; it does not render or install a font. Use the measured style again in the draw list to keep layout consistent.

## Methods

Both methods take `context, token` first and return `PluginStatus`.

| Method | Remaining parameters | Result |
|---|---|---|
| `measure` | `Utf8Slice` text, `*const TextStyleV2`, `*mut TextMetricsV2` | Writes width, height, ascent, and descent. |
| `font_family` | `u32` index, byte buffer, capacity, required length output | Copies a host font-family name. |

## Style and output

`TextStyleV2` contains a positive finite `size`, `weight` from 100 to 900, `italic` as 0 or 1, zero `reserved`, and a borrowed UTF-8 `family`. Text is limited to 64 KiB and family to 255 bytes. The returned `TextMetricsV2` values use the host's drawing measurements, so they are suitable for layout before building a [Widget API](/plugin-dev/api/widget) draw list.

For `font_family`, pass an index supported by the host. An invalid index returns `InvalidArgument`. Use the required-length output to size the buffer; a nonempty result and insufficient capacity return `LimitExceeded`.

See the [text types](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/types/v2/mod.rs) and [raw table](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/abi/tables.rs).

[All plugin APIs](/plugin-dev/api)
