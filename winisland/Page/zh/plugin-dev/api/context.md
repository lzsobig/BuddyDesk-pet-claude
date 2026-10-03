# Context API

`ContextApiV2` 向灵动岛发布活动或提醒文字。声明 `CAP_CONTEXT` 并查询 `IFACE_CONTEXT`。SDK `host.context()?.create(title, body)` 创建默认中优先级状态；优先级、超时和紧凑文字需要使用原始服务表。

## 一个常见用法

做计时器时，开始时创建一条状态，时间变化时更新同一个 ID，结束时释放。做短暂的“完成”提醒时，可通过原始服务表设置 `timeout_ms`，到时停止显示；资源之后仍需释放。SDK 返回的 `Resource` 要存在插件实例里；丢弃它就会移除文字。

```rust
let status = host.context()?.create("计时器", "运行中")?;
// 把 status 保存在插件实例中，直到计时结束。
```

SDK 便捷方法没有更新接口。文字变化时用原始 `update`；反复 `create` 会占用更多状态名额。

## 方法

下表参数均排在通用的 `context, token` 之后，所有方法返回 `PluginStatus`。

| 方法 | 其余参数 | 作用 |
|---|---|---|
| `create` | `*const ContextDataV2`、`*mut ResourceId` | 发布状态并写入资源 ID。 |
| `update` | `ResourceId`、`*const ContextDataV2` | 替换内容并刷新更新时间。 |
| `release` | `ResourceId` | 移除状态。 |

## 数据约定

`ContextDataV2` 包含 `struct_size`、`priority`、`flags`、`timeout_ms`、`title`、`body` 和 `compact_text`。优先级分别为 `PRIORITY_LOW`（播放）、`PRIORITY_MEDIUM`（活动）、`PRIORITY_HIGH`（提醒）。`CONTEXT_FLAG_SHOW_COMPACT` 控制紧凑显示。超时为零时，状态会持续到释放；`title` 不得为空；`compact_text` 为空时回退到标题。

固定缓冲区最多容纳 255 字节标题、511 字节正文和 127 字节紧凑文字，另留 NUL 终止符。宿主只接受已知优先级和标记。内容变化时更新现有资源即可。每个插件当前最多拥有 64 个 Context。

参见[快速开始示例](/plugin-dev/quickstart)和[数据类型定义](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/types/v2/context.rs)。

[返回 API 目录](/plugin-dev/api)
