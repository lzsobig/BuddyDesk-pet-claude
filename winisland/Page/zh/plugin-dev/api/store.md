# Store API

`StoreApiV2` 在 WinIsland 重启后仍保留插件独立的字节数据。声明 `CAP_STORE` 并查询 `IFACE_STORE`。SDK 提供 `host.store()?.get(key)`、`set(key, bytes)` 和 `delete(key)`。

## 一个常见用法

要记住一项设置，就在 `create` 时读取；键不存在时使用默认值；用户修改后再写入。Store 保存的是字节，不知道这些字节表示文字、JSON 还是布尔值。插件需自己选定编码方式，并一直使用同一套规则。

```rust
let store = host.store()?;
let show_seconds = store.get("show-seconds")?.as_deref() == Some(&b"true"[..]);
store.set("show-seconds", b"true")?;
```

`None` 表示从未保存；`Some(Vec::new())` 表示键存在，只是值为空。删除键会回到“不存在”的状态。通过这个 API，每个插件只访问自己的键空间。

## 方法

所有方法先接收 `context, token`，并返回 `PluginStatus`。

| 方法 | 其余参数 | 作用 |
|---|---|---|
| `get` | `Utf8Slice` 键、字节缓冲区、容量、所需长度输出、是否存在输出 | 读取字节或报告键不存在。 |
| `set` | `Utf8Slice` 键、`ByteSlice` 值 | 写入或替换值。 |
| `delete` | `Utf8Slice` 键 | 删除值；键不存在时也返回 `Ok`。 |

## 键与读取方式

键必须为非空 UTF-8 字符串，最长 255 字节。值可以是任意字节，也可以为空；每个值最多 1 MiB。宿主将数据存于插件 ID 对应目录；通过此 API，插件无法访问其他插件的 Store 值。

键不存在时，`get` 写入 `found = 0`、`required = 0`。对于非空值，先用零容量查询长度，分配 `required` 字节后再读取。缓冲区不足时第一次调用返回 `LimitExceeded`。两次调用间值可能变化，因此仍需处理第二次容量错误。SDK 对不存在的键返回 `None`，对存在的键返回 `Some(Vec<u8>)`。

参见[原始服务表](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/abi/tables.rs)和[SDK 实现](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/sdk/resources.rs)。

[返回 API 目录](/plugin-dev/api)
