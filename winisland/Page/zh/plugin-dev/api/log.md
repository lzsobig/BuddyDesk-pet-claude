# Log API

`LogApiV2` 写入带插件 ID 和版本的诊断消息。查询 `IFACE_LOG` 即可；此服务不要求 `CAP_*`。SDK `host.log().write(level, message)` 是尽力执行的便捷方法。

## 一个常见用法

初始化失败或外部服务不可用时，记录一条便于定位问题的日志。消息尽量简短，写清失败发生在哪一步。只把日志当作辅助信息时，可用 SDK：

```rust
host.log().write(2, "电台媒体源已注册");
```

这里的 `2` 表示信息级别。这个便捷方法会丢弃返回状态；若写日志失败会影响后续流程，应使用原始服务表。日志不会变成岛上的通知；向用户显示活动文字要用 [Context](/plugin-dev/api/context)。

## 方法

`write(context, token, level, message)` 返回 `PluginStatus`。`message` 是最长 64 KiB 的借用 UTF-8 切片。数字级别分别为 `0` 错误、`1` 警告、`2` 信息、`3` 调试、`4` 跟踪。其他值返回 `InvalidArgument`。令牌已停止或撤销时返回 `StaleHandle`。

SDK 便捷方法会丢弃返回状态；需要处理错误时应查询原始 `LogApiV2.write` 函数槽。日志应记录有用的诊断信息，避免写入密钥、私人数据或无限制的大块内容。

参见[原始服务表](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/abi/tables.rs)和[宿主实现](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-host/src/services/log.rs)。

[返回 API 目录](/plugin-dev/api)
