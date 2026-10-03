# Text API

`TextApiV2` 使用 WinIsland 的字体管理器测量文字，并读取宿主字体族名称。声明 `CAP_TEXT` 并查询 `IFACE_TEXT`。SDK `host.text()?.measure(text, size, family)` 使用 400 字重和正体；其他样式使用原始服务表。

## 一个常见用法

在[小组件](/plugin-dev/api/widget)中画歌曲标题前，按准备使用的字号和字体测量一次。返回的宽度可用来决定封面要留多少空间，或标题是否需要缩短。测量值使用宿主的逻辑绘制单位，可与小组件的 `logical_size()` 搭配。

```rust
let metrics = host.text()?.measure("正在播放", 14.0, "Segoe UI")?;
let title_width = metrics.width;
```

这个 API 只负责测量，不会画文字或安装字体。生成绘制列表时应使用同样的文字样式，避免测量和实际显示不一致。

## 方法

两种方法都先接收 `context, token`，并返回 `PluginStatus`。

| 方法 | 其余参数 | 作用 |
|---|---|---|
| `measure` | `Utf8Slice` 文字、`*const TextStyleV2`、`*mut TextMetricsV2` | 写入宽、高、上升高度和下降高度。 |
| `font_family` | `u32` 索引、字节缓冲区、容量、所需长度输出 | 复制宿主字体族名称。 |

## 样式与输出

`TextStyleV2` 包含正的有限 `size`、100–900 的 `weight`、0 或 1 的 `italic`、必须为零的 `reserved`，以及借用的 UTF-8 `family`。文字最多 64 KiB，字体族名称最多 255 字节。返回的 `TextMetricsV2` 使用宿主绘制时的测量值，可用于构建 [Widget API](/plugin-dev/api/widget) 绘制列表前的布局。

`font_family` 需要宿主支持的索引。无效索引返回 `InvalidArgument`。用所需长度输出为缓冲区分配空间；非空结果容量不足时返回 `LimitExceeded`。

参见[文字类型](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/types/v2/mod.rs)和[原始服务表](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/abi/tables.rs)。

[返回 API 目录](/plugin-dev/api)
