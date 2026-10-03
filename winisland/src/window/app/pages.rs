use std::time::{Duration, Instant};

use crate::ui::expanded::pager::{self, ExpandedPage, PageAvailability, PagerHit, available_pages};
use crate::utils::mouse::is_point_in_continuous_rounded_rect;
use winisland_platform::MouseWheelDelta;
use winisland_render::{Point, Rect};

use super::{App, IslandLayout};

const WHEEL_COOLDOWN: Duration = Duration::from_millis(260);
const WHEEL_PIXEL_THRESHOLD: f32 = 40.0;

impl App {
    pub(super) fn expanded_pages(&self) -> Vec<ExpandedPage> {
        available_pages(&PageAvailability {
            music: self.music_page_available,
            companion: self.companion.island_enabled(),
        })
    }

    fn page_index(&self, page: ExpandedPage) -> Option<usize> {
        self.expanded_pages()
            .iter()
            .position(|candidate| *candidate == page)
    }

    fn page_distance(&self, page: ExpandedPage) -> Option<f32> {
        self.page_index(page)
            .map(|index| (index as f32 - self.springs.view.value).abs())
    }

    pub(super) fn page_translation(&self, page: ExpandedPage) -> f32 {
        self.page_index(page).map_or(0.0, |index| {
            (index as f32 - self.springs.view.value) * self.springs.w.value
        })
    }

    pub(super) fn page_visible(&self, page: ExpandedPage) -> bool {
        self.page_distance(page)
            .is_some_and(|distance| distance < 1.0)
    }

    pub(super) fn page_focused(&self, page: ExpandedPage) -> bool {
        self.page_distance(page)
            .is_some_and(|distance| distance < 0.5)
    }

    pub(super) fn target_page_position(&self) -> f32 {
        self.page_index(self.current_page).unwrap_or(0) as f32
    }

    pub(super) fn reset_page(&mut self) {
        crate::ui::expanded::calendar_view::reset_to_today();
        self.current_page = self
            .expanded_pages()
            .first()
            .copied()
            .unwrap_or(ExpandedPage::Widgets);
    }

    pub(super) fn snap_to_current_page(&mut self) {
        self.springs.view.value = self.target_page_position();
        self.springs.view.velocity = 0.0;
    }

    fn go_to_page_index(&mut self, index: usize) -> bool {
        match self.expanded_pages().get(index) {
            Some(page) if *page != self.current_page => {
                self.current_page = *page;
                true
            }
            _ => false,
        }
    }

    fn step_page(&mut self, step: i32) -> bool {
        let count = self.expanded_pages().len();
        if count < 2 {
            return false;
        }
        let current = self.page_index(self.current_page).unwrap_or(0) as i32;
        let next = (current + step).clamp(0, count as i32 - 1) as usize;
        self.go_to_page_index(next)
    }

    pub(super) fn set_music_page_available(&mut self, available: bool) {
        if available == self.music_page_available {
            return;
        }
        let previous = self.expanded_pages();
        let view = self.springs.view.value;
        let shown_index = (view.round().max(0.0) as usize).min(previous.len().saturating_sub(1));
        let shown = previous.get(shown_index).copied();
        self.music_page_available = available;
        let pages = self.expanded_pages();
        match shown.and_then(|page| pages.iter().position(|candidate| *candidate == page)) {
            Some(index) => self.springs.view.value = index as f32 + (view - shown_index as f32),
            None => {
                self.springs.view.value = shown_index.min(pages.len().saturating_sub(1)) as f32;
                self.springs.view.velocity = 0.0;
            }
        }
        if !pages.contains(&self.current_page) {
            self.current_page = shown
                .filter(|page| pages.contains(page))
                .or_else(|| pages.first().copied())
                .unwrap_or(ExpandedPage::Widgets);
        }
    }

    fn island_rect(&self, layout: &IslandLayout) -> Rect {
        Rect::from_xywh(
            layout.current_island_x as f32,
            layout.current_island_y as f32,
            self.springs.w.value,
            self.springs.h.value,
        )
    }

    pub(super) fn pager_contains(&self, rel_x: i32, rel_y: i32, layout: &IslandLayout) -> bool {
        self.expanded
            && pager::contains(
                self.island_rect(layout),
                self.expanded_pages().len(),
                self.config.expanded_scale,
                layout.dock_bottom,
                Point::new(rel_x as f32, rel_y as f32),
            )
    }

    pub(super) fn handle_pager_press(
        &mut self,
        rel_x: i32,
        rel_y: i32,
        layout: &IslandLayout,
    ) -> bool {
        if !self.expanded {
            return false;
        }
        let Some(hit) = pager::hit_test(
            self.island_rect(layout),
            self.expanded_pages().len(),
            self.springs.view.value,
            self.config.expanded_scale,
            layout.dock_bottom,
            Point::new(rel_x as f32, rel_y as f32),
        ) else {
            return false;
        };
        match hit {
            PagerHit::Page(index) => {
                self.go_to_page_index(index);
            }
            PagerHit::Close => {
                self.expanded = false;
                self.reset_page();
            }
        }
        true
    }

    pub(super) fn update_pager_hover(
        &mut self,
        window: &crate::platform::WindowRef,
        rel_x: i32,
        rel_y: i32,
        layout: &IslandLayout,
        interaction_allowed: bool,
        dt: f32,
    ) {
        let hit = (interaction_allowed && self.expanded)
            .then(|| {
                pager::hit_test(
                    self.island_rect(layout),
                    self.expanded_pages().len(),
                    self.springs.view.value,
                    self.config.expanded_scale,
                    layout.dock_bottom,
                    Point::new(rel_x as f32, rel_y as f32),
                )
            })
            .flatten();
        let close_target = if hit == Some(PagerHit::Close) {
            1.0
        } else {
            0.0
        };
        let bar_target = if matches!(hit, Some(PagerHit::Page(_))) {
            1.0
        } else {
            0.0
        };
        let before = (self.close_hover.value, self.bar_hover.value);
        for (spring, target) in [
            (&mut self.close_hover, close_target),
            (&mut self.bar_hover, bar_target),
        ] {
            spring.update_dt(target, 0.22, 0.62, dt);
            spring.settle(target, 0.002, 0.001);
        }
        let calendar_hover =
            (interaction_allowed && self.expanded && self.page_focused(ExpandedPage::Calendar))
                .then(|| {
                    crate::ui::expanded::calendar_view::hit_test(
                        layout.offset_x as f32 + self.page_translation(ExpandedPage::Calendar),
                        layout.island_y as f32,
                        self.springs.w.value,
                        (self.config.expanded_height * self.config.expanded_scale)
                            .min(self.springs.h.value),
                        self.config.expanded_scale,
                        Point::new(rel_x as f32, rel_y as f32),
                    )
                })
                .flatten();
        let calendar_changed = crate::ui::expanded::calendar_view::set_hover(calendar_hover);
        let companion_hover =
            (interaction_allowed && self.expanded && self.page_focused(ExpandedPage::Companion))
                .then(|| {
                    crate::ui::expanded::companion_view::hit_test(
                        Rect::from_xywh(
                            layout.offset_x as f32 + self.page_translation(ExpandedPage::Companion),
                            layout.island_y as f32,
                            self.springs.w.value,
                            (self.config.expanded_height * self.config.expanded_scale)
                                .min(self.springs.h.value),
                        ),
                        self.config.expanded_scale,
                        Point::new(rel_x as f32, rel_y as f32),
                    )
                })
                .flatten();
        let companion_changed = self.companion.set_hover(companion_hover);
        if (self.close_hover.value, self.bar_hover.value) != before
            || calendar_changed
            || companion_changed
        {
            window.request_redraw();
        }
    }

    pub(super) fn handle_mouse_wheel(&mut self, delta: MouseWheelDelta, px: i32, py: i32) -> bool {
        if !self.expanded {
            return false;
        }
        let rel_x = px - self.geom.win_x;
        let rel_y = py - self.geom.win_y;
        let layout = self.compute_island_layout();
        if rel_y as f32
            >= layout.current_island_y as f32
                + self.config.expanded_height * self.config.expanded_scale
        {
            return false;
        }
        let over_island = is_point_in_continuous_rounded_rect(
            rel_x as f64,
            rel_y as f64,
            layout.current_island_x,
            layout.current_island_y,
            self.springs.w.value as f64,
            self.springs.h.value as f64,
            self.springs.r.value as f64,
        );
        if !over_island && !self.pager_contains(rel_x, rel_y, &layout) {
            return false;
        }
        let dominant = |x: f32, y: f32| if x.abs() > y.abs() { x } else { -y };
        let step = match delta {
            MouseWheelDelta::Lines { x, y } => {
                self.wheel_accumulator = 0.0;
                dominant(x, y).signum()
            }
            MouseWheelDelta::Pixels { x, y } => {
                self.wheel_accumulator += dominant(x as f32, y as f32);
                if self.wheel_accumulator.abs() < WHEEL_PIXEL_THRESHOLD {
                    return false;
                }
                let step = self.wheel_accumulator.signum();
                self.wheel_accumulator = 0.0;
                step
            }
        };
        if step == 0.0 {
            return false;
        }
        let now = Instant::now();
        if self
            .last_wheel_page_at
            .is_some_and(|last| now.saturating_duration_since(last) < WHEEL_COOLDOWN)
        {
            return false;
        }
        self.last_wheel_page_at = Some(now);
        self.idle_timer = now;
        self.step_page(step as i32)
    }
}
