# 插件 API 参考

ABI v2 提供十一张宿主服务表。先按要做的事选择 API，再进对应页面看方法、输入、资源归属和限制。如果还没成功加载过插件，请先做[快速开始](/plugin-dev/quickstart)；只有 `create` 收到宿主和令牌后才能使用这些服务。

每个服务调用都需要传入表中的 `prefix.context` 和宿主签发的 `PluginToken`，并返回 `PluginStatus`。创建的资源归该令牌所有。原始调用通过 `PluginHostV2.query(context, IFACE_*, IFACE_VERSION_1)` 获取服务表，检查表的大小、版本和所需函数槽。SDK 的 `Host` 封装会为便捷方法执行这些检查。

| API | 提供的能力 |
|---|---|
| [Context API](/plugin-dev/api/context) | 按优先级显示活动状态文字 |
| [Media API](/plugin-dev/api/media) | 媒体源、封面、进度和控制 |
| [I18n API](/plugin-dev/api/i18n) | 插件翻译资源 |
| [Host State API](/plugin-dev/api/host-state) | 媒体与主题状态及变化通知 |
| [Widget API](/plugin-dev/api/widget) | 网格小组件和经校验的绘制列表 |
| [Lyrics Transform API](/plugin-dev/api/lyrics-transform) | 已解析歌词的逐行转换 |
| [Settings API](/plugin-dev/api/settings) | 声明式插件设置页 |
| [Text API](/plugin-dev/api/text) | 文字测量和宿主字体族 |
| [Image API](/plugin-dev/api/image) | 解码、上传和封面图片句柄 |
| [Store API](/plugin-dev/api/store) | 插件独立命名空间中的持久化字节数据 |
| [Log API](/plugin-dev/api/log) | 带插件标识的诊断日志 |

## 常见功能要组合哪些 API？

- **自己画“正在播放”小组件：**从 [Host State](/plugin-dev/api/host-state) 读取曲目信息，用 [Image](/plugin-dev/api/image) 取封面，必要时用 [Text](/plugin-dev/api/text) 测量标题，再通过 [Widget](/plugin-dev/api/widget) 绘制。小组件不会自动拿到歌曲或图片，绘制命令要由插件提交。
- **重启后还记得的设置：**用 [Settings](/plugin-dev/api/settings) 添加控件，用户确认修改后用 [Store](/plugin-dev/api/store) 保存，再在创建设置页时读回。Settings 管界面，Store 管保存。
- **带控制按钮的媒体源：**通过 [Media](/plugin-dev/api/media) 发布曲目，并声明按钮、提供 `on_command` 回调。SDK 的简易 `create_source` 只发布基本信息，不提供控制按钮。

## 通用 ABI 规则

除 Log 外，使用服务前必须在 `PluginDescriptorV2.capabilities` 声明对应 `CAP_*`。查到服务表本身并不授予使用权。宿主会拒绝过期、属于其他插件或类型不符的句柄。借用的数据必须保持有效，直到同步调用返回；回调数据必须保持有效，直到回调不可能再运行。

状态值包括 `Ok`、`InvalidArgument`、`StaleHandle`、`CapabilityMissing`、`LimitExceeded`、`UnsupportedVersion`、`IoError` 和 `Internal`。二进制输出方法通常可用空缓冲区和零容量查询所需字节数；非空结果在容量不足时返回 `LimitExceeded`。具体回调规则见各接口页。

| 如果遇到…… | 先检查什么 |
|---|---|
| `CapabilityMissing` | 描述符中是否声明了对应的 `CAP_*`？ |
| `StaleHandle` | 资源是否已释放，或 ID 属于其他令牌、其他资源类型？ |
| `InvalidArgument` | 结构体大小、UTF-8、标记、长度和输出指针是否有效？ |
| `LimitExceeded` | 是否超出数量限制、输出缓冲区太小，或在回调执行期间释放资源？具体含义要看方法页。 |

SDK 会把这些状态转成 `sdk::Error`，并在包装对象被丢弃时释放资源。因此要把包装对象存在插件实例里；如果只放在 `create` 的局部变量里，函数结束后资源就会被移除。

本文档对应当前 ABI v2 实现。[宿主服务概览](/plugin-dev/services)提供简短介绍；精确的 Rust 布局以 [SDK 源码](https://github.com/WinIslandProject/WinIsland/tree/master/crates/winisland-plugin-api/src)为准。
