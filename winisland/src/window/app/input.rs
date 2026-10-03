use std::time::Instant;

use crate::ui::expanded::music_view::{
    get_cover_rect, get_next_btn_rect, get_pause_btn_rect, get_prev_btn_rect,
    get_progress_bar_rect, trigger_cover_flip, trigger_next_click, trigger_pause_click,
    trigger_prev_click,
};
use crate::ui::expanded::today_section::{self, TodayHit};
use crate::ui::widget::expanded::{widget_corner_radius, widget_grid_layout};
use crate::utils::mouse::{
    double_click_interval, is_point_in_continuous_rounded_rect, is_point_in_rect,
};
use winisland_core::config::{MIN_HIDDEN_WIDTH, WidgetKind};
use winisland_platform::InputState;

use super::{App, DragAxis, IslandLayout};
use crate::ui::expanded::pager::ExpandedPage;

#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum InputSource {
    Mouse,
    Touch,
}

impl App {
    pub(super) fn handle_input(
        &mut self,
        state: InputState,
        px: i32,
        py: i32,
        source: InputSource,
    ) {
        let fullscreen_suppressed = self.fullscreen_hide_active() && !self.hide.overlay_reveal;
        if fullscreen_suppressed || (source == InputSource::Mouse && self.is_cursor_suppressed) {
            return;
        }
        let rel_x = px - self.geom.win_x;
        let rel_y = py - self.geom.win_y;
        let layout = self.compute_island_layout();

        if state == InputState::Pressed {
            self.handle_press(rel_x, rel_y, &layout);
        } else if state == InputState::Released {
            self.update_volume_drag_position(rel_x, &layout);
            self.update_brightness_drag_position(rel_x, &layout);
            self.handle_release(px, py);
        }
    }

    pub(super) fn handle_right_input(&mut self, state: InputState, px: i32, py: i32) {
        if self.expanded && self.page_focused(ExpandedPage::Companion) && !self.is_cursor_suppressed
        {
            let layout = self.compute_island_layout();
            let action = crate::ui::expanded::companion_view::hit_test(
                winisland_render::Rect::from_xywh(
                    layout.offset_x as f32 + self.page_translation(ExpandedPage::Companion),
                    layout.island_y as f32,
                    self.springs.w.value,
                    (self.config.expanded_height * self.config.expanded_scale)
                        .min(self.springs.h.value),
                ),
                self.config.expanded_scale,
                winisland_render::Point::new(
                    (px - self.geom.win_x) as f32,
                    (py - self.geom.win_y) as f32,
                ),
            );
            if action == Some(crate::core::companion::CompanionAction::Pet) {
                if state == InputState::Released {
                    self.companion
                        .act(crate::core::companion::CompanionAction::Sleep);
                    if let Some(window) = &self.window {
                        window.request_redraw();
                    }
                }
                return;
            }
        }
        if !self.config.right_click_drag
            || self.expanded
            || self.is_cursor_suppressed
            || (self.is_fullscreen_suppressed && self.is_hidden())
        {
            return;
        }
        match state {
            InputState::Pressed => {
                let rel_x = px - self.geom.win_x;
                let rel_y = py - self.geom.win_y;
                let layout = self.compute_island_layout();
                let is_hovering = is_point_in_continuous_rounded_rect(
                    rel_x as f64,
                    rel_y as f64,
                    layout.current_island_x,
                    layout.current_island_y,
                    self.springs.w.value as f64,
                    self.springs.h.value as f64,
                    self.springs.r.value as f64,
                );
                if is_hovering {
                    self.right_press_cursor = Some((px, py));
                    self.right_drag_start_offset = Some((
                        self.config.position_x_offset + self.geom.win_x - self.geom.configured_x,
                        self.config.position_y_offset + self.geom.win_y - self.geom.configured_y,
                    ));
                }
            }
            InputState::Released => {
                if self.is_right_dragging {
                    self.is_right_dragging = false;
                    crate::core::persistence::save_config(&self.config);
                    log::info!(
                        "Right click drag offsets saved: ({}, {})",
                        self.config.position_x_offset,
                        self.config.position_y_offset
                    );
                }
                self.right_press_cursor = None;
                self.right_drag_start_offset = None;
            }
        }
    }

    pub(super) fn handle_press(&mut self, rel_x: i32, rel_y: i32, layout: &IslandLayout) {
        let island_y = layout.island_y;
        let offset_x = layout.offset_x;
        let current_island_x = layout.current_island_x;
        let current_island_y = layout.current_island_y;
        let is_hovering_visible = is_point_in_continuous_rounded_rect(
            rel_x as f64,
            rel_y as f64,
            current_island_x,
            current_island_y,
            self.springs.w.value as f64,
            self.springs.h.value as f64,
            self.springs.r.value as f64,
        ) || self.pager_contains(rel_x, rel_y, layout);
        let is_on_hidden_reveal = self.is_hidden()
            && self.config.hidden_width <= MIN_HIDDEN_WIDTH
            && self.springs.hide.value >= 0.999
            && is_point_in_rect(
                rel_x as f64,
                rel_y as f64,
                layout.hidden_reveal_x,
                layout.hidden_reveal_y,
                layout.hidden_reveal_w,
                layout.hidden_reveal_h,
            );

        if !self.expanded
            && is_hovering_visible
            && self.compact_overlay.begin_volume_drag(
                rel_x as f32,
                rel_y as f32,
                winisland_render::Rect::from_xywh(
                    current_island_x as f32,
                    current_island_y as f32,
                    self.springs.w.value,
                    self.springs.h.value,
                ),
                self.config.compact_scale,
            )
        {
            self.idle_timer = Instant::now();
            return;
        }

        if !self.expanded
            && is_hovering_visible
            && self.compact_overlay.begin_brightness_drag(
                rel_x as f32,
                rel_y as f32,
                winisland_render::Rect::from_xywh(
                    current_island_x as f32,
                    current_island_y as f32,
                    self.springs.w.value,
                    self.springs.h.value,
                ),
                self.config.compact_scale,
            )
        {
            self.idle_timer = Instant::now();
            return;
        }

        if !(self.expanded || self.fullscreen_hide_active())
            && self.compact_overlay.is_notification_visible()
            && is_hovering_visible
        {
            self.dismissing_notification = true;
            self.is_dragging = true;
            self.drag_start_px = rel_x + self.geom.win_x;
            self.drag_start_py = rel_y + self.geom.win_y;
            self.drag_has_moved = false;
            self.drag_axis = None;
            return;
        }

        if self.fullscreen_hide_active() {
            return;
        }

        if self.expanded {
            self.expanded_press_started_inside = true;
            self.expanded_header_press = None;
            if self.handle_pager_press(rel_x, rel_y, layout) {
                return;
            }
            let today_area = today_section::rect(
                winisland_render::Rect::from_xywh(
                    layout.current_island_x as f32,
                    layout.current_island_y as f32,
                    self.springs.w.value,
                    self.springs.h.value,
                ),
                (self.config.expanded_height * self.config.expanded_scale)
                    .min(self.springs.h.value),
                self.config.expanded_scale,
                today_section::height(self.agent.snapshot(), self.agent.connected()),
            );
            let point = winisland_render::Point::new(rel_x as f32, rel_y as f32);
            if today_area.contains(point) {
                if let Some(hit) = today_section::hit_test(
                    today_area,
                    self.config.expanded_scale,
                    self.agent.snapshot(),
                    self.agent.connected(),
                    point,
                ) {
                    let command = match hit {
                        TodayHit::Complete(index) => self.agent.snapshot().and_then(|snapshot| snapshot.tasks.get(index)).map(|task| (if task.status == crate::core::agent::TaskStatus::Done { "task_reopen" } else { "task_complete" }, serde_json::json!({"task_id": task.id}))),
                        TodayHit::Detail(index) => self.agent.snapshot().and_then(|snapshot| snapshot.tasks.get(index)).map(|task| ("task_detail", serde_json::json!({"task_id": task.id}))),
                        TodayHit::More => Some(("open_tasks", serde_json::json!({}))),
                        TodayHit::ReminderComplete => self.agent.snapshot().map(|snapshot| ("reminder_complete", serde_json::json!({"reminder_id": snapshot.reminder_id}))),
                        TodayHit::ReminderSnooze => self.agent.snapshot().map(|snapshot| ("reminder_snooze", serde_json::json!({"reminder_id": snapshot.reminder_id, "minutes": 10}))),
                        TodayHit::ReminderDismiss => self.agent.snapshot().map(|snapshot| ("reminder_dismiss", serde_json::json!({"reminder_id": snapshot.reminder_id}))),
                    };
                    if let Some((action, args)) = command
                        && let Err(error) = self.agent.send_command(action, args)
                    {
                        log::warn!("Cannot send today action: {error}");
                    }
                }
                return;
            }
            let w = self.springs.w.value as f64;
            let h = (self.config.expanded_height * self.config.expanded_scale)
                .min(self.springs.h.value) as f64;
            let scale = self.config.expanded_scale as f64;

            if self.page_focused(ExpandedPage::Companion)
                && let Some(action) = crate::ui::expanded::companion_view::hit_test(
                    winisland_render::Rect::from_xywh(
                        offset_x as f32 + self.page_translation(ExpandedPage::Companion),
                        island_y as f32,
                        w as f32,
                        h as f32,
                    ),
                    self.config.expanded_scale,
                    winisland_render::Point::new(rel_x as f32, rel_y as f32),
                )
            {
                self.companion.act(action);
                if let Some(window) = &self.window {
                    window.request_redraw();
                }
                return;
            }

            if self.page_focused(ExpandedPage::Music) {
                let media = self.current_media_info().clone();
                let music_on = !media.title.is_empty()
                    && (self.plugin_media_source.is_some() || self.config.smtc_enabled);
                let cx = rel_x as f32 - self.page_translation(ExpandedPage::Music);
                let cy = rel_y as f32;
                let (cover_x, cover_y, cover_w, cover_h) =
                    get_cover_rect(offset_x as f32, island_y as f32, self.config.expanded_scale);
                if music_on
                    && !media.source_app_id.is_empty()
                    && cx >= cover_x
                    && cx <= cover_x + cover_w
                    && cy >= cover_y
                    && cy <= cover_y + cover_h
                {
                    if self
                        .cover_click
                        .register((cx, cy), Instant::now(), double_click_interval())
                    {
                        if crate::platform::shell()
                            .activate_media_app(&media.source_app_id)
                            .unwrap_or_else(|error| {
                                log::warn!("Media application activation failed: {error}");
                                false
                            })
                        {
                            log::info!("Media application activated: {}", media.source_app_id);
                        } else {
                            log::warn!(
                                "Media application could not be activated: {}",
                                media.source_app_id
                            );
                        }
                    }
                    return;
                }
                self.cover_click.reset();

                let (bx, by, bw, bh) = get_pause_btn_rect(
                    offset_x as f32,
                    island_y as f32,
                    w as f32,
                    self.config.expanded_scale,
                );
                if music_on
                    && self.media_control_available(
                        winisland_plugin_api::types::v2::context::MEDIA_CONTROL_TOGGLE_PLAY,
                    )
                    && cx >= bx
                    && cx <= bx + bw
                    && cy >= by
                    && cy <= by + bh
                {
                    trigger_pause_click(media.is_playing);
                    self.dispatch_media_command(
                        winisland_plugin_api::types::v2::context::MEDIA_COMMAND_TOGGLE_PLAY,
                        0,
                    );
                    return;
                }

                let (px, py, pw, ph) = get_prev_btn_rect(
                    offset_x as f32,
                    island_y as f32,
                    w as f32,
                    self.config.expanded_scale,
                );
                if music_on
                    && self.media_control_available(
                        winisland_plugin_api::types::v2::context::MEDIA_CONTROL_PREVIOUS,
                    )
                    && cx >= px
                    && cx <= px + pw
                    && cy >= py
                    && cy <= py + ph
                {
                    trigger_cover_flip();
                    trigger_prev_click();
                    self.dispatch_media_command(
                        winisland_plugin_api::types::v2::context::MEDIA_COMMAND_PREVIOUS,
                        0,
                    );
                    return;
                }

                let (nx, ny, nw, nh) = get_next_btn_rect(
                    offset_x as f32,
                    island_y as f32,
                    w as f32,
                    self.config.expanded_scale,
                );
                if music_on
                    && self.media_control_available(
                        winisland_plugin_api::types::v2::context::MEDIA_CONTROL_NEXT,
                    )
                    && cx >= nx
                    && cx <= nx + nw
                    && cy >= ny
                    && cy <= ny + nh
                {
                    trigger_cover_flip();
                    trigger_next_click();
                    self.dispatch_media_command(
                        winisland_plugin_api::types::v2::context::MEDIA_COMMAND_NEXT,
                        0,
                    );
                    return;
                }

                if let Some((bar_left, bar_right, bar_top, bar_hit_h)) = get_progress_bar_rect(
                    offset_x as f32,
                    island_y as f32,
                    w as f32,
                    music_on,
                    self.config.expanded_scale,
                ) && self.media_control_available(
                    winisland_plugin_api::types::v2::context::MEDIA_CONTROL_SEEK,
                ) && cx >= bar_left
                    && cx <= bar_right
                    && cy >= bar_top
                    && cy <= bar_top + bar_hit_h
                {
                    let ratio = ((cx - bar_left) / (bar_right - bar_left)).clamp(0.0, 1.0);
                    let duration_ms = media.effective_duration_ms();
                    let seek_ms = (ratio as f64 * duration_ms as f64) as u64;
                    self.seek.begin(
                        bar_left,
                        bar_right,
                        duration_ms,
                        seek_ms,
                        self.plugin_media_source
                            .as_ref()
                            .map(|source| source.resource_id),
                    );
                    return;
                }
            }

            if self.page_focused(ExpandedPage::Widgets) {
                let widget_shift = self.page_translation(ExpandedPage::Widgets) as f64;
                let settings_hit = self
                    .config
                    .widget_layout
                    .iter()
                    .find(|entry| entry.widget == Some(WidgetKind::Settings))
                    .is_some_and(|entry| {
                        let layout = widget_grid_layout(
                            offset_x as f32,
                            island_y as f32,
                            w as f32,
                            h as f32,
                            self.config.expanded_scale,
                        );
                        let (x, y, width, height) =
                            layout.footprint_rect(WidgetKind::Settings, entry.slot);
                        is_point_in_continuous_rounded_rect(
                            rel_x as f64,
                            rel_y as f64,
                            x as f64 + widget_shift,
                            y as f64,
                            width as f64,
                            height as f64,
                            widget_corner_radius(width, height, self.config.expanded_scale) as f64,
                        )
                    });
                if settings_hit {
                    self.open_settings();
                    return;
                }
            }

            if self.page_focused(ExpandedPage::Calendar)
                && let Some(action) = crate::ui::expanded::calendar_view::hit_test(
                    offset_x as f32 + self.page_translation(ExpandedPage::Calendar),
                    island_y as f32,
                    w as f32,
                    h as f32,
                    self.config.expanded_scale,
                    winisland_render::Point::new(rel_x as f32, rel_y as f32),
                )
            {
                crate::ui::expanded::calendar_view::apply_action(action);
                if let Some(window) = &self.window {
                    window.request_redraw();
                }
                return;
            }

            if (rel_y as f64) < island_y + 40.0 * scale {
                self.expanded_header_press =
                    Some((rel_x + self.geom.win_x, rel_y + self.geom.win_y));
            }
        } else if is_hovering_visible || is_on_hidden_reveal {
            if self.is_hidden() && !self.components_hidden {
                self.reveal_island();
                return;
            }
            self.is_dragging = true;
            self.drag_start_px = rel_x + self.geom.win_x;
            self.drag_start_py = rel_y + self.geom.win_y;
            self.drag_start_hide_val = self.springs.hide.value;
            self.drag_has_moved = false;
            self.drag_axis = None;
        }
    }

    pub(super) fn handle_release(&mut self, px: i32, py: i32) {
        self.expanded_press_started_inside = false;
        let expanded_header_press = self.expanded_header_press.take();
        if self.compact_overlay.finish_volume_drag() {
            return;
        }
        if self.compact_overlay.finish_brightness_drag() {
            return;
        }
        if self.finish_seek() {
            return;
        }
        if let Some((start_x, start_y)) = expanded_header_press {
            let threshold = (10.0 * self.config.expanded_scale).max(8.0) as i32;
            if self.expanded
                && (px - start_x).abs() <= threshold
                && (py - start_y).abs() <= threshold
            {
                self.expanded = false;
                self.reset_page();
            }
            return;
        }
        if self.dismissing_notification {
            self.dismissing_notification = false;
            self.is_dragging = false;
            self.drag_axis = None;
            if self.drag_start_py - py > 20 {
                self.compact_overlay.dismiss_notification();
            } else if !self.compact_overlay.activate_notification() {
                self.expand();
            }
            return;
        }
        if self.is_dragging {
            self.is_dragging = false;
            let dx = px - self.drag_start_px;
            let dy = py - self.drag_start_py;
            let drag_axis = self.drag_axis.take();
            if !self.expanded
                && drag_axis != Some(DragAxis::Vertical)
                && dx.abs() >= 40
                && dx.abs() > dy.abs() * 2
            {
                self.components_hidden = !self.components_hidden;
                if self.is_hidden() {
                    self.reveal_island();
                }
                self.idle_timer = Instant::now();
                if let Some(window) = &self.window {
                    window.request_redraw();
                }
                return;
            }
            if drag_axis == Some(DragAxis::Horizontal) {
                return;
            }
            if !self.drag_has_moved
                || (self.components_hidden
                    && drag_axis.is_none()
                    && dx.abs() <= 10
                    && dy.abs() <= 10)
            {
                if self.is_hidden() {
                    self.reveal_island();
                } else {
                    self.expand();
                }
            } else if self.springs.hide.value > 0.3 {
                self.hide.manual = true;
                self.hide.auto = false;
                self.hide.fullscreen = false;
            } else {
                self.hide.manual = false;
                self.hide.auto = false;
                self.hide.fullscreen = false;
            }
        }
    }

    pub(super) fn update_volume_drag_position(&mut self, rel_x: i32, layout: &IslandLayout) {
        self.compact_overlay.update_volume_drag(
            rel_x as f32,
            winisland_render::Rect::from_xywh(
                layout.current_island_x as f32,
                layout.current_island_y as f32,
                self.springs.w.value,
                self.springs.h.value,
            ),
            self.config.compact_scale,
        );
    }

    pub(super) fn update_brightness_drag_position(&mut self, rel_x: i32, layout: &IslandLayout) {
        self.compact_overlay.update_brightness_drag(
            rel_x as f32,
            winisland_render::Rect::from_xywh(
                layout.current_island_x as f32,
                layout.current_island_y as f32,
                self.springs.w.value,
                self.springs.h.value,
            ),
            self.config.compact_scale,
        );
    }

    fn expand(&mut self) {
        let compact_height = self.compact_content_height();
        let interrupts_collapse = self.springs.h.value - compact_height
            > 0.5 * self.config.compact_scale
            || self.springs.h.velocity.abs() > 0.001;
        self.reset_page();
        if !interrupts_collapse {
            self.snap_to_current_page();
        }
        self.expanded = true;
    }

    pub fn show_companion(&mut self) {
        self.expanded = true;
        if self.companion.island_enabled() {
            self.current_page = ExpandedPage::Companion;
        } else {
            self.reset_page();
        }
        self.snap_to_current_page();
    }
}
