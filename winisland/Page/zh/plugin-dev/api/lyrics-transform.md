# Lyrics Transform API

`LyricsTransformApiV2` 注册显示前处理已解析歌词的回调。声明 `CAP_LYRICS` 并查询 `IFACE_LYRICS_TRANSFORM`。SDK `host.lyrics()?.register(|line| ...)` 会管理文字转换闭包的回调存储。

## 一个常见用法

在 `create` 中注册一次转换器，把返回的 `Resource` 存在实例里，`shutdown` 时释放。例如把已知拼写替换成另一种写法：

```rust
let transform = host.lyrics()?.register(|line| line.replace("colour", "Colour"))?;
// 把 transform 保存在插件实例中。
```

这个例子保留了 Unicode 字符数，对逐词同步歌词很重要。SDK 闭包只收到文字，因此最好让所有行的替换都保持字符数不变。若需要区别处理逐词同步行，可用原始回调读取 `LYRICS_TEXT_FLAG_WORD_SYNCED`。

## 方法

两种方法都先接收 `context, token`，并返回 `PluginStatus`。

| 方法 | 其余参数 | 作用 |
|---|---|---|
| `register` | `*const LyricsTransformerDataV2`、`*mut ResourceId` | 注册转换器并写入 ID。 |
| `release` | `ResourceId` | 没有进行中的回调时移除转换器。 |

## 转换回调

`LyricsTransformerDataV2` 必须提供 `on_transform`，保留的 `flags` 必须为零。回调收到 `LyricsTextV2`，包含行时间戳、标记和借用的 UTF-8 文本。每行调用两次：第一次输出指针为空、容量为零，用于查询所需字节数；第二次提供可写缓冲区。两次都要写入 `out_len`，成功时返回 `PluginStatus::Ok`，并保持两次输出一致。

设置 `LYRICS_TEXT_FLAG_WORD_SYNCED` 时，应保留相同的 Unicode 字符数，以维持逐词时间边界。输入文字只在本次回调期间有效。保持 `callback_data` 有效，直到释放成功；回调进行期间释放返回 `LimitExceeded`。每个插件当前最多有 4 个转换器。

参见[歌词示例](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/examples/lyrics_transform.rs)和[回调类型](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/types/v2/lyrics.rs)。

[返回 API 目录](/plugin-dev/api)
