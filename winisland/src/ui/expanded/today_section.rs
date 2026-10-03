use crate::core::agent::{AgentSnapshot, TaskStatus};
use winisland_render::text::{FontManager, PluginTextParams};
use winisland_render::{Painter, Point, Rect, Rgba};

pub const MAX_HEIGHT: f32 = 192.0;
const FONT: &str = "Microsoft YaHei UI";

#[derive(Clone, Copy)]
pub enum TodayHit {
    Complete(usize),
    Detail(usize),
    More,
    ReminderComplete,
    ReminderSnooze,
    ReminderDismiss,
}

pub fn height(snapshot: Option<&AgentSnapshot>, connected: bool) -> f32 {
    let Some(snapshot) = snapshot else {
        return 0.0;
    };
    let task_count = snapshot.visible_task_count();
    let reminding = snapshot.reminder_active(connected);
    if task_count == 0 && !reminding {
        return 0.0;
    }
    let row_end = 32.0 + task_count as f32 * 26.0;
    if reminding {
        row_end + 56.0
    } else {
        row_end + 4.0
    }
}

pub fn rect(island: Rect, original_height: f32, scale: f32, footer_height: f32) -> Rect {
    Rect::from_xywh(
        island.left,
        island.top + original_height,
        island.width(),
        (island.height() - original_height)
            .min(footer_height * scale)
            .max(0.0),
    )
}

pub fn hit_test(
    area: Rect,
    scale: f32,
    snapshot: Option<&AgentSnapshot>,
    connected: bool,
    point: Point,
) -> Option<TodayHit> {
    if !area.contains(point) || area.height() < 30.0 * scale {
        return None;
    }
    let snapshot = snapshot?;
    let x = point.x - area.left;
    let y = (point.y - area.top) / scale;
    let row_end = 32.0 + snapshot.visible_task_count() as f32 * 26.0;
    if snapshot.additional_task_count() > 0
        && (7.0..32.0).contains(&y)
        && x > area.width() - 92.0 * scale
    {
        return Some(TodayHit::More);
    }
    if (32.0..row_end).contains(&y) {
        let index = ((y - 32.0) / 26.0) as usize;
        if index < snapshot.visible_task_count() {
            return Some(if x < 48.0 * scale {
                TodayHit::Complete(index)
            } else {
                TodayHit::Detail(index)
            });
        }
    }
    if ((row_end + 25.0)..(row_end + 56.0)).contains(&y) && snapshot.reminder_active(connected) {
        let third = area.width() / 3.0;
        return Some(if x < third {
            TodayHit::ReminderComplete
        } else if x < third * 2.0 {
            TodayHit::ReminderSnooze
        } else {
            TodayHit::ReminderDismiss
        });
    }
    None
}

pub fn draw(
    painter: Painter<'_>,
    area: Rect,
    scale: f32,
    alpha: u8,
    snapshot: Option<&AgentSnapshot>,
    connected: bool,
) {
    if alpha == 0 || area.height() < 30.0 * scale {
        return;
    }
    painter.save();
    painter.clip_rect(area);
    painter.save_alpha(alpha);
    let x = area.left + 22.0 * scale;
    let right = area.right - 22.0 * scale;
    painter.fill_rect(
        Rect::from_xywh(x, area.top, (right - x).max(0.0), scale),
        Rgba::from_rgba(255, 255, 255, 32),
    );
    label(
        painter,
        "接下来",
        Rect::from_xywh(x, area.top + 7.0 * scale, 76.0 * scale, 24.0 * scale),
        14.0 * scale,
        600,
        Rgba::WHITE,
    );
    if let Some(snapshot) = snapshot {
        if snapshot.additional_task_count() > 0 {
            label(
                painter,
                "查看全部",
                Rect::from_xywh(
                    right - 65.0 * scale,
                    area.top + 8.0 * scale,
                    65.0 * scale,
                    22.0 * scale,
                ),
                11.0 * scale,
                400,
                Rgba::from_rgb(183, 193, 204),
            );
        }
        for (index, task) in snapshot.tasks.iter().take(4).enumerate() {
            let row_y = area.top + (32.0 + index as f32 * 26.0) * scale;
            let center = Point::new(x + 7.0 * scale, row_y + 12.0 * scale);
            if task.status == TaskStatus::Done {
                painter.fill_circle(center, 5.0 * scale, Rgba::from_rgb(142, 189, 151));
            } else {
                painter.stroke_circle(center, 4.0 * scale, scale, Rgba::from_rgb(167, 176, 182));
            }
            let time_width = if task.time_text.is_empty() {
                0.0
            } else {
                82.0 * scale
            };
            label(
                painter,
                &task.title,
                Rect::from_xywh(
                    x + 20.0 * scale,
                    row_y + 1.0 * scale,
                    (right - x - 20.0 * scale - time_width).max(0.0),
                    22.0 * scale,
                ),
                12.0 * scale,
                400,
                if task.status == TaskStatus::Done {
                    Rgba::from_rgb(150, 156, 160)
                } else {
                    Rgba::WHITE
                },
            );
            if time_width > 0.0 {
                label(
                    painter,
                    &task.time_text,
                    Rect::from_xywh(
                        right - time_width,
                        row_y + 2.0 * scale,
                        time_width,
                        20.0 * scale,
                    ),
                    10.0 * scale,
                    400,
                    Rgba::from_rgb(163, 171, 178),
                );
            }
        }
        let row_end = 32.0 + snapshot.visible_task_count() as f32 * 26.0;
        if snapshot.reminder_active(connected) {
            let reminder_text = if snapshot.label.is_empty() {
                "到提醒时间了".to_string()
            } else {
                format!("提醒 · {}", snapshot.label)
            };
            label(
                painter,
                &reminder_text,
                Rect::from_xywh(
                    x,
                    area.top + (row_end + 4.0) * scale,
                    (right - x).max(0.0),
                    20.0 * scale,
                ),
                11.0 * scale,
                400,
                Rgba::from_rgb(183, 193, 204),
            );
            let y = area.top + (row_end + 29.0) * scale;
            label(
                painter,
                "完成",
                Rect::from_xywh(x, y, 46.0 * scale, 22.0 * scale),
                11.0 * scale,
                400,
                Rgba::from_rgb(159, 206, 169),
            );
            label(
                painter,
                "10 分钟后",
                Rect::from_xywh(
                    area.center_x() - 40.0 * scale,
                    y,
                    85.0 * scale,
                    22.0 * scale,
                ),
                11.0 * scale,
                400,
                Rgba::from_rgb(196, 203, 210),
            );
            label(
                painter,
                "稍后处理",
                Rect::from_xywh(right - 60.0 * scale, y, 60.0 * scale, 22.0 * scale),
                11.0 * scale,
                400,
                Rgba::from_rgb(196, 203, 210),
            );
        }
    }
    painter.restore();
    painter.restore();
}

fn label(painter: Painter<'_>, text: &str, rect: Rect, size: f32, weight: u16, color: Rgba) {
    FontManager::global().draw_plugin_text(
        PluginTextParams {
            painter,
            rect,
            size: size.round(),
            italic: false,
            family: FONT,
            align: 0,
            wrap: false,
            ellipsis: true,
        },
        text,
        weight,
        color,
    );
}
