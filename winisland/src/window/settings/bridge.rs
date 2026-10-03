use std::fs;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

use crate::platform::{WindowRef, window};

use super::{
    CONNECTION_PAGE_INDEX, PET_PAGE_INDEX, PREFERENCES_PAGE_INDEX, SETTINGS_HEADER_H, SIDEBAR_W,
    SettingsApp, VOICE_PAGE_INDEX, WIDGETS_PAGE_INDEX,
};

fn epoch_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

#[derive(Deserialize)]
struct Request {
    protocol_version: u32,
    id: String,
    issued_at_ms: u64,
    page: String,
}

pub(crate) fn read_settings_request(seen: &mut Option<String>) -> Option<String> {
    let path = dirs::home_dir()?
        .join(".buddydesk")
        .join("winisland")
        .join("native-settings-request.json");
    if path.metadata().ok()?.len() > 4096 {
        return None;
    }
    let request: Request = serde_json::from_slice(&fs::read(path).ok()?).ok()?;
    let now = epoch_ms();
    if request.protocol_version != 1
        || request.id.is_empty()
        || request.id.len() > 128
        || seen.as_ref() == Some(&request.id)
        || request.issued_at_ms > now.saturating_add(1000)
        || now.saturating_sub(request.issued_at_ms) > 15_000
        || !matches!(
            request.page.as_str(),
            "connection" | "voice" | "preferences" | "pet" | "widgets"
        )
    {
        return None;
    }
    *seen = Some(request.id);
    Some(request.page)
}

#[derive(Serialize)]
struct Surface<'a> {
    protocol_version: u32,
    pid: u32,
    hwnd: usize,
    updated_at_ms: u64,
    active: bool,
    page: &'a str,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    dpi: f64,
    is_light: bool,
}

pub(crate) struct SurfacePublisher {
    pub(crate) next_publish: Instant,
    last_page: String,
    last_error: Option<Instant>,
}

impl Default for SurfacePublisher {
    fn default() -> Self {
        Self {
            next_publish: Instant::now(),
            last_page: String::new(),
            last_error: None,
        }
    }
}

impl SurfacePublisher {
    pub(crate) fn publish(
        &mut self,
        target: Option<WindowRef>,
        page: Option<&str>,
        is_light: bool,
        now: Instant,
    ) {
        let page = page.unwrap_or("");
        if now < self.next_publish && page == self.last_page {
            return;
        }
        self.last_page = page.to_string();
        self.next_publish = now + Duration::from_millis(250);
        let target = target.filter(|target| target.is_minimized() != Some(true));
        let hwnd = target
            .and_then(|target| window().native_surface(target.id()))
            .map_or(0, |surface| surface.handle());
        let dpi = target.map_or(1.0, |target| target.scale_factor());
        let position = target
            .and_then(|target| target.outer_position())
            .unwrap_or(winisland_platform::WindowPosition::new(0, 0));
        let size = target.map_or(winisland_platform::WindowSize::new(0, 0), |target| {
            target.inner_size()
        });
        let active = hwnd != 0 && !page.is_empty();
        let surface = Surface {
            protocol_version: 1,
            pid: std::process::id(),
            hwnd,
            updated_at_ms: epoch_ms(),
            active,
            page,
            x: position.x + (SIDEBAR_W as f64 * dpi).round() as i32,
            y: position.y + (SETTINGS_HEADER_H as f64 * dpi).round() as i32,
            width: size
                .width
                .saturating_sub(((SIDEBAR_W + 12.0) as f64 * dpi).round() as u32),
            height: size
                .height
                .saturating_sub(((SETTINGS_HEADER_H + 12.0) as f64 * dpi).round() as u32),
            dpi,
            is_light,
        };
        let result = (|| -> Result<(), String> {
            let home = dirs::home_dir().ok_or("User directory unavailable")?;
            let directory = home.join(".buddydesk").join("winisland");
            fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
            let temp = directory.join(format!("settings-surface-{}.tmp", std::process::id()));
            fs::write(
                &temp,
                serde_json::to_vec(&surface).map_err(|error| error.to_string())?,
            )
            .map_err(|error| error.to_string())?;
            winisland_platform_windows::replace_file(
                &temp,
                &directory.join("settings-surface.json"),
            )
        })();
        if let Err(error) = result
            && self
                .last_error
                .is_none_or(|last| now.duration_since(last) > Duration::from_secs(10))
        {
            log::warn!("Settings surface could not publish: {error}");
            self.last_error = Some(now);
        }
    }
}

impl SettingsApp {
    pub(crate) fn buddy_page(&self) -> Option<&'static str> {
        match self.active_page {
            CONNECTION_PAGE_INDEX => Some("connection"),
            VOICE_PAGE_INDEX => Some("voice"),
            PREFERENCES_PAGE_INDEX => Some("preferences"),
            PET_PAGE_INDEX => Some("pet"),
            _ => None,
        }
    }

    pub(crate) fn select_buddy_page(&mut self, page: &str) {
        let index = match page {
            "connection" => CONNECTION_PAGE_INDEX,
            "voice" => VOICE_PAGE_INDEX,
            "preferences" => PREFERENCES_PAGE_INDEX,
            "pet" => PET_PAGE_INDEX,
            "widgets" => WIDGETS_PAGE_INDEX,
            _ => return,
        };
        self.visit_page(index);
        self.settings_surface.next_publish = Instant::now();
        self.request_redraw();
    }
}
