# Packaging and installation

A distributable ABI v2 plugin is a ZIP with root-level `plugin.yml` and the DLL named by `entry`. Dependency DLLs and assets may also be included. WinIsland loads only the declared entry as a plugin.

Use a root-level DLL only for a quick local run. Use a ZIP when you want to share or update the plugin: the manifest tells WinIsland which DLL to load and which identity/version to show. The [quickstart](/plugin-dev/quickstart) provides a DLL you can package.

## Build with PluginPackager

Enable the packager feature for a small build tool. Use the current repository source until the ABI v2 crate is available from the registry; the package version is `0.8.0`.

```toml
[dev-dependencies]
winisland-plugin-api = { git = "https://github.com/WinIslandProject/WinIsland", features = ["packager"] }

[[example]]
name = "pack"
path = "package.rs"
```

Create `package.rs`:

```rust
use winisland_plugin_api::packager::PluginPackager;

fn main() {
    PluginPackager::from_cargo()
        .expect("read Cargo.toml")
        .build()
        .expect("build plugin ZIP");
}
```

Run `cargo run --example pack` from the plugin project root. The packager runs `cargo build --release --locked`, locates `target/release/<lib-name>.dll`, copies requested assets, generates `plugin.yml` with DLL hashes, optionally signs it, validates the DLL descriptor, and writes `target/<name>-<version>.zip` unless configured otherwise. Commit the plugin's `Cargo.lock` before packaging.

`from_cargo()` reads `package.name`, `version`, `authors` (joined with `:`), `description`, `repository`, optional `package.metadata.winisland.id`/`name`, and `lib.name`. The first matching root icon (`icon.png`, `.jpg`, `.jpeg`, `.webp`) and README (`README.md`, `.markdown`, `.txt`) are included automatically. `icon()`, `readme()`, `include_dir()`, `dll_path()`, and `output()` override these choices.

The descriptor's ID, name, version, author, and description must match the generated manifest exactly. The packager and installer both load the DLL for descriptor validation before activation. Choose a stable ID of 1–63 ASCII letters, digits, underscores, or hyphens.

## Manifest

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

`id`, `name`, `author`, `version`, `description`, `github-link`, `abi-version`, and `entry` are required. The entry must be a single root-level `.dll` filename. Optional `icon` and `readme` are safe relative paths to files in the archive. The packager may add `dll_hashes` and `signature`. WinIsland currently does not enforce a local ZIP's manifest signature, signer identity, or `dll_hashes` during installation. Do not present that optional signature as an installation trust guarantee.

For the quickstart example, the ZIP root should look like this (other assets are optional):

```text
plugin.yml
hello_winisland_plugin.dll
```

The `entry` value refers to the DLL inside the ZIP, not the name of the ZIP or the Cargo package. A DLL nested under another folder will not match this manifest.

## Install and update

Drop the ZIP onto the island while WinIsland is running. The installer validates the archive and manifest, extracts to staging, loads the new DLL for descriptor/metadata validation, stops an existing packaged instance, swaps the directory, and starts the new instance. A failed replacement restores the previous directory and attempts to reload the old plugin. A successful install is available immediately; no restart is required. The Plugins page can enable, disable, and uninstall it.

For manual development, a root-level `.dll` in the plugin directory is loaded on startup without a manifest. Remove a manual DLL with the same plugin ID before installing the ZIP; a packaged update cannot replace that root DLL.

An update uses the same stable plugin ID with a new package version. Keep the manifest metadata in sync with the DLL descriptor; changing only the ZIP filename does not update the plugin's identity or version.

Archive checks include at most 4096 entries, 256 MiB per entry, 512 MiB total uncompressed, and a root `plugin.yml` of at most 1 MiB. The exact `entry` must exist. Symlinks, traversal, absolute or device paths, unsafe Windows names, and case-insensitive collisions are rejected. Failed extraction removes staging data.

## Signatures and marketplace

`PluginPackager::signing_key_env("WINISLAND_PLUGIN_SIGNING_KEY")` or `signing_key_path(...)` adds an Ed25519 signature over the manifest's canonical fields and DLL hash list. A failed key load currently logs a warning and produces an unsigned ZIP; inspect the resulting manifest if signing is required. Never commit private keys.

Marketplace installation has a separate trust path: WinIsland verifies the signed marketplace catalog and the selected package size and SHA-256 against that catalog. Entries with incompatible ABI versions are filtered. A package's own optional `signature` field is not the marketplace catalog signature.

To submit to the marketplace, follow the [marketplace contribution guide](https://github.com/WinIslandProject/PluginMarketplace/blob/main/CONTRIBUTING.md) and confirm its current requirements. The plugin repository and release asset must provide a valid ABI v2 package before it can appear as compatible.

## Inspect and troubleshoot

```powershell
tar -tf target/hello-winisland-plugin-0.1.0.zip
tar -xOf target/hello-winisland-plugin-0.1.0.zip plugin.yml
dumpbin /exports target/release/hello_winisland_plugin.dll
```

Check that the DLL exports `winisland_plugin_entry_v2`, `abi-version` is `2`, `entry` names the root DLL, and all five descriptor metadata fields match. If an update fails, read the installation error: the old package should stay active after a recoverable replacement failure. A shutdown that cannot finish keeps its DLL loaded to protect outstanding callbacks. Test install, update, disable/enable, rollback, and uninstall before distribution.
