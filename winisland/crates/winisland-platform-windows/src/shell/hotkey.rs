use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::mpsc;

use windows::Win32::UI::Input::KeyboardAndMouse::{
    MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, MOD_SHIFT, MOD_WIN, RegisterHotKey,
};
use windows::Win32::UI::WindowsAndMessaging::{GetMessageW, MSG, WM_HOTKEY};
use winisland_platform::{Hotkey, PlatformError};

const HOTKEY_ID: i32 = 1;

static PRESSES: AtomicU32 = AtomicU32::new(0);
static STARTED: AtomicBool = AtomicBool::new(false);

pub(super) fn register(hotkey: Hotkey) -> Result<(), PlatformError> {
    if !hotkey.key.is_ascii_alphanumeric() {
        return Err(PlatformError::Unavailable("hotkey key"));
    }
    if STARTED.swap(true, Ordering::AcqRel) {
        return Err(PlatformError::backend("A hotkey is already registered"));
    }
    let mut modifiers = MOD_NOREPEAT;
    if hotkey.ctrl {
        modifiers |= MOD_CONTROL;
    }
    if hotkey.alt {
        modifiers |= MOD_ALT;
    }
    if hotkey.shift {
        modifiers |= MOD_SHIFT;
    }
    if hotkey.win {
        modifiers |= MOD_WIN;
    }
    let virtual_key = u32::from(hotkey.key.to_ascii_uppercase());
    let (sender, receiver) = mpsc::channel();
    let spawned = std::thread::Builder::new()
        .name("winisland-hotkey".into())
        .spawn(move || {
            // SAFETY: A null HWND binds the hotkey to this thread's message queue, which this
            // thread owns and pumps below for the rest of the process lifetime.
            let registered = unsafe { RegisterHotKey(None, HOTKEY_ID, modifiers, virtual_key) };
            let succeeded = registered.is_ok();
            let _ = sender.send(registered.map_err(PlatformError::backend));
            if !succeeded {
                return;
            }
            let mut message = MSG::default();
            // SAFETY: `message` is a valid out-pointer and the queue belongs to this thread.
            while unsafe { GetMessageW(&mut message, None, 0, 0) }.as_bool() {
                if message.message == WM_HOTKEY && message.wParam.0 == HOTKEY_ID as usize {
                    PRESSES.fetch_add(1, Ordering::Relaxed);
                }
            }
        });
    let result = spawned
        .map_err(PlatformError::backend)
        .and_then(|_| receiver.recv().map_err(PlatformError::backend)?);
    if result.is_err() {
        STARTED.store(false, Ordering::Release);
    }
    result
}

pub(super) fn poll_presses() -> u32 {
    PRESSES.swap(0, Ordering::Relaxed)
}
