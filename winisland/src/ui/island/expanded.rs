use crate::core::smtc::MediaInfo;
use crate::ui::expanded::calendar_view::draw_calendar_page;
use crate::ui::expanded::music_view::{DrawMusicPageParams, draw_music_page};
use crate::ui::expanded::pager::ExpandedPage;
use crate::ui::expanded::widget_view::draw_widget_page;
use std::collections::HashMap;
use winisland_core::config::{PluginWidgetSlot, WidgetSlot};
use winisland_plugin_host::draw::replay::PreparedFrame;
use winisland_plugin_host::host::PluginHost;
use winisland_render::{BlurSpec, LayerSpec, Painter, Rect, Rgba, Vec2};

pub(super) struct ExpandedContentParams<'a> {
    pub(super) companion: &'a crate::core::companion::Companion,
    pub(super) painter: Painter<'a>,
    pub(super) blur_filter: Option<BlurSpec>,
    pub(super) expanded_alpha: f32,
    pub(super) pages: &'a [ExpandedPage],
    pub(super) view_offset: f32,
    pub(super) current_w: f32,
    pub(super) offset_x: f32,
    pub(super) offset_y: f32,
    pub(super) current_h: f32,
    pub(super) media: &'a MediaInfo,
    pub(super) music_active: bool,
    pub(super) available_controls: u32,
    pub(super) global_scale: f32,
    pub(super) expansion_progress: f32,
    pub(super) viz_h_scale: f32,
    pub(super) use_blur: bool,
    pub(super) font_size: f32,
    pub(super) dt: f32,
    pub(super) expanded_width: f32,
    pub(super) expanded_height: f32,
    pub(super) text_color: Rgba,
    pub(super) text_color_sec: Rgba,
    pub(super) palette: &'a [Rgba],
    pub(super) widget_layout: &'a [WidgetSlot],
    pub(super) plugin_widget_layout: &'a [PluginWidgetSlot],
    pub(super) plugin_widgets: &'a winisland_core::widgets::WidgetManager,
    pub(super) plugin_frames: &'a HashMap<u64, PreparedFrame>,
    pub(super) plugin_host: Option<&'a PluginHost>,
}

pub(super) fn draw_expanded_content(params: ExpandedContentParams<'_>) -> bool {
    let ExpandedContentParams {
        companion,
        painter,
        blur_filter,
        expanded_alpha: expanded_alpha_f,
        pages,
        view_offset,
        current_w,
        offset_x,
        offset_y,
        current_h,
        media,
        music_active,
        available_controls,
        global_scale,
        expansion_progress,
        viz_h_scale,
        use_blur,
        font_size,
        dt,
        expanded_width,
        expanded_height,
        text_color,
        text_color_sec,
        palette,
        widget_layout,
        plugin_widget_layout,
        plugin_widgets,
        plugin_frames,
        plugin_host,
    } = params;
    let mut widget_animating = false;
    if expanded_alpha_f > 0.01 {
        let alpha = (expanded_alpha_f * 255.0) as u8;
        painter.save();
        painter.clip_rect(Rect::from_xywh(offset_x, offset_y, current_w, current_h));

        for (index, page) in pages.iter().enumerate() {
            let distance = index as f32 - view_offset;
            if distance.abs() >= 1.0 {
                continue;
            }
            painter.save();
            painter.translate(Vec2::new(distance * current_w, 0.0));
            let page_blur = blur_filter.filter(|_| *page != ExpandedPage::Companion);
            if let Some(filter) = page_blur {
                painter.begin_layer(LayerSpec::Blur(filter));
            }
            match page {
                ExpandedPage::Companion => {
                    widget_animating |= crate::ui::expanded::companion_view::draw_companion_page(
                        crate::ui::expanded::companion_view::CompanionPageParams {
                            painter,
                            rect: winisland_render::Rect::from_xywh(
                                offset_x, offset_y, current_w, current_h,
                            ),
                            scale: global_scale,
                            alpha,
                            companion,
                            playing: media.is_playing,
                        },
                    );
                }
                ExpandedPage::Music => draw_music_page(DrawMusicPageParams {
                    painter,
                    ox: offset_x,
                    oy: offset_y,
                    w: current_w,
                    alpha,
                    media,
                    music_active,
                    available_controls,
                    scale: global_scale,
                    expansion_progress,
                    viz_h_scale: viz_h_scale * global_scale,
                    use_blur,
                    font_size,
                    dt,
                    text_color,
                    text_color_sec,
                    palette,
                }),
                ExpandedPage::Widgets => {
                    widget_animating |= draw_widget_page(
                        painter,
                        offset_x,
                        offset_y,
                        current_w,
                        current_h,
                        alpha,
                        global_scale,
                        expanded_width,
                        expanded_height,
                        widget_layout,
                        plugin_widget_layout,
                        plugin_widgets,
                        plugin_frames,
                        plugin_host,
                        text_color,
                    );
                }
                ExpandedPage::Calendar => draw_calendar_page(
                    painter,
                    offset_x,
                    offset_y,
                    current_w,
                    current_h,
                    alpha,
                    global_scale,
                    text_color,
                ),
            }
            if page_blur.is_some() {
                painter.restore();
            }
            painter.restore();
        }

        painter.restore();
    }
    widget_animating
}
