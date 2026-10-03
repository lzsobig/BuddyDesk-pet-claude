use super::{draw_widget_rounded_background, draw_widget_text_centered};
use crate::ui::widget::time_text::with_current_time_text;
use winisland_render::{Painter, Rect, Rgba};

#[allow(clippy::too_many_arguments)]
pub fn draw_time_widget(
    painter: Painter<'_>,
    x: f32,
    y: f32,
    w: f32,
    h: f32,
    scale: f32,
    alpha: u8,
    text_color: Rgba,
) {
    draw_widget_rounded_background(painter, x, y, w, h, scale, alpha);

    let large = h > 80.0 * scale;
    let size = (h * 0.60).min(w * 0.27).max(6.0 * scale);
    let color = text_color.with_alpha(alpha);

    with_current_time_text(|text| {
        draw_widget_text_centered(
            painter,
            text,
            Rect::from_xywh(x, y, w, if large { h * 0.76 } else { h }),
            size,
            true,
            color,
        );
    });
    if large {
        let date_time = crate::platform::shell().local_datetime();
        let date = format!("{:02} / {:02}", date_time.month, date_time.day);
        draw_widget_text_centered(
            painter,
            &date,
            Rect::from_xywh(x, y + h * 0.65, w, h * 0.2),
            (h * 0.10).min(11.0 * scale),
            false,
            color.with_alpha((alpha as f32 * 0.48) as u8),
        );
    }
}
