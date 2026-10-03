use crate::utils::settings_ui::content_height;
use crate::utils::settings_ui::items::SettingsItem;

use super::{
    CONNECTION_PAGE_INDEX, PET_PAGE_INDEX, PREFERENCES_PAGE_INDEX, SETTINGS_HEADER_H, SettingsApp,
    VOICE_PAGE_INDEX,
};

impl SettingsApp {
    pub(crate) fn build_current_items(&self) -> Vec<SettingsItem> {
        match self.active_page {
            0 => self.build_general_items(),
            1 => self.build_music_items(),
            2 => self.build_widget_items(),
            3 => self.build_plugin_items(),
            CONNECTION_PAGE_INDEX | VOICE_PAGE_INDEX | PREFERENCES_PAGE_INDEX => {
                vec![SettingsItem::RowLabel {
                    label: winisland_core::i18n::tr("buddy_settings_connecting"),
                }]
            }
            PET_PAGE_INDEX => self.build_pet_items(),
            page if page == self.about_page_index() => self.build_about_items(),
            _ => self.build_plugin_settings_items(),
        }
    }

    pub(crate) fn rebuild_items_cache(&mut self) {
        self.cached_items = self.build_current_items();
        let switch_states: Vec<bool> = self
            .cached_items
            .iter()
            .filter_map(|item| match item {
                SettingsItem::RowSwitch { on, .. } => Some(*on),
                _ => None,
            })
            .collect();
        let switch_context = (self.active_page, 0);
        if self.switch_anim_context != switch_context
            || self.switch_anim.len() != switch_states.len()
        {
            self.switch_anim = crate::utils::settings_ui::SwitchAnimator::new(&switch_states);
            self.switch_anim_context = switch_context;
        } else {
            self.switch_anim.set_targets(&switch_states);
        }
        self.cached_content_height = content_height(&self.cached_items, SETTINGS_HEADER_H);
        let view_h = self.logical_window_size().1;
        self.cached_max_scroll = (self.cached_content_height - view_h + 20.0).max(0.0);
        self.items_dirty = false;
    }

    pub(crate) fn ensure_items_cache(&mut self) {
        if self.items_dirty {
            self.rebuild_items_cache();
        }
    }

    pub(crate) fn mark_items_dirty(&mut self) {
        self.items_dirty = true;
    }
}
