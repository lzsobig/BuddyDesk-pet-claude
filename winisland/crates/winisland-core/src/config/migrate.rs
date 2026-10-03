use super::AppConfig;

pub const CONFIG_VERSION: u32 = 3;

/// Stamps a config that was loaded as `from_version` with the current version.
///
/// Returns `true` when the config changed and therefore has to be written back.
pub fn migrate(config: &mut AppConfig, from_version: u32) -> bool {
    if from_version >= CONFIG_VERSION {
        return false;
    }
    config.config_version = CONFIG_VERSION;
    config.expanded_height = (config.expanded_height + 60.0).min(1000.0);
    for entry in &mut config.widget_layout {
        if entry.widget == Some(super::WidgetKind::Settings) && entry.slot == 17 {
            entry.widget = None;
        }
    }
    if !config
        .widget_layout
        .iter()
        .any(|entry| entry.widget == Some(super::WidgetKind::Settings))
    {
        config.widget_layout.push(super::WidgetSlot {
            slot: 23,
            widget: Some(super::WidgetKind::Settings),
        });
    }
    if (config.resource_widget_columns, config.resource_widget_rows) == (2, 1) {
        config.resource_widget_rows = 2;
    }
    true
}
