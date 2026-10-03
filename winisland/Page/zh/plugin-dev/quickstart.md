# 插件快速开始

本例构建完整的 ABI v2 DLL，发布一条活动状态文字。示例校验宿主输入，持有资源，在 `shutdown` 中释放资源，并在 `destroy` 中释放不透明实例。

加载成功后，WinIsland 会注册标题为“Hello WinIsland”、正文为“ABI v2 plugin is running”的活动状态。它会一直存在，直到禁用插件或关闭 WinIsland；如果此时有更高优先级的内容，岛上可能暂时显示别的内容。

## 前置条件

- Windows 10 2004 或更新版本，或 Windows 11
- 安装 `x86_64-pc-windows-msvc` 目标的稳定版 Rust
- Visual Studio C++ 构建工具和 Windows SDK
- 支持 ABI v2 的 WinIsland

## 创建库

```powershell
cargo new --lib hello-winisland-plugin
cd hello-winisland-plugin
```

使用以下 `Cargo.toml`。在支持 ABI v2 的库发布到注册表前，先使用此处的仓库源码；发布后可改用匹配的 `winisland-plugin-api = "0.8"` 版本。

```toml
[package]
name = "hello-winisland-plugin"
version = "0.1.0"
edition = "2024"
authors = ["Example Author"]
description = "Minimal WinIsland ABI v2 plugin"
repository = "https://github.com/example/hello-winisland-plugin"

[lib]
name = "hello_winisland_plugin"
crate-type = ["cdylib"]

[dependencies]
winisland-plugin-api = { git = "https://github.com/WinIslandProject/WinIsland" }
```

包 ID、名称、版本、作者和描述必须与描述符、安装包清单一致。`repository` 中的网址会成为 `github-link`。

`cdylib` 表示要生成 Windows DLL。`lib.name` 决定 DLL 文件名，`package.name` 是 Cargo 包名；这里 DLL 文件名使用下划线，所以两者不同。

## 实现 `src/lib.rs`

```rust
use std::ffi::c_void;
use winisland_plugin_api::abi::{
    ABI_VERSION_2, CAP_CONTEXT, PluginCreateInfoV2, PluginDescriptorV2,
    PluginHandleV2, PluginStatus,
};
use winisland_plugin_api::sdk::{Host, Resource};
use winisland_plugin_api::PluginMetadataC;

struct Instance {
    context: Option<Resource>,
}

static DESCRIPTOR: PluginDescriptorV2 = PluginDescriptorV2 {
    struct_size: std::mem::size_of::<PluginDescriptorV2>() as u32,
    abi_version: ABI_VERSION_2,
    capabilities: CAP_CONTEXT,
    metadata: PluginMetadataC::new(
        "hello-winisland-plugin",
        "hello-winisland-plugin",
        env!("CARGO_PKG_VERSION"),
        "Example Author",
        "Minimal WinIsland ABI v2 plugin",
    ),
    create: Some(create),
    shutdown: Some(shutdown),
    destroy: Some(destroy),
    on_tick: None,
};

unsafe extern "C" fn create(
    info: *const PluginCreateInfoV2,
    out_handle: *mut PluginHandleV2,
) -> PluginStatus {
    if info.is_null() || out_handle.is_null() {
        return PluginStatus::InvalidArgument;
    }
    // SAFETY: WinIsland supplies a readable create-info header.
    let info = unsafe { &*info };
    if info.struct_size < std::mem::size_of::<PluginCreateInfoV2>() as u32
        || info.abi_version != ABI_VERSION_2
        || info.plugin_token == winisland_plugin_api::PluginToken::INVALID
    {
        return PluginStatus::UnsupportedVersion;
    }
    // SAFETY: The host table remains allocated throughout this instance's lifetime.
    let host = match unsafe { Host::from_raw(info.host_api, info.plugin_token) } {
        Ok(host) => host,
        Err(_) => return PluginStatus::InvalidArgument,
    };
    let context = match host
        .context()
        .and_then(|api| api.create("Hello WinIsland", "ABI v2 plugin is running"))
    {
        Ok(context) => context,
        Err(_) => return PluginStatus::Internal,
    };
    let instance = Box::new(Instance {
        context: Some(context),
    });
    // SAFETY: WinIsland treats this pointer as opaque until destroy.
    unsafe { out_handle.write(Box::into_raw(instance).cast::<c_void>()) };
    PluginStatus::Ok
}

unsafe extern "C" fn shutdown(handle: PluginHandleV2) -> PluginStatus {
    if handle.is_null() {
        return PluginStatus::InvalidArgument;
    }
    // SAFETY: This handle was created above and has not been destroyed.
    let instance = unsafe { &mut *handle.cast::<Instance>() };
    drop(instance.context.take());
    PluginStatus::Ok
}

unsafe extern "C" fn destroy(handle: PluginHandleV2) {
    if !handle.is_null() {
        // SAFETY: WinIsland calls destroy once after successful shutdown.
        unsafe { drop(Box::from_raw(handle.cast::<Instance>())) };
    }
}

/// # Safety
/// WinIsland calls this exported symbol using the ABI v2 entry signature.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn winisland_plugin_entry_v2() -> *const PluginDescriptorV2 {
    &DESCRIPTOR
}
```

`PluginStatus` 是数字状态，不包含错误字符串。需要详细诊断时使用 `LogApiV2`。任何导出的 C 回调都不能让栈展开越过 C 边界。

这里的 `create` 获取 Context 服务，并把返回的 `Resource` 存在 `Instance` 里。这一步很关键：如果资源只放在局部变量中，`create` 结束时它就会被丢弃，文字随即消失。`shutdown` 在宿主 API 仍可用时释放资源，`destroy` 最后释放实例内存。

## 构建并加载

```powershell
cargo check
cargo clippy -- -D warnings
cargo build --release
```

DLL 位于 `target/release/hello_winisland_plugin.dll`。正常的 Windows 安装中，WinIsland 插件目录是 `%APPDATA%\WinIsland\plugins`。本地试运行时，先关闭 WinIsland，把 DLL 复制到该目录，再启动应用：

```powershell
$pluginDir = Join-Path $env:APPDATA 'WinIsland\plugins'
New-Item -ItemType Directory -Force -Path $pluginDir | Out-Null
Copy-Item .\target\release\hello_winisland_plugin.dll $pluginDir
```

这种根目录 DLL 是没有 `plugin.yml` 的手动安装，启动时加载。可在“插件”页面确认它已启用。安装同 ID 的 ZIP 前先移除这个 DLL；打包更新无法替换手动文件。

要分发 ZIP，阅读[打包与安装](/plugin-dev/packaging)。设置 `abi-version: 2`，并让 `entry` 等于 DLL 文件名。WinIsland 运行时也可以直接把 ZIP 拖到岛上。

## 扩展示例

- 在[宿主服务](/plugin-dev/services)中了解媒体、小组件、设置、图片、存储和歌词接口。
- 添加回调或线程前阅读 [ABI 与生命周期](/plugin-dev/abi-lifecycle)。
- [SDK 小组件示例](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/examples/minimal_widget.rs)展示了 `DrawListBuilder` 的使用。

## 看不到效果时

| 现象 | 先检查 |
|---|---|
| “插件”页面找不到插件 | DLL 是否在插件目录根部、是否为 64 位 Windows 构建、是否导出 `winisland_plugin_entry_v2`？复制后要重启。 |
| 找到了，但没有启用 | 在“插件”页面启用；仍失败时查看 WinIsland 日志中的加载错误。 |
| 已启用，但文字没出现 | 可能有其他更高优先级的内容；确认 `create` 成功，且 `Resource` 一直保存在 `Instance` 中。 |
| ZIP 安装拒绝 DLL | 按[打包指南](/plugin-dev/packaging)核对 `abi-version: 2`、`entry` 文件名，以及描述符和清单中的五项元数据。 |
