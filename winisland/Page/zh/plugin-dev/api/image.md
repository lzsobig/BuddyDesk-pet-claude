# Image API

`ImageApiV2` 为小组件绘制列表创建图片句柄。声明 `CAP_IMAGE` 并查询 `IFACE_IMAGE`。SDK 提供 `decode`、`upload_rgba`、`album_art`，以及在丢弃时释放 ID 的 `ImageHandle`。

## 一个常见用法

做音乐小组件时，曲目变化后调用 `album_art()`，保留返回的 `ImageHandle`，并在小组件的图片绘制命令里传入 `id()`。没有封面时会返回错误，这时可以画占位图。已提交的帧不再引用旧图片后，再释放旧句柄。

```rust
let cover = host.images()?.album_art().ok();
// 已提交的小组件帧仍使用图片 ID 时，保留 cover。
```

自己的 PNG/JPEG/WebP 资源可调用一次 `decode(encoded_bytes)`，之后复用句柄。自行生成像素时，使用 `upload_rgba(width, height, rgba)`，每个像素恰好四字节。不要每次 tick 都解码同一张图：每个新句柄都占用图片名额。

## 方法

所有方法先接收 `context, token`，并返回 `PluginStatus`。

| 方法 | 其余参数 | 作用 |
|---|---|---|
| `decode` | `ByteSlice` 编码图片、`*mut ImageId` | 解码图片并写入 ID。 |
| `upload_rgba` | 宽、高、`ByteSlice` 像素、`*mut ImageId` | 复制 RGBA8 像素，创建图片。 |
| `album_art` | `*mut ImageId` | 取得当前封面的图片句柄。 |
| `release` | `ImageId` | 释放所属图片。 |

## 输入与生命周期

`decode` 接收最多 16 MiB 的编码图片；无法解码时返回 `InvalidArgument`。`upload_rgba` 要求宽高大于零且均不超过 4096，像素字节数必须等于 `width × height × 4`。宿主在调用期间复制借用的字节。没有封面时 `album_art` 返回 `IoError`；取得的句柄在当前封面变化后仍保留原图。

图片 ID 属于创建它的插件。可在 `DRAW_IMAGE` 等绘制命令中使用，待提交帧不再需要时释放。每个插件当前最多有 64 个图片句柄，解码后 RGBA 资源字节总量上限为 64 MiB。

参见[原始服务表](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/abi/tables.rs)和[小组件示例](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/examples/minimal_widget.rs)。

[返回 API 目录](/plugin-dev/api)
