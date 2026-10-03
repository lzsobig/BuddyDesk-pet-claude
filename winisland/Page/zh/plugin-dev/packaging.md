# 打包与安装

可分发的 ABI v2 插件是 ZIP，根目录含 `plugin.yml` 及 `entry` 指定的 DLL。也可加入依赖 DLL 和资源。WinIsland 只把指定入口当作插件加载。

根目录 DLL 适合本地快速试运行；要分享或更新插件，就用 ZIP。清单告诉 WinIsland 加载哪个 DLL，以及展示什么插件 ID 和版本。[快速开始](/plugin-dev/quickstart)中的 DLL 可以直接拿来打包。

## 使用 `PluginPackager` 构建

为构建工具启用 `packager` 功能。在支持 ABI v2 的库发布到注册表之前，使用当前仓库源码；包版本为 `0.8.0`。

```toml
[dev-dependencies]
winisland-plugin-api = { git = "https://github.com/WinIslandProject/WinIsland", features = ["packager"] }

[[example]]
name = "pack"
path = "package.rs"
```

创建 `package.rs`：

```rust
use winisland_plugin_api::packager::PluginPackager;

fn main() {
    PluginPackager::from_cargo()
        .expect("read Cargo.toml")
        .build()
        .expect("build plugin ZIP");
}
```

在插件项目根目录运行 `cargo run --example pack`。打包工具执行 `cargo build --release --locked`，寻找 `target/release/<lib-name>.dll`，复制资源，生成带 DLL 哈希值的 `plugin.yml`，按配置签名，校验 DLL 描述符，然后默认写入 `target/<name>-<version>.zip`。打包前应提交插件的 `Cargo.lock`。

`from_cargo()` 读取 `package.name`、`version`、`authors`（以 `:` 连接）、`description`、`repository`、可选的 `package.metadata.winisland.id`/`name` 和 `lib.name`。根目录第一个匹配的图标（`icon.png`、`.jpg`、`.jpeg`、`.webp`）及 README（`README.md`、`.markdown`、`.txt`）会自动加入。可用 `icon()`、`readme()`、`include_dir()`、`dll_path()` 和 `output()` 覆盖默认值。

描述符的 ID、名称、版本、作者和描述必须与生成的清单文件完全一致。打包工具和安装器在激活前都会加载 DLL 校验描述符。ID 应稳定，并且只能使用 1–63 个 ASCII 字母、数字、下划线或连字符。

## 清单文件

```yaml
id: hello-winisland-plugin
name: hello-winisland-plugin
author: Example Author
version: 0.1.0
description: Minimal WinIsland ABI v2 plugin
github-link: https://github.com/example/hello-winisland-plugin
abi-version: 2
entry: hello_winisland_plugin.dll
```

`id`、`name`、`author`、`version`、`description`、`github-link`、`abi-version` 和 `entry` 为必填。入口只能是 ZIP 根目录的单个 `.dll` 文件名。可选的 `icon`、`readme` 必须是归档中安全的相对路径。打包工具还可能添加 `dll_hashes` 与 `signature`。WinIsland 当前安装本地 ZIP 时不会强制校验清单签名、签名者身份或 `dll_hashes`；不能把这个可选签名描述为安装信任保证。

以上面的快速开始示例为例，ZIP 根目录应至少有这些文件（其他资源可选）：

```text
plugin.yml
hello_winisland_plugin.dll
```

`entry` 指向 ZIP 里面的 DLL 文件名，不是 ZIP 名或 Cargo 包名。若 DLL 被放进子目录，上面的清单就找不到它。

## 安装与更新

WinIsland 运行时将 ZIP 拖到岛上。安装器校验归档和清单文件，在暂存目录解压，加载新 DLL 校验描述符与元数据，停止旧的打包插件，切换目录并启动新实例。替换失败时恢复旧目录并尝试重新加载旧插件。成功安装立即生效，无需重启。在“插件”页面可禁用、启用或卸载。

本地开发时，也可以把 `.dll` 放入插件目录根部；这种安装方式没有清单文件，需在启动时加载。同 ID 的手动 DLL 应先移除，打包更新无法替换这个根目录文件。

更新时沿用稳定的插件 ID，并给新包设置新版本。清单中的元数据必须与 DLL 描述符一致；只改 ZIP 文件名不会改变插件身份或版本。

归档最多 4096 项、每项解压后最多 256 MiB、合计最多 512 MiB；根目录 `plugin.yml` 最多 1 MiB。指定 `entry` 必须存在。符号链接、路径穿越、绝对路径、设备路径、不安全 Windows 文件名和忽略大小写后的冲突都会被拒绝。解压失败会清理暂存目录。

## 签名与插件市场

`PluginPackager::signing_key_env("WINISLAND_PLUGIN_SIGNING_KEY")` 或 `signing_key_path(...)` 使用 Ed25519 对清单的规范字段和 DLL 哈希值列表签名。当前密钥加载失败时只记录警告，继续生成未签名 ZIP；若发布流程要求签名，须检查最终清单文件。不要提交私钥。

市场安装有独立的信任路径：WinIsland 校验市场目录签名，并核对所选安装包的大小和 SHA-256。ABI 版本不兼容的目录项会被过滤。包内可选 `signature` 与市场目录签名不是一回事。

提交市场请查看[市场贡献指南](https://github.com/WinIslandProject/PluginMarketplace/blob/main/CONTRIBUTING.md)，并核实其当前要求。插件仓库与发布附件必须先提供有效的 ABI v2 包，才能作为兼容项出现。

## 检查与排障

```powershell
tar -tf target/hello-winisland-plugin-0.1.0.zip
tar -xOf target/hello-winisland-plugin-0.1.0.zip plugin.yml
dumpbin /exports target/release/hello_winisland_plugin.dll
```

检查 DLL 是否导出准确的 `winisland_plugin_entry_v2`，`abi-version` 是否为 `2`，`entry` 是否指向根目录 DLL，以及描述符的五项元数据是否一致。更新失败时查看安装错误：可恢复的替换失败应继续运行旧包。无法完成 `shutdown` 的 DLL 会保持加载，以保护仍在执行的回调。发布前验证安装、更新、禁用/启用、回滚及卸载。
