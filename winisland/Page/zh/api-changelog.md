# API 更新日志

此更新日志列出 `winisland-plugin-api` 各版本的变更。网站将此文件显示为插件 API 更新日志。

## 0.8.0 - 2026 年 9 月 27 日

变更：

- **不兼容变更**：将原生 ABI v1 入口替换为 `winisland_plugin_entry_v2` 和 `PluginDescriptorV2`；ABI v1 DLL 必须重新构建，并使用 `abi-version: 2` 打包
- 将 `PluginResultC` 替换为 `PluginStatus`，并将可选的 `on_tick` 移至插件描述符
- 将渲染线程上的小组件回调替换为完整绘制列表，由插件工作线程提交、宿主校验并重放，重放时不进入插件代码
- 更新 `PluginPackager`，使其生成 ABI v2 清单，并在生成 ZIP 前校验构建出的 DLL 描述符
- 将 `winisland-plugin-api` 及其可发布依赖 `winisland-plugin-package` 的许可证声明为 GPL-3.0-only

新增：

- 十一种带版本号的宿主接口，分别用于活动状态文字、媒体、国际化、宿主状态、小组件、歌词转换、设置、文字、图片、存储和日志
- 按需启用的 Rust SDK，提供拥有所有权的资源句柄、小组件绘制列表构建器、图片辅助功能、持久化存储操作和简单设置页辅助功能
- 支持裁剪、变换、透明度、形状、渐变、描边、阴影、图片以及显式指定字体族的 UTF-8 文字等绘制列表操作
- 专辑封面访问、丰富的声明式设置项、插件独立命名空间的持久化存储和宿主状态订阅

修复：

- 渲染前对绘制列表进行有界校验，并检查资源所有权
- 在插件关闭失败或部分初始化实例清理失败时，保护 DLL 的生命周期

## 0.7.0 - 2026 年 9 月 13 日

新增：

- `CAPABILITY_SETTINGS` 和 `SettingsApiV1` 宿主服务
- 支持自定义侧边栏图标的声明式插件设置页
- 章节、分组、标签、开关、选择框、步进器和按钮等设置项
- 同步变更回调，支持返回拒绝操作的错误，并由回调控制值的更新

变更：

- 将插件设置页加入设置侧边栏，并在卸载时自动移除
- 设置资源纳入令牌所有权、资源限制和确保回调安全的关闭流程

## 0.6.0 - 2026 年 8 月 24 日

新增：

- `CAPABILITY_LYRICS_TRANSFORM` 和 `LyricsTransformApiV1` 宿主服务
- `LyricsTransformerDataV1` 和分两次调用的 UTF-8 歌词行转换回调
- 包含行时间戳和 `LYRICS_TEXT_FLAG_WORD_SYNCED` 的 `LyricsTextV1`

变更：

- 获取并解析歌词后、宿主缓存歌词前，由已注册的转换器处理一次
- 逐词同步的歌词行保留其时间边界，并拒绝 Unicode 字符数不同的转换结果
- 歌词回调正在执行时，拒绝卸载插件或释放转换器

## 0.5.0 - 2026 年 8 月 14 日

新增：

- 通过 `WidgetDataV1::key` 提供在各插件内保持稳定的小组件键
- 使用这些稳定的键持久化插件小组件的位置，并在设置中控制布局

变更：

- 带键的小组件可在布局编辑器中管理，并在重启后保留位置；仍支持 0.4 版本中不带键的小组件
- 小组件键必须在插件内唯一，匹配 `[a-zA-Z0-9_-]+`，并在创建后保持不变

## 0.4.1 - 2026 年 8 月 14 日

新增：

- 插件安装包清单中的可选字段 `icon` 和 `readme`
- 用于加入插件详情资源的 `PluginPackager::icon()` 和 `PluginPackager::readme()`
- 打包时自动检测根目录下受支持的图标和 README 文件

修复：

- 缺少可选字段 `icon` 和 `readme` 时，旧版安装包的签名校验

## 0.4.0 - 2026 年 8 月 13 日

新增：

- `CAPABILITY_WIDGET` 和 `WidgetApiV1` 宿主服务（创建、更新、释放）
- `WidgetDataV1`：归插件所有的小组件资源，包含网格跨度和渲染回调
- `WidgetDrawContextV1` / `DrawApiV1`：宿主提供的绘制操作，使插件无需链接任何图形库即可在宿主的 Skia 画布上渲染
- 绘制操作：文字、文字测量、矩形、圆角矩形、圆、线段、圆弧、图片，以及插件独立的 `save` / `restore` / `translate` 变换栈
- `WIDGET_FLAG_SHOW_COMPACT`：为未来的迷你岛渲染预留的标记
- `HostApiV1::widget_api()`，用于在 `create` 期间查询小组件服务

变更：

- 小组件在展开的小组件页面中，由渲染线程同步渲染；坐标使用相对于小组件槽位的逻辑坐标，宿主负责应用 `scale`/`alpha`
- `callback_data` 采用与媒体接口相同的不透明 `*mut c_void` 约定
- `DrawApiV1` 接口带有版本号，并通过 `WidgetDrawContextV1::draw_api()` 校验

## 0.3.0 - 2026 年 8 月 9 日

新增：

- 原生 DLL ABI v1，采用描述符入口 `winisland_plugin_entry_v1`
- 用于宿主校验所有权的 `PluginToken` 和 `ResourceId` 标识
- 活动状态文字、媒体、国际化和宿主状态服务的能力声明
- 通过 `HostApiV1::query_interface` 发现带版本号的宿主服务
- 活动状态文字和媒体资源的创建、更新及释放操作
- 可选的媒体控制回调，支持播放/暂停、上一首、下一首和跳转进度命令
- 可释放的翻译资源包，以及包含当前媒体和主题信息的宿主状态快照
- `plugin.yml` 中的 `id`、`abi-version` 和指定单个入口 DLL 的 `entry` 字段
- 打包工具对 Cargo `repository` 和 `[lib].name` 元数据的支持

变更：

- **不兼容变更**：移除 0.2 版本的 `PluginVTable`、`PluginType`、`PluginInstanceC`、`HostApiC`、`plugin_get_instance` 和 `plugin_set_host_api` 接口
- **不兼容变更**：移除尚未完成的 Theme（主题）和 Shortcut（快捷方式）接口
- 插件生命周期严格遵循 `create -> shutdown -> destroy`；WinIsland 仅在 `shutdown` 成功后卸载 DLL
- 活动状态文字的 ID 改为宿主签发的数字资源标识，不再使用插件提供的字符串
- 插件媒体源保持活动状态，不受 SMTC 设置影响，且仅提供已声明的控制功能
- 插件工作线程上的资源变更会唤醒 WinIsland 事件循环
- 开发示例和打包文档改为面向 Rust 2024 和 ABI v1

修复：

- 对描述符大小、ABI 版本、能力、元数据和生命周期回调的校验
- 各插件的资源所有权检查、数量限制和内存限制
- 媒体回调的重入和卸载同步
- 保证 UTF-8 完整性的固定缓冲区截断，以及有界的借用切片复制
- 活动状态文字更新/释放事件的合并，以及媒体跳转进度操作的来源绑定
- 有界的 ZIP 解压，包含暂存、Windows 路径冲突检查、事务式激活、备份和明确的回滚错误
- 插件关闭期间的翻译资源包清理和宿主唤醒请求合并

## 0.2.0 - 2026 年 6 月 19 日

新增：

- `TranslationPairC`：用于插件国际化、可安全通过 FFI 传递的翻译键值对
- `HostApiC::register_translations`：插件在 `on_load` 期间注册翻译；同一个键后注册的翻译会覆盖先注册的翻译
- 国际化覆盖层：`tr()` 优先查询插件注册的翻译，再查询 `.lang` 文件

变更：

- **不兼容变更**：`HostApiC` 增加必填字段 `register_translations`；所有宿主实现都必须提供此回调
- 将 `lib.rs` 拆分为模块文件：`host.rs`、`vtable.rs`、`types/mod.rs`、`types/{metadata,content,context,theme,shortcut,i18n}.rs`
- 从库根模块重新导出所有公开类型，插件作者使用的导入路径保持不变

## 0.1.3 - 2026 年 6 月 19 日

新增：

- `MediaSourceC`：可由插件注入的媒体源，包含标题、艺术家、专辑、时长、进度和封面
- `HostApiC::set_media_source`：使用插件提供的媒体数据替换 SMTC
- `HostApiC::clear_media_source`：恢复以 SMTC 作为当前媒体源

变更：

- 为 `HostApiC` 派生 `Clone`、`Copy`，以便安全地通过 FFI 使用
- 为 `PluginResultC` 派生 `Debug`、`Clone`、`Copy`
- `ContextDataC`、`ContextIdC`、`HostStateC`：新增基于推送的上下文类型
- `PluginVTable::set_host_api`：供插件接收 `HostApiC` 指针的可选函数槽

## 0.1.2 - 2026 年 6 月 17 日

新增：

- README.md，包含库级文档、使用示例和功能开关

## 0.1.1 - 2026 年 6 月 16 日

新增：

- `packager` 功能：通过 `PluginPackager` 构建、签名并将插件打包为 ZIP
- 用于发布到 crates.io 的 Cargo.toml 元数据（仓库、主页、许可证、关键词和分类）
- 启用 `packager` 功能的 `docs.rs` 配置

变更：

- 使用 `str_to_fixed` 辅助函数初始化字节缓冲区，替换手动填充循环
- 打包工具在 `build()` 期间校验 `manifest.yaml`，检查缺失字段和超长缓冲区
- `Manifest` 中的 `github_link` 字段改为必填且不能为空，以满足宿主校验要求

修复：

- `plugin_get_instance` 文档示例使用正确的 `#[no_mangle]` 导出，并移除多余的 `fn main`
- 打包模块文档中的无效链接
- 签名流程中的 `BG_CACHE` 大小检查

## 0.1.0 - 2026 年 6 月 15 日

新增：

- 首次发布，将 C ABI 类型从 WinIsland 宿主中提取为独立的库
- 核心类型：`PluginInstanceC`、`PluginVTable`、`PluginMetadataC`、`IslandContentC`、`ThemeColorsC`、`AnimationConfigC`、`ShortcutC`、`PluginResultC`
- 支持 `from_u32` 转换的 `PluginType` 枚举
- `PluginGetInstanceFn`：插件 DLL 的入口签名
- 用于处理 FFI 字节缓冲区的 `str_to_fixed` / `read_c_str` / `read_opt_c_str` 辅助函数
- 优先级常量：`PRIORITY_LOW`、`PRIORITY_MEDIUM`、`PRIORITY_HIGH`
- 内容标签常量：`ISLAND_CONTENT_TAG_MUSIC`、`ISLAND_CONTENT_TAG_NOTIFICATION`、`ISLAND_CONTENT_TAG_STATUS`
