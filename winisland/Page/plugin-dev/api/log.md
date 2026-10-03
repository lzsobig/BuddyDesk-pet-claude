# Log API

`LogApiV2` writes diagnostic messages tagged with the plugin's ID and version. Query `IFACE_LOG`; this table has no `CAP_*` requirement. The SDK exposes `host.log().write(level, message)` as a best-effort convenience method.

## A typical use

Log a useful event when setup fails or an external service is unavailable. Keep the message short and give enough context to act on it, such as which step failed. The SDK call is convenient when logging is optional:

```rust
host.log().write(2, "Radio source registered");
```

Here `2` means info. Because this helper discards the status, use the raw table if a failed log write affects your control flow. A log message will not appear as an island notification; use [Context](/plugin-dev/api/context) for user-facing activity text.

## Method

`write(context, token, level, message)` returns `PluginStatus`. `message` is a borrowed UTF-8 slice limited to 64 KiB. The numeric levels are `0` error, `1` warning, `2` info, `3` debug, and `4` trace. Other values return `InvalidArgument`. A stopped or revoked plugin token returns `StaleHandle`.

The SDK convenience method discards the return status. Query the raw `LogApiV2.write` function slot when error handling matters. Log useful diagnostics without including credentials, private data, or unbounded payloads.

See the [raw table](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/abi/tables.rs) and [host implementation](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-host/src/services/log.rs).

[All plugin APIs](/plugin-dev/api)
