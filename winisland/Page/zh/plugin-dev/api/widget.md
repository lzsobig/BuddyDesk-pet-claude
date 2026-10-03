# Widget API

`WidgetApiV2` 创建网格小组件并接收完整绘制列表。声明 `CAP_WIDGET` 并查询 `IFACE_WIDGET`。SDK 提供 `host.widgets()?.create(WidgetSpec::new("key").span(2, 1))`、`Widget` 句柄及 `DrawListBuilder`。

## 一帧是怎么画出来的

小组件创建一次即可，把 `Widget` 对象存在插件实例中。内容变化时先读 `logical_size()`，按这个尺寸画好**整帧**，再提交。只提交变化的文字不够，因为新列表会替换上一帧。稳定的 `key` 对应用户设置的布局位置，发布新版本时也应保持不变。

```rust
let (width, height) = widget.logical_size();
if width > 0.0 && height > 0.0 {
    let mut list = DrawListBuilder::new(Size::new(width, height));
    list.fill_round_rect(
        Rect::new(0.0, 0.0, width, height),
        8.0,
        Rgba::from_argb(0x8000_0000),
    );
    widget.submit(list.finish())?;
}
```

此处假设 `widget` 是 SDK 的 `Widget`，并已导入 SDK 绘制类型。[完整示例](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/examples/minimal_widget.rs)还画了文字和封面。`request_redraw` 是请求重画已有帧；画面内容变了，要提交新列表。

## 方法

所有方法先接收 `context, token`，并返回 `PluginStatus`。

| 方法 | 其余参数 | 作用 |
|---|---|---|
| `create` | `*const WidgetSpecV2`、`*mut WidgetId` | 注册小组件并写入 ID。 |
| `update` | `WidgetId`、`*const WidgetSpecV2` | 替换小组件配置。 |
| `release` | `WidgetId` | 移除小组件。 |
| `submit_draw_list` | `WidgetId`、字节指针、字节长度 | 复制一帧完整绘制数据，稍后校验。 |
| `request_redraw` | `WidgetId` | 标记需要重绘。 |
| `logical_size` | `WidgetId`、宽度输出、高度输出 | 读取当前逻辑绘制尺寸。 |

## 配置与绘制

`WidgetSpecV2` 包含 `span_cols`、`span_rows`、`flags`、`title`、`body`、稳定的 `key` 和最小尺寸。行列跨度分别为 1–4；尺寸必须为非负有限值。目前唯一的标记是 `WIDGET_FLAG_SHOW_COMPACT`。稳定键用于跨重启保留布局位置。

用 `DrawListBuilder::new(Size::new(width, height))` 新建完整列表，加入绘制命令，再提交 `finish()`。协议支持裁剪、变换、透明度、形状、渐变、描边、阴影、图片和文字。布局前读取 `logical_size`；SDK 查询失败时返回 `(0, 0)`。即使灵动岛正在收起，逻辑尺寸仍由展开网格确定。

提交成功只代表宿主复制了字节；宿主稍后校验、准备，并在网格区域内裁剪重放。单份列表最多 4 MiB、4096 条命令；反复提交错误帧可能禁用小组件。每个插件当前最多有 8 个小组件。`PluginDescriptorV2.on_tick` 在插件工作线程运行，可用于生成新帧。当前 Widget API 没有鼠标或键盘事件回调。

参见[小组件示例](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/examples/minimal_widget.rs)和[绘制协议](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/draw/v2.rs)。

[返回 API 目录](/plugin-dev/api)
