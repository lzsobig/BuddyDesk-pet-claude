# ABI and lifecycle

ABI v2 is a native, in-process contract. Only C-compatible values, sized structures, opaque handles, and borrowed byte ranges cross the boundary. The host cannot make an invalid native pointer safe; the plugin must keep every pointer valid for its documented lifetime.

In everyday terms: WinIsland loads your DLL, calls `create` once to start an instance, calls its registered callbacks while it runs, then asks `shutdown` to stop it and `destroy` to free it. The DLL must stay loaded until all plugin code and callbacks have finished.

| Stage | Your job | Host behavior |
|---|---|---|
| Entry | Return a stable descriptor. | Checks metadata, ABI, capabilities, and callbacks. |
| `create` | Validate input, create an instance, retain resources and callback data. | Gives the instance a token and service tables. |
| Running | Update or submit content; handle callbacks. | Owns scheduling and validates resources and drawings. |
| `shutdown` | Stop your threads and release resources; return `Ok` only when safe. | Stops using the instance and revokes remaining resources after success. |
| `destroy` | Free the instance pointer once. | Unloads the DLL after cleanup. |

## Entry and descriptor

Export `winisland_plugin_entry_v2` and return an immutable descriptor that remains live until the DLL unloads:

```rust
/// # Safety
/// WinIsland calls this symbol using the ABI v2 entry signature.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn winisland_plugin_entry_v2() -> *const PluginDescriptorV2 {
    &DESCRIPTOR
}
```

`PluginDescriptorV2` contains `struct_size`, `abi_version = ABI_VERSION_2`, capabilities, `PluginMetadataC`, required `create`/`shutdown`/`destroy`, and optional `on_tick`. The host rejects a missing or null entry, short descriptor, wrong ABI, unknown capability bits, missing lifecycle callback, or invalid plugin ID. A packaged DLL's ID, name, version, author, and description must match `plugin.yml`.

## Creation and service lookup

The host gives `create` a `PluginCreateInfoV2` with a nonzero `PluginToken` and an instance-owned `PluginHostV2`. Validate both pointers, `struct_size`, `abi_version`, and token before use. `Host::from_raw(info.host_api, info.plugin_token)` performs host-table checks for SDK users.

Raw callers use `PluginHostV2.query(context, interface_id, IFACE_VERSION_1)`. Every returned table begins with `TablePrefix { struct_size, version, context }`. Validate the prefix and check that each function slot the plugin needs is populated. Declaring a capability permits a service call; merely obtaining a table does not. The log table needs no capability bit.

A successful `create` writes one non-null `PluginHandleV2` and returns `PluginStatus::Ok`. If creation fails with a non-null partial handle, the host calls `shutdown` and then `destroy` if shutdown succeeds. If partial cleanup fails, the DLL and its host tables remain allocated until process exit. Return a null handle when there is no initialized state to clean.

## Resource ownership

`PluginToken`, `ResourceId`, `WidgetId`, and `ImageId` are opaque identities. Each resource belongs to the token that created it; stale, foreign, or wrong-kind handles are rejected. The host copies borrowed request data during synchronous service calls. The SDK's `Resource`, `Widget`, and `ImageHandle` wrappers release resources on drop. Drop them before `shutdown` returns; raw callers must release their IDs explicitly. The host revokes leftovers after successful shutdown.

`PluginStatus` values include `Ok`, `InvalidArgument`, `StaleHandle`, `CapabilityMissing`, `LimitExceeded`, `UnsupportedVersion`, `IoError`, and `Internal`. A successful draw-list submission only confirms copying; validation and rendering occur later.

If a service returns `StaleHandle`, first check whether the resource was already released or its ID belongs to a different plugin or resource kind. If it returns `CapabilityMissing`, check the descriptor bit. `LimitExceeded` can mean a quota, an output buffer that is too small, or an active callback that blocks release; the relevant [API page](/plugin-dev/api) gives the specific rule.

## Tick, callbacks, and shutdown

The host invokes optional `PluginDescriptorV2.on_tick(handle, widget_id, dt_seconds)` on the plugin worker, never on the render thread. Widget drawing is submitted as bytes through `WidgetApiV2.submit_draw_list`. The host validates and replays complete lists. Media commands, host-state notifications, settings changes, and lyric transforms also use host-managed callback dispatch; callback data must remain alive until release is safe. A lyric transform receives a size query followed by a write call, so both passes must agree.

`shutdown` must stop and join every plugin-owned thread, finish callback activity, and release resources before returning `Ok`. Design it to tolerate a retry. `destroy` is called once after successful shutdown and frees the opaque instance. The DLL unloads only after that. If shutdown fails, the host retains the DLL and service tables through process exit. It cannot detect a plugin thread that falsely reports completion.

Release builds use aborting panics. A panic inside a plugin C callback can terminate the process. On the next start, WinIsland detects an active-plugin marker, disables the named plugin, and shows a recovery notice. It cannot keep the first process alive after such a panic.

## FFI rules

- Use the ABI's `#[repr(C)]` types and exact callback signatures. Never pass Rust `String`, `Vec`, references, trait objects, or unwinding panics across the boundary.
- Fixed metadata buffers are NUL-terminated UTF-8. `Utf8Slice` and `ByteSlice` are borrowed pointer/length pairs, not C strings.
- Keep borrowed input alive until the synchronous host call returns. Keep callback data alive until no callback can enter it.
- Check `struct_size` and table version before reading fields. Service table version `IFACE_VERSION_1` is separate from top-level `ABI_VERSION_2`.
- Do not retain a host table or callback pointer after successful shutdown.

## Moving from ABI v1

ABI v1 has no compatibility path in the current host. Rebuild source with `winisland-plugin-api` v2 types, export `winisland_plugin_entry_v2`, change capability names to `CAP_*`, replace `PluginResultC` with `PluginStatus`, and submit widget draw lists instead of drawing through a render-thread callback. Put `abi-version: 2` in the new ZIP. Renaming the old DLL or changing only its manifest is insufficient.

## Review checklist

- Descriptor and package metadata match, and only supported capability bits are set.
- All required tables and function slots are checked.
- Resource and callback storage outlives every host call that uses it.
- Draw lists are complete and bounded.
- Plugin threads are joined before successful shutdown.
- Shutdown can be retried; destroy frees the handle exactly once.
- No panic or Rust-owned layout crosses a C boundary.
