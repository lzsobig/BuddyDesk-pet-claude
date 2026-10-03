use crate::utils::color::SettingsTheme;
use crate::utils::settings_ui::settings_color;
use winisland_core::config::{
    ResourceMetricKind, ResourceMetricStyle, WIDGET_GRID_SLOTS, WidgetKind, place_builtin_widget,
    set_resource_widget_span, span_cells,
};
use winisland_core::i18n::tr;
use winisland_render::text::{DrawTextCachedParams, FontManager};
use winisland_render::{Angle, Painter, Point, Radius, Rect, Rgba, StrokeCap};

use super::{PopupState, SettingsApp};
use crate::utils::settings_ui::WidgetEditorMode;

const DIALOG_WIDTH: f32 = 520.0;
const DIALOG_RADIUS: f32 = 14.0;
const DIALOG_PADDING: f32 = 20.0;
const GROUP_RADIUS: f32 = 10.0;
const SIZE_GROUP_TOP: f32 = 74.0;
const SIZE_GROUP_HEIGHT: f32 = 44.0;
const EXPANDED_LIST_TOP: f32 = 132.0;
const COMPACT_LIST_TOP: f32 = 76.0;
const ROW_HEIGHT: f32 = 52.0;
const FOOTER_HEIGHT: f32 = 68.0;
const NAME_LEFT: f32 = 76.0;
const SEGMENT_WIDTH: f32 = 112.0;
const SEGMENT_HEIGHT: f32 = 24.0;
const SWATCH_DIAMETER: f32 = 18.0;
const SWITCH_WIDTH: f32 = 32.0;
const SWITCH_HEIGHT: f32 = 18.0;
const COLORS: [u32; 10] = [
    0x0a84ff, 0x32bef6, 0x30d158, 0xff9f0a, 0xff453a, 0xff375f, 0xaf52de, 0x64d2ff, 0xffffff,
    0x8e8e93,
];
const SIZE_OPTIONS: [(usize, usize); 8] = [
    (1, 1),
    (2, 1),
    (3, 1),
    (1, 2),
    (2, 2),
    (3, 2),
    (1, 3),
    (2, 3),
];

#[derive(Clone, Copy)]
enum EditorControl {
    Done,
    Toggle(usize),
    Bar(usize),
    Ring(usize),
    Color(usize),
    MoveUp(usize),
    MoveDown(usize),
    SizeDropdown,
}

struct RowLayout {
    row: Rect,
    up: Rect,
    down: Rect,
    glyph: Rect,
    style: Rect,
    color: Rect,
    toggle: Rect,
}

impl RowLayout {
    fn new(list: Rect, index: usize) -> Self {
        let row = Rect::from_xywh(
            list.left,
            list.top + index as f32 * ROW_HEIGHT,
            list.width(),
            ROW_HEIGHT,
        );
        let center_y = row.center_y();
        let toggle = Rect::from_xywh(
            row.right - 14.0 - SWITCH_WIDTH,
            center_y - SWITCH_HEIGHT / 2.0,
            SWITCH_WIDTH,
            SWITCH_HEIGHT,
        );
        let color = Rect::from_xywh(
            toggle.left - 18.0 - SWATCH_DIAMETER,
            center_y - SWATCH_DIAMETER / 2.0,
            SWATCH_DIAMETER,
            SWATCH_DIAMETER,
        );
        let style = Rect::from_xywh(
            color.left - 16.0 - SEGMENT_WIDTH,
            center_y - SEGMENT_HEIGHT / 2.0,
            SEGMENT_WIDTH,
            SEGMENT_HEIGHT,
        );
        Self {
            row,
            up: Rect::from_xywh(row.left + 12.0, center_y - 17.0, 18.0, 17.0),
            down: Rect::from_xywh(row.left + 12.0, center_y, 18.0, 17.0),
            glyph: Rect::from_xywh(row.left + 40.0, center_y - 12.0, 24.0, 24.0),
            style,
            color,
            toggle,
        }
    }

    fn bar_segment(&self) -> Rect {
        Rect::from_xywh(
            self.style.left,
            self.style.top,
            self.style.width() / 2.0,
            self.style.height(),
        )
    }

    fn ring_segment(&self) -> Rect {
        Rect::from_xywh(
            self.style.center_x(),
            self.style.top,
            self.style.width() / 2.0,
            self.style.height(),
        )
    }
}

impl SettingsApp {
    fn resource_editor_metrics(&self) -> &[winisland_core::config::ResourceMetricConfig] {
        match self.widget_editor_mode {
            WidgetEditorMode::Expanded => &self.config.resource_metrics,
            WidgetEditorMode::Compact => &self.config.compact_resource_metrics,
        }
    }

    fn resource_editor_metrics_mut(
        &mut self,
    ) -> &mut Vec<winisland_core::config::ResourceMetricConfig> {
        match self.widget_editor_mode {
            WidgetEditorMode::Expanded => &mut self.config.resource_metrics,
            WidgetEditorMode::Compact => &mut self.config.compact_resource_metrics,
        }
    }

    fn resource_editor_list_top(&self) -> f32 {
        match self.widget_editor_mode {
            WidgetEditorMode::Expanded => EXPANDED_LIST_TOP,
            WidgetEditorMode::Compact => COMPACT_LIST_TOP,
        }
    }

    fn resource_editor_rect(&self) -> Rect {
        let (window_width, window_height) = self.logical_window_size();
        let width = DIALOG_WIDTH.min(window_width - 28.0);
        let desired_height = self.resource_editor_list_top()
            + self.resource_editor_metrics().len() as f32 * ROW_HEIGHT
            + FOOTER_HEIGHT;
        let height = desired_height.min(window_height - 28.0);
        Rect::from_xywh(
            (window_width - width) / 2.0,
            (window_height - height) / 2.0,
            width,
            height,
        )
    }

    fn resource_editor_list_rect(&self, dialog: Rect) -> Rect {
        Rect::from_xywh(
            dialog.left + DIALOG_PADDING,
            dialog.top + self.resource_editor_list_top(),
            dialog.width() - DIALOG_PADDING * 2.0,
            self.resource_editor_metrics().len() as f32 * ROW_HEIGHT,
        )
    }

    fn resource_editor_control(&self, x: f32, y: f32) -> Option<EditorControl> {
        let dialog = self.resource_editor_rect();
        let point = Point::new(x, y);
        if !dialog.contains(point) {
            return None;
        }
        if done_button(dialog).contains(point) {
            return Some(EditorControl::Done);
        }
        if self.widget_editor_mode == WidgetEditorMode::Expanded
            && resource_size_button(dialog).contains(point)
        {
            return Some(EditorControl::SizeDropdown);
        }
        let list = self.resource_editor_list_rect(dialog);
        for index in 0..self.resource_editor_metrics().len() {
            let layout = RowLayout::new(list, index);
            if !layout.row.contains(point) {
                continue;
            }
            return if layout.up.contains(point) {
                Some(EditorControl::MoveUp(index))
            } else if layout.down.contains(point) {
                Some(EditorControl::MoveDown(index))
            } else if layout.toggle.contains(point) {
                Some(EditorControl::Toggle(index))
            } else if layout.bar_segment().contains(point) {
                Some(EditorControl::Bar(index))
            } else if layout.ring_segment().contains(point) {
                Some(EditorControl::Ring(index))
            } else if layout.color.contains(point) {
                Some(EditorControl::Color(index))
            } else {
                None
            };
        }
        None
    }

    pub(crate) fn resource_editor_control_at(&self, x: f32, y: f32) -> bool {
        self.resource_editor_control(x, y).is_some()
    }

    pub(crate) fn handle_resource_editor_click(&mut self, x: f32, y: f32) {
        let dialog = self.resource_editor_rect();
        let Some(control) = self.resource_editor_control(x, y) else {
            if !dialog.contains(Point::new(x, y)) {
                self.resource_editor_open = false;
                self.request_redraw();
            }
            return;
        };
        match control {
            EditorControl::Done => self.resource_editor_open = false,
            EditorControl::Toggle(index) => {
                if let Some(metric) = self.resource_editor_metrics_mut().get_mut(index) {
                    metric.enabled = !metric.enabled;
                }
            }
            EditorControl::Bar(index) => {
                if let Some(metric) = self.resource_editor_metrics_mut().get_mut(index) {
                    metric.style = ResourceMetricStyle::Bar;
                }
            }
            EditorControl::Ring(index) => {
                if let Some(metric) = self.resource_editor_metrics_mut().get_mut(index) {
                    metric.style = ResourceMetricStyle::Ring;
                }
            }
            EditorControl::Color(index) => {
                if let Some(metric) = self.resource_editor_metrics_mut().get_mut(index) {
                    let current = COLORS.iter().position(|color| *color == metric.color);
                    metric.color =
                        COLORS[current.map_or(0, |position| position + 1) % COLORS.len()];
                }
            }
            EditorControl::MoveUp(index) if index > 0 => {
                self.resource_editor_metrics_mut().swap(index, index - 1);
            }
            EditorControl::MoveDown(index) if index + 1 < self.resource_editor_metrics().len() => {
                self.resource_editor_metrics_mut().swap(index, index + 1);
            }
            EditorControl::MoveUp(_) | EditorControl::MoveDown(_) => {}
            EditorControl::SizeDropdown => self.open_resource_size_popup(),
        }
        crate::ui::widget::resource_usage::set_configs(
            &self.config.resource_metrics,
            &self.config.compact_resource_metrics,
        );
        crate::core::persistence::save_config(&self.config);
        self.mark_items_dirty();
        self.request_redraw();
    }

    fn open_resource_size_popup(&mut self) {
        let dialog = self.resource_editor_rect();
        let selected = SIZE_OPTIONS
            .iter()
            .position(|size| {
                *size
                    == (
                        self.config.resource_widget_columns,
                        self.config.resource_widget_rows,
                    )
            })
            .unwrap_or(0);
        let options: Vec<_> = SIZE_OPTIONS
            .iter()
            .map(|(columns, rows)| format!("{columns} × {rows}"))
            .collect();
        let values: Vec<_> = SIZE_OPTIONS
            .iter()
            .map(|(columns, rows)| format!("{columns}x{rows}"))
            .collect();
        let (window_width, window_height) = self.logical_window_size();
        self.show_popup(PopupState::new(
            select_resource_size,
            resource_size_button(dialog),
            options,
            values,
            selected,
            window_width,
            window_height,
        ));
    }

    fn resize_resource_widget(&mut self, columns: usize, rows: usize) {
        let span = set_resource_widget_span(columns, rows);
        self.config.resource_widget_columns = span.0;
        self.config.resource_widget_rows = span.1;
        let Some(current_anchor) = self.config.widget_layout.iter().find_map(|entry| {
            (entry.widget == Some(WidgetKind::ResourceUsage)).then_some(entry.slot)
        }) else {
            return;
        };
        let settings_slot =
            self.config.widget_layout.iter().find_map(|entry| {
                (entry.widget == Some(WidgetKind::Settings)).then_some(entry.slot)
            });
        let current = span_cells(current_anchor, span)
            .first()
            .copied()
            .unwrap_or(current_anchor);
        let target = std::iter::once(current)
            .chain(0..WIDGET_GRID_SLOTS)
            .find(|candidate| {
                let cells = span_cells(*candidate, span);
                cells.first() == Some(candidate)
                    && !settings_slot.is_some_and(|slot| cells.contains(&slot))
            })
            .unwrap_or(current);
        place_builtin_widget(
            &mut self.config.widget_layout,
            &mut self.config.plugin_widget_layout,
            &self.plugin_widgets,
            WidgetKind::ResourceUsage,
            target,
        );
    }

    pub(crate) fn draw_resource_editor(
        &self,
        painter: Painter<'_>,
        theme: &SettingsTheme,
        win_w: f32,
        win_h: f32,
    ) {
        if !self.resource_editor_open {
            return;
        }
        painter.fill_rect(
            Rect::from_xywh(0.0, 0.0, win_w, win_h),
            Rgba::from_argb(96, 0, 0, 0),
        );
        let dialog = self.resource_editor_rect();
        draw_sheet(painter, dialog, theme);

        draw_text(
            painter,
            &tr(match self.widget_editor_mode {
                WidgetEditorMode::Expanded => "resource_editor_title_expanded",
                WidgetEditorMode::Compact => "resource_editor_title_compact",
            }),
            dialog.left + DIALOG_PADDING,
            dialog.top + 36.0,
            17.0,
            true,
            settings_color(theme.text_pri),
        );
        draw_text(
            painter,
            &tr("resource_editor_hint"),
            dialog.left + DIALOG_PADDING,
            dialog.top + 56.0,
            12.0,
            false,
            settings_color(theme.text_sec),
        );

        if self.widget_editor_mode == WidgetEditorMode::Expanded {
            let group = size_group(dialog);
            draw_group(painter, group, theme);
            draw_text(
                painter,
                &tr("resource_size"),
                group.left + 14.0,
                group.center_y() + 4.5,
                13.0,
                false,
                settings_color(theme.text_pri),
            );
            let button = resource_size_button(dialog);
            draw_raised_control(painter, button, 7.0, theme);
            draw_text(
                painter,
                &format!(
                    "{} × {}",
                    self.config.resource_widget_columns, self.config.resource_widget_rows
                ),
                button.left + 11.0,
                button.center_y() + 4.0,
                12.0,
                false,
                settings_color(theme.text_pri),
            );
            draw_popup_chevrons(painter, button.right - 14.0, button.center_y(), theme);
        }

        let list = self.resource_editor_list_rect(dialog);
        let metrics = self.resource_editor_metrics();
        draw_group(painter, list, theme);
        for (index, metric) in metrics.iter().enumerate() {
            let layout = RowLayout::new(list, index);
            let center_y = layout.row.center_y();
            if index > 0 {
                painter.fill_rect(
                    Rect::from_xywh(
                        layout.row.left + NAME_LEFT,
                        layout.row.top,
                        layout.row.width() - NAME_LEFT,
                        1.0,
                    ),
                    settings_color(theme.separator),
                );
            }
            draw_stepper(
                painter,
                &layout,
                index > 0,
                index + 1 < metrics.len(),
                theme,
            );
            let accent = rgb(metric.color);
            draw_style_glyph(
                painter,
                layout.glyph,
                metric.style,
                if metric.enabled {
                    accent
                } else {
                    settings_color(theme.disabled)
                },
                theme,
            );
            draw_text(
                painter,
                metric_name(metric.kind),
                layout.row.left + NAME_LEFT,
                center_y + 4.5,
                13.0,
                true,
                settings_color(if metric.enabled {
                    theme.text_pri
                } else {
                    theme.disabled
                }),
            );
            draw_segmented(painter, &layout, metric.style, theme);
            draw_swatch(painter, layout.color, accent, theme);
            draw_switch(painter, layout.toggle, metric.enabled, theme);
        }

        let done = done_button(dialog);
        painter.fill_round_rect(done, Radius::uniform(7.0), settings_color(theme.accent));
        draw_centered_text(
            painter,
            &tr("resource_editor_done"),
            done,
            13.0,
            true,
            Rgba::WHITE,
        );
    }
}

fn metric_name(kind: ResourceMetricKind) -> &'static str {
    match kind {
        ResourceMetricKind::Cpu => "CPU",
        ResourceMetricKind::Ram => "RAM",
        ResourceMetricKind::Gpu => "GPU",
        ResourceMetricKind::Network => "NET",
        ResourceMetricKind::Disk => "DISK",
    }
}

fn is_dark(theme: &SettingsTheme) -> bool {
    theme.text_pri.r() > 128
}

fn size_group(dialog: Rect) -> Rect {
    Rect::from_xywh(
        dialog.left + DIALOG_PADDING,
        dialog.top + SIZE_GROUP_TOP,
        dialog.width() - DIALOG_PADDING * 2.0,
        SIZE_GROUP_HEIGHT,
    )
}

fn resource_size_button(dialog: Rect) -> Rect {
    let group = size_group(dialog);
    Rect::from_xywh(
        group.right - 10.0 - 104.0,
        group.center_y() - 12.0,
        104.0,
        24.0,
    )
}

fn done_button(dialog: Rect) -> Rect {
    Rect::from_xywh(
        dialog.right - DIALOG_PADDING - 80.0,
        dialog.bottom - DIALOG_PADDING - 28.0,
        80.0,
        28.0,
    )
}

fn select_resource_size(app: &mut SettingsApp, value: &str) {
    let Some((columns, rows)) = value.split_once('x') else {
        return;
    };
    let (Ok(columns), Ok(rows)) = (columns.parse::<usize>(), rows.parse::<usize>()) else {
        return;
    };
    app.resize_resource_widget(columns, rows);
}

fn draw_sheet(painter: Painter<'_>, dialog: Rect, theme: &SettingsTheme) {
    for (offset, spread) in [(14.0, 6.0), (4.0, 1.0)] {
        painter.fill_round_rect(
            Rect::from_xywh(
                dialog.left - spread,
                dialog.top + offset - spread,
                dialog.width() + spread * 2.0,
                dialog.height() + spread * 2.0,
            ),
            Radius::uniform(DIALOG_RADIUS + spread),
            settings_color(theme.shadow),
        );
    }
    painter.fill_round_rect(
        dialog,
        Radius::uniform(DIALOG_RADIUS),
        settings_color(theme.win_bg),
    );
    painter.stroke_round_rect(
        dialog,
        Radius::uniform(DIALOG_RADIUS),
        1.0,
        settings_color(theme.popup_border),
    );
}

fn draw_group(painter: Painter<'_>, rect: Rect, theme: &SettingsTheme) {
    painter.fill_round_rect(
        rect,
        Radius::uniform(GROUP_RADIUS),
        settings_color(theme.group_bg),
    );
    painter.stroke_round_rect(
        rect,
        Radius::uniform(GROUP_RADIUS),
        1.0,
        settings_color(theme.group_border),
    );
}

fn draw_raised_control(painter: Painter<'_>, rect: Rect, radius: f32, theme: &SettingsTheme) {
    painter.fill_round_rect(
        Rect::from_xywh(rect.left, rect.top + 0.5, rect.width(), rect.height()),
        Radius::uniform(radius),
        settings_color(theme.shadow),
    );
    painter.fill_round_rect(
        rect,
        Radius::uniform(radius),
        if is_dark(theme) {
            settings_color(theme.control_hover)
        } else {
            Rgba::WHITE
        },
    );
    painter.stroke_round_rect(
        rect,
        Radius::uniform(radius),
        0.75,
        settings_color(theme.control_border),
    );
}

fn draw_popup_chevrons(painter: Painter<'_>, x: f32, y: f32, theme: &SettingsTheme) {
    let color = settings_color(theme.text_sec);
    draw_chevron(painter, x, y - 3.0, true, color);
    draw_chevron(painter, x, y + 3.0, false, color);
}

fn draw_chevron(painter: Painter<'_>, x: f32, y: f32, up: bool, color: Rgba) {
    let direction = if up { -1.0 } else { 1.0 };
    painter.stroke_line(
        Point::new(x - 3.0, y - 1.5 * direction),
        Point::new(x, y + 1.5 * direction),
        1.4,
        color,
        StrokeCap::Round,
    );
    painter.stroke_line(
        Point::new(x, y + 1.5 * direction),
        Point::new(x + 3.0, y - 1.5 * direction),
        1.4,
        color,
        StrokeCap::Round,
    );
}

fn draw_stepper(
    painter: Painter<'_>,
    layout: &RowLayout,
    can_move_up: bool,
    can_move_down: bool,
    theme: &SettingsTheme,
) {
    let body = Rect::from_xywh(
        layout.up.left,
        layout.up.top,
        layout.up.width(),
        layout.down.bottom - layout.up.top,
    );
    draw_raised_control(painter, body, 5.0, theme);
    painter.fill_rect(
        Rect::from_xywh(
            body.left + 3.0,
            body.center_y() - 0.25,
            body.width() - 6.0,
            0.5,
        ),
        settings_color(theme.control_border),
    );
    let color = |enabled: bool| {
        settings_color(if enabled {
            theme.text_pri
        } else {
            theme.disabled
        })
    };
    draw_chevron(
        painter,
        layout.up.center_x(),
        layout.up.center_y() + 1.0,
        true,
        color(can_move_up),
    );
    draw_chevron(
        painter,
        layout.down.center_x(),
        layout.down.center_y() - 1.0,
        false,
        color(can_move_down),
    );
}

fn draw_style_glyph(
    painter: Painter<'_>,
    rect: Rect,
    style: ResourceMetricStyle,
    color: Rgba,
    theme: &SettingsTheme,
) {
    let track = settings_color(theme.text_pri).with_alpha(28);
    match style {
        ResourceMetricStyle::Bar => {
            let bar = Rect::from_xywh(
                rect.left + 1.0,
                rect.center_y() - 2.0,
                rect.width() - 2.0,
                4.0,
            );
            painter.fill_round_rect(bar, Radius::uniform(2.0), track);
            painter.fill_round_rect(
                Rect::from_xywh(bar.left, bar.top, bar.width() * 0.62, bar.height()),
                Radius::uniform(2.0),
                color,
            );
        }
        ResourceMetricStyle::Ring => {
            let center = Point::new(rect.center_x(), rect.center_y());
            let radius = rect.width() / 2.0 - 3.0;
            painter.stroke_circle(center, radius, 3.0, track);
            painter.stroke_arc(
                Rect::from_xywh(
                    center.x - radius,
                    center.y - radius,
                    radius * 2.0,
                    radius * 2.0,
                ),
                Angle::ZERO,
                Angle::from_degrees(0.62 * 360.0),
                3.0,
                color,
                StrokeCap::Round,
            );
        }
    }
}

fn draw_segmented(
    painter: Painter<'_>,
    layout: &RowLayout,
    style: ResourceMetricStyle,
    theme: &SettingsTheme,
) {
    painter.fill_round_rect(
        layout.style,
        Radius::uniform(7.0),
        settings_color(theme.control_bg),
    );
    let (bar, ring) = (layout.bar_segment(), layout.ring_segment());
    let selected = match style {
        ResourceMetricStyle::Bar => bar,
        ResourceMetricStyle::Ring => ring,
    };
    draw_raised_control(
        painter,
        Rect::from_xywh(
            selected.left + 2.0,
            selected.top + 2.0,
            selected.width() - 4.0,
            selected.height() - 4.0,
        ),
        5.5,
        theme,
    );
    for (rect, key, active) in [
        (bar, "resource_style_bar", style == ResourceMetricStyle::Bar),
        (
            ring,
            "resource_style_ring",
            style == ResourceMetricStyle::Ring,
        ),
    ] {
        draw_centered_text(
            painter,
            &tr(key),
            rect,
            11.5,
            active,
            settings_color(if active {
                theme.text_pri
            } else {
                theme.text_sec
            }),
        );
    }
}

fn draw_swatch(painter: Painter<'_>, rect: Rect, color: Rgba, theme: &SettingsTheme) {
    let center = Point::new(rect.center_x(), rect.center_y());
    let radius = rect.width() / 2.0;
    painter.fill_circle(center, radius, color);
    painter.stroke_circle(
        center,
        radius - 0.5,
        1.0,
        settings_color(theme.text_pri).with_alpha(48),
    );
    painter.stroke_circle(
        center,
        radius - 2.5,
        1.0,
        Rgba::from_argb(70, 255, 255, 255),
    );
}

fn rgb(value: u32) -> Rgba {
    Rgba::from_rgb((value >> 16) as u8, (value >> 8) as u8, value as u8)
}

fn draw_text(painter: Painter<'_>, text: &str, x: f32, y: f32, size: f32, bold: bool, color: Rgba) {
    FontManager::global().draw_text_cached(DrawTextCachedParams {
        painter,
        text,
        x,
        y,
        size,
        bold,
        color,
        blur: None,
    });
}

fn draw_centered_text(
    painter: Painter<'_>,
    text: &str,
    rect: Rect,
    size: f32,
    bold: bool,
    color: Rgba,
) {
    let width = FontManager::global().measure_text_cached(
        text,
        size,
        if bold {
            winisland_render::FontStyle::bold()
        } else {
            winisland_render::FontStyle::normal()
        },
    );
    draw_text(
        painter,
        text,
        rect.center_x() - width / 2.0,
        rect.center_y() + size * 0.36,
        size,
        bold,
        color,
    );
}

fn draw_switch(painter: Painter<'_>, rect: Rect, enabled: bool, theme: &SettingsTheme) {
    let radius = rect.height() / 2.0;
    painter.fill_round_rect(
        rect,
        Radius::uniform(radius),
        settings_color(if enabled {
            theme.toggle_on
        } else {
            theme.toggle_off
        }),
    );
    let knob_x = if enabled {
        rect.right - radius
    } else {
        rect.left + radius
    };
    painter.fill_circle(
        Point::new(knob_x, rect.center_y() + 0.5),
        radius - 1.5,
        Rgba::from_argb(40, 0, 0, 0),
    );
    painter.fill_circle(
        Point::new(knob_x, rect.center_y()),
        radius - 2.0,
        Rgba::WHITE,
    );
}
