use std::cell::RefCell;

use crate::core::companion::{Companion, CompanionAction, PetMood};
use winisland_render::text::{FontManager, PluginTextParams};
use winisland_render::{
    Image, ImageFit, ImageOptions, Painter, Point, Radius, Rect, Rgba, Sampling, StrokeCap,
};

const ACCENT: Rgba = Rgba::from_rgb(242, 174, 111);
const MUTED: Rgba = Rgba::from_rgb(205, 207, 213);
const UI_FONT: &str = "Microsoft YaHei UI";
const FRAME_BYTES: [&[u8]; 2] = [
    include_bytes!("../../../resources/companion/idle.png"),
    include_bytes!("../../../resources/companion/thinking.png"),
];
const PIXEL_FRAME_BYTES: [&[u8]; 2] = [
    include_bytes!("../../../resources/companion/frame_00.png"),
    include_bytes!("../../../resources/companion/frame_64.png"),
];

thread_local! {
    static SPRITES: RefCell<Option<(String, Vec<Option<Image>>)>> = const { RefCell::new(None) };
}

pub struct CompanionPageParams<'a> {
    pub painter: Painter<'a>,
    pub rect: Rect,
    pub scale: f32,
    pub alpha: u8,
    pub companion: &'a Companion,
    pub playing: bool,
}

struct CompanionLayout {
    cat: Rect,
    text: Rect,
    buttons: [(CompanionAction, Rect); 2],
}

fn layout(rect: Rect, scale: f32) -> CompanionLayout {
    let scale = scale.min(rect.width() / 240.0).min(rect.height() / 150.0);
    let inset = 24.0 * scale;
    let inner = Rect::from_xywh(
        rect.left + inset,
        rect.top + 20.0 * scale,
        (rect.width() - inset * 2.0).max(1.0),
        (rect.height() - 40.0 * scale).max(1.0),
    );
    let footer_h = 34.0 * scale;
    let gap = 8.0 * scale;
    let small_w = footer_h;
    let chat_w = inner.width() - small_w - gap;
    let y = inner.bottom - footer_h;
    let cat_size = (inner.height() - footer_h - 20.0 * scale)
        .min(96.0 * scale)
        .max(30.0 * scale);
    let cat = Rect::from_xywh(inner.left, inner.top + 6.0 * scale, cat_size, cat_size);
    let text_x = cat.right + 18.0 * scale;
    CompanionLayout {
        cat,
        text: Rect::from_xywh(text_x, cat.top, (inner.right - text_x).max(1.0), cat_size),
        buttons: [
            (
                CompanionAction::Chat,
                Rect::from_xywh(inner.left, y, chat_w, footer_h),
            ),
            (
                CompanionAction::Settings,
                Rect::from_xywh(inner.right - small_w, y, small_w, footer_h),
            ),
        ],
    }
}

pub fn hit_test(rect: Rect, scale: f32, point: Point) -> Option<CompanionAction> {
    let layout = layout(rect, scale);
    layout
        .buttons
        .into_iter()
        .find(|(_, area)| area.contains(point))
        .map(|(action, _)| action)
        .or_else(|| layout.cat.contains(point).then_some(CompanionAction::Pet))
}

pub fn draw_companion_page(params: CompanionPageParams<'_>) -> bool {
    let CompanionPageParams {
        painter,
        rect,
        scale,
        alpha,
        companion,
        playing,
    } = params;
    let layout = layout(rect, scale);
    let s = scale.min(rect.width() / 240.0).min(rect.height() / 150.0);
    let mood = companion.mood(playing);
    if alpha < u8::MAX {
        painter.save_alpha(alpha);
    }
    let dot_color = if mood == PetMood::Error {
        Rgba::from_rgb(235, 132, 123)
    } else if companion.connected() {
        Rgba::from_rgb(161, 198, 167)
    } else {
        ACCENT
    };
    if mood == PetMood::Thinking {
        draw_spinner(
            painter,
            Point::new(layout.text.left + 5.0 * s, layout.text.top + 42.0 * s),
            5.0 * s,
            companion.elapsed(),
        );
    } else {
        painter.fill_circle(
            Point::new(layout.text.left + 4.0 * s, layout.text.top + 42.0 * s),
            3.0 * s,
            dot_color,
        );
    }
    text(
        painter,
        if mood == PetMood::Thinking {
            companion.thinking_label()
        } else {
            companion.status()
        },
        Point::new(layout.text.left + 16.0 * s, layout.text.top + 46.0 * s),
        12.0 * s,
        false,
        dot_color,
        layout.text.width() - 16.0 * s,
    );
    let center = Point::new(layout.cat.center_x(), layout.cat.center_y());
    painter.fill_circle(
        center,
        layout.cat.width() * 0.43,
        Rgba::from_rgba(242, 174, 111, 8),
    );
    painter.fill_oval(
        Rect::from_xywh(
            layout.cat.left + layout.cat.width() * 0.15,
            layout.cat.bottom - 5.0 * s,
            layout.cat.width() * 0.7,
            7.0 * s,
        ),
        Rgba::from_rgba(0, 0, 0, 65),
    );
    draw_cat(painter, layout.cat, mood, companion, u8::MAX);
    if mood == PetMood::Sleep {
        text(
            painter,
            "z z",
            Point::new(layout.cat.right - 14.0 * s, layout.cat.top + 12.0 * s),
            12.0 * s,
            true,
            MUTED,
            28.0 * s,
        );
    }
    text(
        painter,
        companion.name(),
        Point::new(layout.text.left, layout.text.top + 23.0 * s),
        19.0 * s,
        true,
        Rgba::WHITE,
        layout.text.width(),
    );
    let thinking_detail = format!("已等待 {} 秒 · 随时可以停止", companion.thinking_seconds());
    let detail = if mood == PetMood::Thinking {
        thinking_detail.as_str()
    } else if companion.hovered() == Some(CompanionAction::Settings) {
        "打开助手设置"
    } else if companion.hovered() == Some(CompanionAction::Pet) {
        "点一下摸摸，右键切换休息。"
    } else if mood == PetMood::Sleep {
        "休息一下，也陪着你。"
    } else if mood == PetMood::Happy {
        "收到你的摸摸啦。"
    } else if playing && companion.compact_status().is_none() {
        "音乐响了，一起听。"
    } else {
        companion.detail()
    };
    if layout.text.height() >= 70.0 * s {
        let two_lines = layout.text.height() >= 85.0 * s;
        let body_size = (13.0 * s).round();
        let top = (layout.text.top + 58.0 * s).round();
        FontManager::global().draw_plugin_text(
            PluginTextParams {
                painter,
                rect: Rect::from_xywh(
                    layout.text.left.round(),
                    top,
                    layout.text.width(),
                    (if two_lines { 40.0 } else { 23.0 }) * s,
                ),
                size: body_size,
                italic: false,
                family: UI_FONT,
                align: 0,
                wrap: two_lines,
                ellipsis: true,
            },
            detail,
            400,
            MUTED,
        );
    }
    for (action, button) in layout.buttons {
        let hovered = companion.hovered() == Some(action);
        let primary = action == CompanionAction::Chat;
        let fill = if primary {
            if hovered {
                Rgba::from_rgb(255, 193, 138)
            } else {
                ACCENT
            }
        } else if hovered {
            Rgba::from_rgb(53, 47, 43)
        } else {
            Rgba::from_rgb(31, 29, 28)
        };
        painter.fill_round_rect(button, Radius::uniform(10.0 * s), fill);
        if !primary {
            for offset in [-4.0, 0.0, 4.0] {
                painter.fill_circle(
                    Point::new(button.center_x() + offset * s, button.center_y()),
                    1.2 * s,
                    MUTED,
                );
            }
            continue;
        }
        let caption = if mood == PetMood::Thinking {
            "查看进度"
        } else {
            "开始聊天"
        };
        let width = FontManager::global()
            .measure_plugin_text(caption, (12.0 * s).round(), 600, false, UI_FONT)
            .map_or(0.0, |metrics| metrics.width);
        text(
            painter,
            caption,
            Point::new(button.center_x() - width / 2.0, button.center_y() + 4.0 * s),
            12.0 * s,
            primary,
            if primary {
                Rgba::from_rgb(36, 25, 18)
            } else {
                MUTED
            },
            button.width() - 6.0 * s,
        );
        let arrow = Point::new(button.right - 18.0 * s, button.center_y());
        let arrow_color = Rgba::from_rgb(36, 25, 18);
        painter.stroke_line(
            Point::new(arrow.x - 5.0 * s, arrow.y),
            Point::new(arrow.x + 3.0 * s, arrow.y),
            s,
            arrow_color,
            StrokeCap::Round,
        );
        painter.stroke_line(
            Point::new(arrow.x, arrow.y - 3.0 * s),
            Point::new(arrow.x + 3.0 * s, arrow.y),
            s,
            arrow_color,
            StrokeCap::Round,
        );
        painter.stroke_line(
            Point::new(arrow.x, arrow.y + 3.0 * s),
            Point::new(arrow.x + 3.0 * s, arrow.y),
            s,
            arrow_color,
            StrokeCap::Round,
        );
    }
    if alpha < u8::MAX {
        painter.restore();
    }
    matches!(mood, PetMood::Happy | PetMood::Walk | PetMood::Thinking)
}

pub fn draw_companion_mini(
    painter: Painter<'_>,
    rect: Rect,
    scale: f32,
    alpha: u8,
    companion: &Companion,
) {
    if rect.width() < 48.0 * scale || alpha == 0 {
        return;
    }
    let size = (rect.height() - 4.0 * scale).min(24.0 * scale);
    let cat = Rect::from_xywh(
        rect.left + 9.0 * scale,
        rect.center_y() - size / 2.0,
        size,
        size,
    );
    draw_cat(painter, cat, companion.mood(false), companion, alpha);
    let caption = companion
        .compact_status()
        .unwrap_or_else(|| companion.name());
    text(
        painter,
        caption,
        Point::new(cat.right + 7.0 * scale, rect.center_y() + 3.5 * scale),
        10.0 * scale,
        false,
        ACCENT.with_alpha(alpha),
        (rect.right - cat.right - 18.0 * scale).max(1.0),
    );
}

fn draw_spinner(painter: Painter<'_>, center: Point, radius: f32, elapsed: f32) {
    for index in 0..8 {
        let angle = index as f32 * std::f32::consts::TAU / 8.0 + elapsed * 1.6;
        let from = Point::new(
            center.x + angle.cos() * radius * 0.58,
            center.y + angle.sin() * radius * 0.58,
        );
        let to = Point::new(
            center.x + angle.cos() * radius,
            center.y + angle.sin() * radius,
        );
        painter.stroke_line(
            from,
            to,
            (radius * 0.24).max(1.0),
            ACCENT.with_alpha(70 + index * 23),
            StrokeCap::Round,
        );
    }
}

fn draw_cat(painter: Painter<'_>, rect: Rect, mood: PetMood, companion: &Companion, alpha: u8) {
    let elapsed = companion.elapsed();
    let index = usize::from(mood == PetMood::Thinking);
    let offset = match mood {
        PetMood::Thinking => (elapsed * 2.5).sin(),
        PetMood::Happy | PetMood::Walk => (elapsed * 4.0).sin() * 1.5,
        _ => 0.0,
    };
    let destination = Rect::from_xywh(
        rect.left.round(),
        (rect.top + offset).round(),
        rect.width().round(),
        rect.height().round(),
    );
    SPRITES.with_borrow_mut(|cache| {
        let key = companion.image_key();
        if cache
            .as_ref()
            .is_none_or(|(cached_key, _)| *cached_key != key)
        {
            let frames = if companion.pet_id() == "pixel-cat" {
                &PIXEL_FRAME_BYTES
            } else {
                &FRAME_BYTES
            };
            let images = frames
                .iter()
                .enumerate()
                .map(|(index, bytes)| {
                    companion
                        .pet_image_bytes(index == 1)
                        .as_deref()
                        .and_then(Image::decode)
                        .or_else(|| Image::decode(bytes))
                })
                .collect();
            *cache = Some((key, images));
        }
        let Some((_, images)) = cache.as_ref() else {
            return;
        };
        if let Some(image) = images.get(index).and_then(Option::as_ref) {
            painter.draw_image(
                image,
                destination,
                &ImageOptions {
                    fit: ImageFit::Contain,
                    sampling: if companion.pet_id() == "pixel-cat" {
                        Sampling::Default
                    } else {
                        Sampling::LinearLinear
                    },
                    alpha,
                    ..ImageOptions::default()
                },
            );
        }
    });
    if mood == PetMood::Thinking && rect.width() > 48.0 {
        let unit = rect.width() / 100.0;
        for index in 0..3 {
            let pulse = ((elapsed * 3.0 - index as f32 * 0.6).sin() + 1.0) / 2.0;
            painter.fill_circle(
                Point::new(
                    rect.right - 20.0 * unit + index as f32 * 7.0 * unit,
                    rect.top + 3.0 * unit,
                ),
                (1.3 + pulse) * unit,
                ACCENT.with_alpha((110.0 + pulse * 145.0) as u8),
            );
        }
    }
}

fn text(
    painter: Painter<'_>,
    value: &str,
    at: Point,
    size: f32,
    bold: bool,
    color: Rgba,
    width: f32,
) {
    let size = size.round();
    let manager = FontManager::global();
    let Some(metrics) = manager.measure_plugin_text(value, size, 400, false, UI_FONT) else {
        return;
    };
    manager.draw_plugin_text(
        PluginTextParams {
            painter,
            rect: Rect::from_xywh(
                at.x.round(),
                (at.y - metrics.ascent).round(),
                width.max(0.0),
                metrics.height.max(size * 1.1) + 1.0,
            ),
            size,
            italic: false,
            family: UI_FONT,
            align: 0,
            wrap: false,
            ellipsis: true,
        },
        value,
        if bold { 600 } else { 400 },
        color,
    );
}
