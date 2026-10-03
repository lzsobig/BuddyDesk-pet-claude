use std::cell::RefCell;
use std::time::{Duration, Instant};

use winisland_core::config::{ResourceMetricKind, WidgetKind};
use winisland_core::i18n::tr;
use winisland_render::text::FontManager;
use winisland_render::{Painter, Radius, Rect, Rgba};

use super::{draw_widget_rounded_background, draw_widget_text_centered};
use crate::ui::widget::resource_usage::{with_expanded_config, with_resource_usage};

struct TaskSummary {
    bridge: crate::core::agent::AgentBridge,
    read_at: Option<Instant>,
    completed: u64,
    pending: u64,
    next: String,
    available: bool,
}

impl Default for TaskSummary {
    fn default() -> Self {
        Self {
            bridge: crate::core::agent::AgentBridge::new(),
            read_at: None,
            completed: 0,
            pending: 0,
            next: String::new(),
            available: false,
        }
    }
}

impl TaskSummary {
    fn refresh(&mut self) {
        if self
            .read_at
            .is_some_and(|at| at.elapsed() < Duration::from_secs(1))
        {
            return;
        }
        let now = Instant::now();
        self.read_at = Some(now);
        self.bridge.poll(now);
        self.available = self.bridge.connected();
        if let Some(data) = self.bridge.snapshot().filter(|_| self.available) {
            self.completed = data.completed_today as u64;
            self.pending = data.pending_count.unwrap_or_else(|| {
                data.total_count.saturating_sub(
                    data.tasks
                        .iter()
                        .filter(|task| task.status == crate::core::agent::TaskStatus::Done)
                        .count(),
                )
            }) as u64;
            self.next = data
                .tasks
                .iter()
                .find(|task| task.status == crate::core::agent::TaskStatus::Pending)
                .map(|task| task.title.clone())
                .unwrap_or_default();
        } else {
            self.completed = 0;
            self.pending = 0;
            self.next.clear();
        }
    }
}

thread_local! { static TASKS: RefCell<TaskSummary> = RefCell::new(TaskSummary::default()); }

#[allow(clippy::too_many_arguments)]
pub fn draw_summary(
    painter: Painter<'_>,
    kind: WidgetKind,
    bounds: Rect,
    scale: f32,
    alpha: u8,
    text_color: Rgba,
    preview: bool,
) {
    let (label, value, progress, detail) = match kind {
        WidgetKind::Today => {
            if preview {
                (
                    tr("widget_today"),
                    "2 / 5".into(),
                    Some(0.4),
                    tr("widget_today_hint"),
                )
            } else {
                TASKS.with(|cell| {
                    let mut tasks = cell.borrow_mut();
                    tasks.refresh();
                    let total = tasks.completed + tasks.pending;
                    (
                        tr("widget_today"),
                        if tasks.available {
                            format!("{} / {total}", tasks.completed)
                        } else {
                            "—".into()
                        },
                        (total > 0).then(|| tasks.completed as f32 / total as f32),
                        if !tasks.available {
                            tr("widget_agent_offline")
                        } else if tasks.next.is_empty() {
                            tr("widget_today_clear")
                        } else {
                            tasks.next.clone()
                        },
                    )
                })
            }
        }
        _ => {
            let metric = if kind == WidgetKind::Network {
                ResourceMetricKind::Network
            } else {
                ResourceMetricKind::Disk
            };
            let (value, progress) = if preview {
                if kind == WidgetKind::Network {
                    ("2.4M/s".into(), None)
                } else {
                    ("71%".into(), Some(0.71))
                }
            } else {
                with_expanded_config(|config| {
                    with_resource_usage(config, |usage| {
                        let usage = usage.metric(metric);
                        (
                            if usage.text.is_empty() {
                                "—".to_string()
                            } else {
                                usage.text.to_string()
                            },
                            usage.value,
                        )
                    })
                })
            };
            (
                tr(if kind == WidgetKind::Network {
                    "widget_network"
                } else {
                    "widget_storage"
                }),
                value,
                if kind == WidgetKind::Network {
                    None
                } else {
                    progress
                },
                tr(if kind == WidgetKind::Network {
                    "widget_network_hint"
                } else {
                    "widget_storage_hint"
                }),
            )
        }
    };
    let save = painter.save();
    painter.clip_rect(bounds);
    draw_widget_rounded_background(
        painter,
        bounds.left,
        bounds.top,
        bounds.width(),
        bounds.height(),
        scale,
        alpha,
    );
    let inset = (9.0 * scale).min(bounds.width() * 0.16);
    let large = bounds.height() > 80.0 * scale;
    let label_size = (bounds.height() * 0.15).clamp(6.0 * scale, 10.0 * scale);
    draw_widget_text_centered(
        painter,
        &label,
        Rect::from_xywh(
            bounds.left + inset,
            bounds.top + inset,
            bounds.width() - inset * 2.0,
            label_size * 1.5,
        ),
        label_size,
        false,
        text_color.with_alpha((alpha as f32 * 0.55) as u8),
    );
    let mut size = (bounds.height() * 0.32).clamp(9.0 * scale, 30.0 * scale);
    let width = FontManager::global()
        .measure_str(&value, size, true)
        .width();
    size *= ((bounds.width() - inset * 2.0) / width.max(1.0)).min(1.0);
    draw_widget_text_centered(
        painter,
        &value,
        Rect::from_xywh(
            bounds.left,
            bounds.top + bounds.height() * 0.32,
            bounds.width(),
            bounds.height() * 0.40,
        ),
        size,
        true,
        text_color.with_alpha(alpha),
    );
    if large {
        let detail = crate::utils::settings_ui::ellipsize_text(
            FontManager::global(),
            &detail,
            label_size,
            winisland_render::FontStyle::normal(),
            bounds.width() - inset * 2.0,
        );
        draw_widget_text_centered(
            painter,
            &detail,
            Rect::from_xywh(
                bounds.left + inset,
                bounds.top + bounds.height() * 0.75,
                bounds.width() - inset * 2.0,
                label_size * 1.5,
            ),
            label_size,
            false,
            text_color.with_alpha((alpha as f32 * 0.5) as u8),
        );
    }
    if let Some(progress) = progress {
        let track = Rect::from_xywh(
            bounds.left + inset,
            bounds.bottom - 6.0 * scale,
            bounds.width() - inset * 2.0,
            2.0 * scale,
        );
        painter.fill_round_rect(
            track,
            Radius::uniform(scale),
            text_color.with_alpha((alpha as f32 * 0.1) as u8),
        );
        if progress > 0.0 {
            painter.fill_round_rect(
                Rect::from_xywh(
                    track.left,
                    track.top,
                    track.width() * progress.clamp(0.0, 1.0),
                    track.height(),
                ),
                Radius::uniform(scale),
                Rgba::from_rgb(164, 193, 181).with_alpha(alpha),
            );
        }
    }
    painter.restore_to(save);
}
