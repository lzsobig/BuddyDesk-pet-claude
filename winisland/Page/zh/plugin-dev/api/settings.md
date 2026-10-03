# Settings API

`SettingsApiV2` 向 WinIsland 添加一页声明式插件设置。声明 `CAP_SETTINGS` 并查询 `IFACE_SETTINGS`。SDK 辅助方法可创建简单章节或标签页；交互设置项需要原始服务表。

## 一个常见用法

先做一页只读内容，确认插件设置页能够出现：

```rust
let page = host.settings()?.create_label_page("sample", "示例设置", "插件已就绪")?;
// 把 page 保存在插件实例中。
```

要做可操作的开关，先从 [Store](/plugin-dev/api/store) 读取旧值，把它填入页面数据，再用原始 `SettingsApiV2` 创建页面。`on_change` 收到新值时，先校验，再写入 Store；接受后才返回 `Ok`。Settings 不会自动保存用户选择。页面键和设置项键应保持稳定，才能在重启后恢复对应值。

## 方法

所有方法先接收 `context, token`，并返回 `PluginStatus`。

| 方法 | 其余参数 | 作用 |
|---|---|---|
| `create` | `*const SettingsPageDataV2`、`*mut ResourceId` | 添加设置页并写入 ID。 |
| `update` | `ResourceId`、`*const SettingsPageDataV2` | 保留页面键并替换页面内容。 |
| `release` | `ResourceId` | 没有进行中的变更回调时移除页面。 |

## 页面与设置项

`SettingsPageDataV2` 包含稳定的 ASCII `key`、标题、可选的 PNG/JPEG/WebP 图标、设置项数组和可选 `on_change`。一页需有 1–64 项。类型包括章节、分组开始/结束、标签、开关、选择、步进器和按钮。标签与控件必须位于分组内，分组不能嵌套。交互项的键须唯一，只能包含 ASCII 字母、数字、`_` 或 `-`。开关值为 `true` 或 `false`；选择值须匹配一个选项；步进器须有有限数值、上下界和正数步长。

宿主在创建或更新时复制图标、设置项与选项。包含交互项的页面必须提供 `on_change`。回调在插件工作线程收到 `SettingsChangeV2 { key, value }`；按钮点击发送空值。返回错误状态可拒绝变更。要跨重启保存设置，请使用 [Store API](/plugin-dev/api/store)，并在创建页面时恢复当前值。回调进行期间更新或释放返回 `LimitExceeded`。

每个插件当前只能有 1 个设置页，页面资源字节上限为 2 MiB；图标最多 1 MiB。参见[设置页示例](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/examples/settings_page.rs)和[设置项类型](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/src/types/v2/settings.rs)。

[返回 API 目录](/plugin-dev/api)
