# Plugin quickstart

This example builds a complete ABI v2 DLL that publishes one context. It validates the host input, keeps the resource alive, releases it during `shutdown`, and frees the opaque instance in `destroy`.

After loading it, WinIsland has an activity named “Hello WinIsland” with the text “ABI v2 plugin is running.” The context stays registered until you disable the plugin or close WinIsland. Other higher-priority content can temporarily take the island's display space.

## Prerequisites

- Windows 10 version 2004 or later, or Windows 11
- Stable Rust with the `x86_64-pc-windows-msvc` target
- Visual Studio C++ build tools and Windows SDK
- A WinIsland build with ABI v2 support

## Create a library

```powershell
cargo new --lib hello-winisland-plugin
cd hello-winisland-plugin
```

Use this `Cargo.toml`. Until an ABI v2 crate is published to the registry, use the repository source shown here. After publication, a matching `winisland-plugin-api = "0.8"` release can replace the Git dependency.

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

The package ID, name, version, author, and description must agree with the descriptor and the packaged manifest. The repository URL supplies `github-link`.

`cdylib` tells Rust to produce a Windows DLL. The `lib.name` value determines the DLL filename, while `package.name` is the Cargo package name. They differ here because DLL filenames use underscores.

## Implement `src/lib.rs`

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

`PluginStatus` is a numeric status; it does not carry an error string. Log diagnostic details through `LogApiV2` when needed. Do not unwind through any exported C callback.

In this example, `create` asks for Context and stores the returned `Resource` in `Instance`. Keeping it there matters: if the `Resource` were only a local variable, Rust would drop it as `create` returned and the text would disappear. `shutdown` drops the resource while the host API is still valid; `destroy` then frees the instance allocation.

## Build and load

```powershell
cargo check
cargo clippy -- -D warnings
cargo build --release
```

The DLL is `target/release/hello_winisland_plugin.dll`. On a normal Windows installation, WinIsland's plugin directory is `%APPDATA%\WinIsland\plugins`. For a quick local run, close WinIsland, copy the DLL into that directory, then start WinIsland again:

```powershell
$pluginDir = Join-Path $env:APPDATA 'WinIsland\plugins'
New-Item -ItemType Directory -Force -Path $pluginDir | Out-Null
Copy-Item .\target\release\hello_winisland_plugin.dll $pluginDir
```

This is a manual installation: the root-level DLL has no `plugin.yml` and loads at startup. Check the Plugins page to confirm it is enabled. Remove that DLL before installing a ZIP with the same plugin ID; a packaged update cannot replace the manual copy.

For a distributable ZIP, follow [Packaging and installation](/plugin-dev/packaging). Set `abi-version: 2` and make `entry` equal to the DLL filename. You can also drop the ZIP onto the island while WinIsland is running.

## Extend the example

- Use [Host services](/plugin-dev/services) for Media, Widgets, Settings, Images, Store, and lyrics.
- Use [ABI and lifecycle](/plugin-dev/abi-lifecycle) before adding callbacks or threads.
- See the [SDK widget example](https://github.com/WinIslandProject/WinIsland/blob/master/crates/winisland-plugin-api/examples/minimal_widget.rs) for `DrawListBuilder` usage.

## If nothing appears

| Symptom | Check |
|---|---|
| Plugin is absent from the Plugins page | Is the DLL in the plugin directory root, built for 64-bit Windows, and exporting `winisland_plugin_entry_v2`? Restart after copying it. |
| Plugin is listed but inactive | Enable it in the Plugins page; check WinIsland's log for the loader error if it still fails. |
| Plugin is active but the text is not visible | Other content may currently have priority. Check that `create` succeeded and that the `Resource` remains stored in `Instance`. |
| ZIP installation rejects the DLL | Check `abi-version: 2`, the `entry` filename, and the five descriptor/manifest metadata fields in [Packaging](/plugin-dev/packaging). |
