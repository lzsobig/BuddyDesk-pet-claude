use std::cell::OnceCell;

use winisland_render::Image;

use crate::utils::settings_ui::ClickResult;
use crate::utils::settings_ui::items::SettingsItem;
use winisland_core::i18n::tr;

use super::super::SettingsApp;
use super::{PageInput, SettingsPage};

const ABOUT_ICON_SIZE: f32 = 126.0;
const ABOUT_ICON_HEIGHT: f32 = 138.0;
const BUDDYDESK_REPO: &str = "https://github.com/lzsobig/BuddyDesk-pet-claude";
const BUDDYDESK_INTRO: &str = "https://lzsobig.github.io/BuddyDesk-pet-claude/";

thread_local! {
    static ABOUT_ICON: OnceCell<Image> = const { OnceCell::new() };
}

pub(super) fn app_icon() -> Image {
    ABOUT_ICON.with(|icon| {
        icon.get_or_init(|| {
            Image::from_encoded(include_bytes!("../../../../resources/buddydesk-logo.png"))
                .expect("Failed to load about page icon")
        })
        .clone()
    })
}

#[derive(Clone, Copy)]
enum AboutAction {
    Repository,
    Introduction,
}

impl SettingsApp {
    fn build_about_page(&self) -> SettingsPage<AboutAction> {
        let theme = self.theme();
        let mut page = SettingsPage::new();
        page.spacer(20.0);
        page.center_image(app_icon(), ABOUT_ICON_SIZE, ABOUT_ICON_HEIGHT);
        page.center_text("BuddyDesk".to_string(), 28.0, theme.text_pri);
        page.center_text(tr("about_pet_tagline"), 14.0, theme.text_sec);
        page.center_text("v0.3.0".to_string(), 13.0, theme.text_sec);
        page.spacer(12.0);
        page.center_link(
            tr("about_pet_intro"),
            theme.accent,
            AboutAction::Introduction,
        );
        page.center_link(tr("about_pet_repo"), theme.accent, AboutAction::Repository);
        page.spacer(22.0);
        page.center_text(tr("about_native_credit"), 11.0, theme.text_sec);
        page
    }

    pub(crate) fn build_about_items(&self) -> Vec<SettingsItem> {
        self.build_about_page().into_items()
    }

    pub(crate) fn handle_about_click(&self, input: PageInput) {
        let page = self.build_about_page();
        let result = input.hit_test(&page);
        let url = match (page.action(&result), result) {
            (Some(AboutAction::Introduction), ClickResult::CenterLink(_)) => Some(BUDDYDESK_INTRO),
            (Some(AboutAction::Repository), ClickResult::CenterLink(_)) => Some(BUDDYDESK_REPO),
            _ => None,
        };
        if let Some(url) = url
            && let Err(error) = crate::platform::shell().open_url(url)
        {
            log::warn!("Could not open BuddyDesk page: {error}");
        }
    }
}
