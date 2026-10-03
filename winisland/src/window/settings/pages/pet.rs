use std::cell::{OnceCell, RefCell};
use std::fs::File;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde::Deserialize;
use serde_json::json;
use winisland_core::i18n::tr;
use winisland_render::Image;

use crate::core::agent::send_settings_command;
use crate::utils::settings_ui::ClickResult;
use crate::utils::settings_ui::items::SettingsItem;

use super::{PageInput, SettingsPage};
use crate::window::settings::{PopupState, SettingsApp};

const MAX_PET_SNAPSHOT_BYTES: u64 = 32 * 1024;
const MAX_VISIBLE_PETS: usize = 11;

thread_local! {
    static PREVIEW_IMAGE: RefCell<Option<(PathBuf, SystemTime, u64, Image)>> = const { RefCell::new(None) };
    static FALLBACK_PET: OnceCell<Image> = const { OnceCell::new() };
}

fn enabled_by_default() -> bool {
    true
}

#[derive(Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
pub(crate) struct PetChoice {
    pub(crate) id: String,
    pub(crate) name: String,
}

#[derive(Clone, Deserialize, PartialEq)]
#[serde(default)]
pub(crate) struct PetSnapshot {
    pub(crate) protocol_version: u32,
    pub(crate) pet_id: String,
    pub(crate) pet_name: String,
    #[serde(default = "enabled_by_default")]
    pub(crate) desktop_enabled: bool,
    #[serde(default = "enabled_by_default")]
    pub(crate) island_enabled: bool,
    pub(crate) roam_enabled: bool,
    pub(crate) idle_path: String,
    pub(crate) available_pets: Vec<PetChoice>,
    #[serde(skip)]
    pub(crate) connected: bool,
}

impl Default for PetSnapshot {
    fn default() -> Self {
        Self {
            protocol_version: 1,
            pet_id: "orange".into(),
            pet_name: "小橘".into(),
            desktop_enabled: true,
            island_enabled: true,
            roam_enabled: false,
            idle_path: String::new(),
            available_pets: Vec::new(),
            connected: false,
        }
    }
}

impl PetSnapshot {
    pub(crate) fn read() -> (Self, Option<SystemTime>) {
        let Some(directory) =
            dirs::home_dir().map(|home| home.join(".buddydesk").join("winisland"))
        else {
            return (Self::default(), None);
        };
        let path = directory.join("pet.json");
        let modified = path
            .metadata()
            .and_then(|metadata| metadata.modified())
            .ok();
        let Some(mut snapshot) = read_limited::<Self>(&path) else {
            return (Self::default(), modified);
        };
        if snapshot.protocol_version != 1 {
            return (Self::default(), modified);
        }
        snapshot.pet_name = clean_label(&snapshot.pet_name, 24);
        if snapshot.pet_name.is_empty() {
            snapshot.pet_name = "小橘".into();
        }
        snapshot
            .available_pets
            .retain(|choice| valid_pet_id(&choice.id));
        snapshot.available_pets.truncate(32);
        for choice in &mut snapshot.available_pets {
            choice.name = clean_label(&choice.name, 24);
        }
        if !snapshot
            .available_pets
            .iter()
            .any(|choice| choice.id == snapshot.pet_id)
            && valid_pet_id(&snapshot.pet_id)
        {
            snapshot.available_pets.push(PetChoice {
                id: snapshot.pet_id.clone(),
                name: snapshot.pet_name.clone(),
            });
        }
        let now_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;
        snapshot.connected = read_limited::<AgentHeartbeat>(&directory.join("state.json"))
            .is_some_and(|state| {
                state.protocol_version == 1
                    && state.pid > 0
                    && state.updated_at_ms <= now_ms.saturating_add(1_000)
                    && now_ms.saturating_sub(state.updated_at_ms) <= 4_000
            });
        (snapshot, modified)
    }

    fn visible_choices(&self) -> Vec<&PetChoice> {
        let mut choices: Vec<_> = self.available_pets.iter().take(MAX_VISIBLE_PETS).collect();
        if let Some(selected) = self
            .available_pets
            .iter()
            .find(|choice| choice.id == self.pet_id)
            && !choices.iter().any(|choice| choice.id == selected.id)
        {
            choices.push(selected);
        }
        choices
    }

    fn preview_image(&self) -> Image {
        let path = Path::new(&self.idle_path);
        if path.is_absolute()
            && matches!(
                path.extension().and_then(|ext| ext.to_str()),
                Some("png" | "webp" | "jpg" | "jpeg")
            )
            && let Ok(metadata) = path.metadata()
            && metadata.is_file()
            && metadata.len() <= 8 * 1024 * 1024
            && let Ok(modified) = metadata.modified()
        {
            if let Some(image) = PREVIEW_IMAGE.with(|cache| {
                cache
                    .borrow()
                    .as_ref()
                    .and_then(|(cached_path, cached_at, cached_len, image)| {
                        (cached_path == path
                            && *cached_at == modified
                            && *cached_len == metadata.len())
                        .then(|| image.clone())
                    })
            }) {
                return image;
            }
            if let Ok(bytes) = std::fs::read(path)
                && let Some(image) = Image::decode(&bytes)
            {
                PREVIEW_IMAGE.with(|cache| {
                    *cache.borrow_mut() =
                        Some((path.to_path_buf(), modified, metadata.len(), image.clone()));
                });
                return image;
            }
        }
        FALLBACK_PET.with(|icon| {
            icon.get_or_init(|| {
                Image::from_encoded(include_bytes!("../../../../resources/buddydesk-cat.png"))
                    .expect("Failed to load pet fallback image")
            })
            .clone()
        })
    }
}

#[derive(Default, Deserialize)]
#[serde(default)]
struct AgentHeartbeat {
    protocol_version: u32,
    pid: u32,
    updated_at_ms: u64,
}

fn read_limited<T: for<'de> Deserialize<'de>>(path: &Path) -> Option<T> {
    let file = File::open(path).ok()?;
    if file.metadata().ok()?.len() > MAX_PET_SNAPSHOT_BYTES {
        return None;
    }
    serde_json::from_reader(file.take(MAX_PET_SNAPSHOT_BYTES + 1)).ok()
}

fn clean_label(value: &str, limit: usize) -> String {
    value
        .chars()
        .filter(|character| !character.is_control())
        .take(limit)
        .collect::<String>()
        .trim()
        .to_string()
}

fn valid_pet_id(id: &str) -> bool {
    id == "orange" || (id.len() == 32 && id.bytes().all(|byte| byte.is_ascii_hexdigit()))
}

#[derive(Clone, Copy)]
enum PetAction {
    Select,
    Name,
    Desktop,
    Island,
    Roam,
    ResetPosition,
    Manage,
}

impl SettingsApp {
    pub(crate) fn refresh_pet_snapshot(&mut self, now: Instant) {
        if now < self.pet_next_refresh {
            return;
        }
        self.pet_next_refresh = now + Duration::from_millis(650);
        let (snapshot, modified) = PetSnapshot::read();
        let same_file = modified == self.pet_last_modified;
        if same_file
            && snapshot.connected
            && self.pet_pending_until.is_some_and(|until| now < until)
        {
            return;
        }
        if !same_file {
            self.pet_last_modified = modified;
            self.pet_pending_until = None;
            self.pet_feedback = None;
        } else if self.pet_pending_until.is_some_and(|until| now >= until) {
            self.pet_pending_until = None;
            self.pet_feedback = Some(tr("pet_change_failed"));
        }
        if snapshot != self.pet_snapshot {
            self.pet_snapshot = snapshot;
            self.mark_items_dirty();
            self.request_redraw();
        }
    }

    fn build_pet_page(&self) -> SettingsPage<PetAction> {
        let mut page = SettingsPage::new();
        let snapshot = &self.pet_snapshot;
        let theme = self.theme();
        page.center_image(snapshot.preview_image(), 76.0, 72.0);
        page.center_text(snapshot.pet_name.clone(), 22.0, theme.text_pri);
        page.section(tr("pet_identity"));
        page.group_start();
        page.row_source(
            tr("pet_select"),
            snapshot
                .visible_choices()
                .iter()
                .map(|choice| (choice.name.clone(), choice.id == snapshot.pet_id))
                .collect(),
            snapshot.connected,
            PetAction::Select,
        );
        page.row_button(
            tr("pet_name"),
            tr("pet_edit"),
            snapshot.connected,
            PetAction::Name,
        );
        page.group_end();
        page.section(tr("pet_presence"));
        page.group_start();
        page.row_switch(
            tr("pet_desktop"),
            snapshot.desktop_enabled,
            snapshot.connected,
            PetAction::Desktop,
        );
        page.row_switch(
            tr("pet_island"),
            snapshot.island_enabled,
            snapshot.connected,
            PetAction::Island,
        );
        page.row_switch(
            tr("pet_roam"),
            snapshot.roam_enabled,
            snapshot.connected && snapshot.desktop_enabled,
            PetAction::Roam,
        );
        page.row_button(
            tr("pet_position"),
            tr("pet_reset"),
            snapshot.connected && snapshot.desktop_enabled,
            PetAction::ResetPosition,
        );
        page.group_end();
        page.section(tr("pet_custom"));
        page.group_start();
        page.row_button(
            tr("pet_import"),
            tr("pet_manage"),
            snapshot.connected,
            PetAction::Manage,
        );
        page.group_end();
        if !snapshot.connected {
            page.row_label(tr("pet_start_app"));
        } else if let Some(message) = &self.pet_feedback {
            page.row_label(message.clone());
        } else if snapshot.available_pets.len() > MAX_VISIBLE_PETS {
            page.row_label(tr("pet_more_choices"));
        }
        page
    }

    pub(crate) fn build_pet_items(&self) -> Vec<SettingsItem> {
        self.build_pet_page().into_items()
    }

    pub(crate) fn handle_pet_click(&mut self, input: PageInput) {
        let page = self.build_pet_page();
        let result = input.hit_test(&page);
        let Some(action) = page.action(&result).copied() else {
            return;
        };
        match (action, result) {
            (PetAction::Select, ClickResult::SourceButton(index)) => {
                let choices = self.pet_snapshot.visible_choices();
                let options = choices.iter().map(|choice| choice.name.clone()).collect();
                let values: Vec<_> = choices.iter().map(|choice| choice.id.clone()).collect();
                let selected = values
                    .iter()
                    .position(|value| value == &self.pet_snapshot.pet_id)
                    .unwrap_or_default();
                let rect = input.popup_button_rect(&page, index, self.scroll_y);
                let (width, height) = self.logical_window_size();
                self.show_popup(PopupState::new(
                    select_pet, rect, options, values, selected, width, height,
                ));
            }
            (PetAction::Desktop, ClickResult::Switch(_)) => {
                self.update_pet_setting("pet_enabled", json!(!self.pet_snapshot.desktop_enabled));
            }
            (PetAction::Island, ClickResult::Switch(_)) => {
                self.update_pet_setting(
                    "pet_island_enabled",
                    json!(!self.pet_snapshot.island_enabled),
                );
            }
            (PetAction::Roam, ClickResult::Switch(_)) => {
                self.update_pet_setting("pet_roam", json!(!self.pet_snapshot.roam_enabled));
            }
            (PetAction::ResetPosition, ClickResult::RowButton(_)) => {
                self.update_pet_setting("pet_position", serde_json::Value::Null);
            }
            (PetAction::Name | PetAction::Manage, ClickResult::RowButton(_)) => {
                self.send_pet_command("open_pet_settings", json!({}));
            }
            _ => {}
        }
    }

    fn send_pet_command(&mut self, action: &str, args: serde_json::Value) -> bool {
        if !self.pet_snapshot.connected {
            self.pet_feedback = Some(tr("pet_start_app"));
            self.mark_items_dirty();
            self.request_redraw();
            return false;
        }
        match send_settings_command(action, args) {
            Ok(()) => {
                self.pet_feedback = None;
                self.pet_next_refresh = std::time::Instant::now();
                self.mark_items_dirty();
                self.request_redraw();
                true
            }
            Err(error) => {
                log::warn!("Pet settings command could not be sent: {error}");
                self.pet_feedback = Some(tr("pet_change_failed"));
                self.mark_items_dirty();
                self.request_redraw();
                false
            }
        }
    }

    pub(crate) fn update_pet_setting(&mut self, key: &str, value: serde_json::Value) {
        if !self.send_pet_command("pet_update", json!({"key": key, "value": value})) {
            return;
        }
        match key {
            "pet_enabled" => {
                self.pet_snapshot.desktop_enabled = value.as_bool().unwrap_or_default()
            }
            "pet_island_enabled" => {
                self.pet_snapshot.island_enabled = value.as_bool().unwrap_or_default();
            }
            "pet_roam" => self.pet_snapshot.roam_enabled = value.as_bool().unwrap_or_default(),
            "pet_id" => {
                if let Some(id) = value.as_str() {
                    self.pet_snapshot.pet_id = id.to_string();
                    if let Some(choice) = self
                        .pet_snapshot
                        .available_pets
                        .iter()
                        .find(|choice| choice.id == id)
                    {
                        self.pet_snapshot.pet_name = choice.name.clone();
                    }
                }
            }
            _ => {}
        }
        self.pet_pending_until = Some(std::time::Instant::now() + Duration::from_secs(2));
        self.mark_items_dirty();
        self.request_redraw();
    }
}

fn select_pet(app: &mut SettingsApp, id: &str) {
    if app
        .pet_snapshot
        .available_pets
        .iter()
        .any(|choice| choice.id == id)
        && app.pet_snapshot.pet_id != id
    {
        app.update_pet_setting("pet_id", json!(id));
    }
}
