# ABI 与生命周期

ABI v2 是进程内原生契约。边界上只传递 C 兼容值、带长度的结构体、不透明句柄和借用字节区间。宿主无法验证任意原生指针是否可读；插件必须保证指针在约定期间有效。

简单说，WinIsland 加载 DLL 后，调用一次 `create` 创建实例；运行中调用已注册的回调；结束时先让 `shutdown` 停止，再由 `destroy` 释放实例。只要插件代码或回调还可能运行，DLL 就不能卸载。

| 阶段 | 插件要做什么 | 宿主会做什么 |
|---|---|---|
| 入口 | 返回一直有效的描述符。 | 校验元数据、ABI、能力位和回调。 |
| `create` | 校验输入，创建实例，保留资源和回调数据。 | 提供实例令牌和服务表。 |
| 运行中 | 更新或提交内容，处理回调。 | 负责调度，校验资源与绘制内容。 |
| `shutdown` | 停止自己的线程并释放资源；安全后才返回 `Ok`。 | 成功后撤销剩余资源。 |
| `destroy` | 只释放一次实例指针。 | 清理完成后卸载 DLL。 |

## 入口和描述符

导出 `winisland_plugin_entry_v2`，返回在 DLL 卸载前始终有效且不变的描述符（`PluginDescriptorV2`）：

```rust
/// # Safety
/// WinIsland 使用 ABI v2 入口签名调用该符号。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn winisland_plugin_entry_v2() -> *const PluginDescriptorV2 {
    &DESCRIPTOR
}
```

`PluginDescriptorV2` 包含 `struct_size`、`abi_version = ABI_VERSION_2`、能力位、`PluginMetadataC`、必需的 `create`/`shutdown`/`destroy` 和可选 `on_tick`。入口缺失或为空、描述符结构体过短、ABI 错误、未知能力位、缺少生命周期回调或插件 ID 无效时，宿主会拒绝加载。打包 DLL 的 ID、名称、版本、作者和描述必须与 `plugin.yml` 相同。

## 创建与服务查询

宿主向 `create` 提供 `PluginCreateInfoV2`，其中有非零 `PluginToken` 和实例专属 `PluginHostV2`。使用前校验两个指针、`struct_size`、`abi_version` 和令牌。SDK 用户可通过 `Host::from_raw(info.host_api, info.plugin_token)` 校验宿主表。

原始 ABI 调用者使用 `PluginHostV2.query(context, interface_id, IFACE_VERSION_1)`。返回的每张表都以 `TablePrefix { struct_size, version, context }` 开头。应校验表头，并确认插件所需的每个函数槽均已填充。声明能力位才允许调用对应服务；拿到服务表本身不授予权限。日志服务没有能力位。

`create` 成功时必须写入非空 `PluginHandleV2`，并返回 `PluginStatus::Ok`。如果失败时留有非空的部分初始化实例，宿主会调用 `shutdown`；若清理成功，再调用 `destroy`。部分初始化实例清理失败时，宿主会保留 DLL 和服务表直到进程退出。没有已初始化状态时应留下空句柄。

## 资源所有权

`PluginToken`、`ResourceId`、`WidgetId` 和 `ImageId` 是不透明标识。资源归创建它的令牌所有；过期、属于其他插件或类型错误的句柄会被拒绝。同步服务调用会复制借用的请求数据。SDK 的 `Resource`、`Widget` 和 `ImageHandle` 在析构时释放资源；应在 `shutdown` 返回前完成析构。原始 ABI 调用者须显式释放 ID。`shutdown` 成功后，宿主撤销剩余资源。

`PluginStatus` 包括 `Ok`、`InvalidArgument`、`StaleHandle`、`CapabilityMissing`、`LimitExceeded`、`UnsupportedVersion`、`IoError` 和 `Internal`。绘制列表提交成功只表示字节已复制，校验与渲染稍后进行。

服务返回 `StaleHandle` 时，先看资源是否已释放，或 ID 是否来自另一个插件、另一种资源；返回 `CapabilityMissing` 时，检查描述符能力位。`LimitExceeded` 可能表示数量超限、输出缓冲区太小，也可能是回调还在运行而暂不能释放；具体规则见对应 [API 页面](/plugin-dev/api)。

## 定时回调与卸载

宿主在插件工作线程调用可选的 `PluginDescriptorV2.on_tick(handle, widget_id, dt_seconds)`，不会在渲染线程调用它。小组件通过 `WidgetApiV2.submit_draw_list` 提交绘制字节；宿主校验并重放完整列表。媒体命令、宿主状态通知、设置变更和歌词转换也由宿主调度；回调数据要保留到安全释放为止。歌词转换先查询输出长度再写入，两次结果必须一致。

`shutdown` 返回 `Ok` 前须停止插件自己的全部线程，并等待其结束，完成回调活动并释放资源。它应支持重试。`destroy` 在 `shutdown` 成功后调用一次，释放不透明实例；之后才卸载 DLL。`shutdown` 失败时，宿主将 DLL 和服务表保留到进程退出。插件错误地声称线程已结束，宿主无法识别。

发布构建使用 `panic = "abort"`。插件 C 回调中的 panic 可能立即终止进程。下次启动时，WinIsland 检查活动插件标记，禁用对应插件并显示恢复提示；首次崩溃无法在原进程内恢复。

## FFI 规则

- 使用 ABI 的 `#[repr(C)]` 类型与精确回调签名。不能跨边界传递 Rust `String`、`Vec`、引用或特征对象，也不能让 panic 的栈展开越过边界。
- 固定元数据缓冲区是 NUL 结尾 UTF-8；`Utf8Slice` 和 `ByteSlice` 是借用的指针/长度对，不是 C 字符串。
- 借用输入须在同步宿主调用结束前保持有效；回调数据须在所有回调均不再访问它之后才能释放。
- 读取字段前检查 `struct_size` 和表版本。服务表 `IFACE_VERSION_1` 与顶层 `ABI_VERSION_2` 不同。
- `shutdown` 成功后不得保留宿主表或回调指针。

## 从 ABI v1 迁移

当前宿主没有 ABI v1 兼容路径。使用 `winisland-plugin-api` v2 类型重建源码，导出 `winisland_plugin_entry_v2`，把能力名改为 `CAP_*`，把 `PluginResultC` 改为 `PluginStatus`，并将渲染线程回调绘制改为提交小组件绘制列表。新 ZIP 的 `abi-version` 应为 `2`。只改旧 DLL 文件名或清单文件不够。

## 审查清单

- 描述符与安装包元数据一致，能力位均受支持。
- 检查所需服务表及函数槽。
- 资源和回调数据在使用它们的全部宿主调用结束前保持有效。
- 绘制列表完整且有长度边界。
- `shutdown` 返回成功前等待插件线程全部结束。
- `shutdown` 可重试；`destroy` 只释放一次句柄。
- C 边界上没有 panic 或 Rust 专属布局。
