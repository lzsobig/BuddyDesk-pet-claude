# Host State API

`HostStateApiV2` 读取当前媒体和主题状态，也可订阅变化。声明 `CAP_HOST_STATE` 并查询 `IFACE_HOST_STATE`。SDK 提供 `host.host_state()?.get()`；订阅使用原始服务表。

## 一个常见用法

显示当前歌曲的小组件可以调用 `get()`，拿到标题和播放状态后生成绘制列表。如果还要跟随状态变化，用原始 `subscribe` 注册回调，并保留订阅 ID 与回调数据。同时先调用 `get` 取得初始状态；订阅用于接收后续通知。释放回调数据前先解除订阅。

```rust
let state = host.host_state()?.get()?;
// 用 state.media_title 和 state.is_playing 绘制下一帧。
```

## 方法

所有方法先接收 `context, token`，并返回 `PluginStatus`。

| 方法 | 其余参数 | 作用 |
|---|---|---|
| `get` | `*mut HostStateV2` | 写入当前状态快照。 |
| `subscribe` | `HostStateChangedFnV2`、回调数据、`*mut ResourceId` | 注册变化回调并写入订阅 ID。 |
| `release_subscription` | `ResourceId` | 没有进行中的回调时移除订阅。 |

## 快照与回调

`HostStateV2` 包含 `media_title`、`media_artist`、`is_playing` 和 `theme`（`light` 或 `dark`）；`flags` 和 `reserved` 字节保留供后续使用。回调收到借用的 `*const HostStateV2`，调用结束后仍需使用的数据应先复制。保持 `callback_data` 有效，直到订阅安全释放。回调进行期间释放会返回 `LimitExceeded`。

每个插件当前最多订阅 16 次。此 API 只观察宿主状态，没有修改主题或媒体播放器的方法。

参见[快照类型](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/types/v2/context.rs)和[回调签名](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/types/v2/mod.rs)。

[返回 API 目录](/plugin-dev/api)
