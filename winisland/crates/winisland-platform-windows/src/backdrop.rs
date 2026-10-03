use std::cell::{OnceCell, RefCell};
use std::sync::Arc;

use windows::{
    System::DispatcherQueueController,
    UI::Composition::Desktop::DesktopWindowTarget,
    UI::Composition::{
        CompositionBackdropBrush, CompositionGeometricClip, CompositionRoundedRectangleGeometry,
        Compositor, ContainerVisual, SpriteVisual,
    },
    Win32::{
        Foundation::HWND,
        System::WinRT::{
            Composition::ICompositorDesktopInterop, CreateDispatcherQueueController,
            DQTAT_COM_NONE, DQTYPE_THREAD_CURRENT, DispatcherQueueOptions,
        },
        UI::WindowsAndMessaging::{
            SWP_HIDEWINDOW, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SWP_SHOWWINDOW,
            SetWindowPos,
        },
    },
    core::Interface,
};
use windows_numerics::{Vector2, Vector3};
use winisland_platform::{BackdropShape, HostBackdropParams};
use winit::{
    raw_window_handle::{HasWindowHandle, RawWindowHandle},
    window::Window,
};

use crate::window::styles::enable_host_backdrop;

const HOST_BACKDROP_INSET: f32 = 1.0;

struct BackdropCompositionContext {
    _dispatcher_queue: DispatcherQueueController,
    compositor: Compositor,
}

struct ClippedVisual {
    visual: SpriteVisual,
    _clip: CompositionGeometricClip,
    geometry: CompositionRoundedRectangleGeometry,
}

pub(crate) struct HostBackdrop {
    _window: Arc<Window>,
    main_hwnd: HWND,
    backdrop_hwnd: HWND,
    target: DesktopWindowTarget,
    _root: ContainerVisual,
    primary: ClippedVisual,
    extras: [ClippedVisual; 2],
    last_geometry: RefCell<Option<BackdropGeometry>>,
}

#[derive(Clone, Copy, PartialEq)]
struct ShapeGeometry {
    x: f32,
    y: f32,
    width: f32,
    height: f32,
    radius: f32,
    opacity: f32,
}

#[derive(Clone, Copy, PartialEq)]
struct BackdropGeometry {
    screen_x: i32,
    screen_y: i32,
    window_width: i32,
    window_height: i32,
    primary: Option<ShapeGeometry>,
    extras: [Option<ShapeGeometry>; 2],
}

thread_local! {
    static BACKDROP_COMPOSITION: OnceCell<Option<BackdropCompositionContext>> = const { OnceCell::new() };
}

fn quantize(value: f32) -> f32 {
    (value * 16.0).round() / 16.0
}

impl ClippedVisual {
    fn new(
        compositor: &Compositor,
        brush: &CompositionBackdropBrush,
        root: &ContainerVisual,
    ) -> Result<Self, String> {
        let visual = compositor
            .CreateSpriteVisual()
            .map_err(|error| format!("CreateSpriteVisual failed: {error}"))?;
        let geometry = compositor
            .CreateRoundedRectangleGeometry()
            .map_err(|error| format!("CreateRoundedRectangleGeometry failed: {error}"))?;
        let clip = compositor
            .CreateGeometricClipWithGeometry(&geometry)
            .map_err(|error| format!("CreateGeometricClipWithGeometry failed: {error}"))?;
        visual
            .SetBrush(brush)
            .map_err(|error| format!("Host backdrop brush assignment failed: {error}"))?;
        visual
            .SetClip(&clip)
            .map_err(|error| format!("Host backdrop clip assignment failed: {error}"))?;
        visual
            .SetIsVisible(false)
            .map_err(|error| format!("Host backdrop visibility setup failed: {error}"))?;
        root.Children()
            .and_then(|children| children.InsertAtTop(&visual))
            .map_err(|error| format!("Host backdrop visual insertion failed: {error}"))?;
        Ok(Self {
            visual,
            _clip: clip,
            geometry,
        })
    }

    fn apply(&self, shape: Option<ShapeGeometry>) -> windows::core::Result<()> {
        let Some(shape) = shape else {
            return self.visual.SetIsVisible(false);
        };
        self.visual.SetOffset(Vector3 {
            X: shape.x,
            Y: shape.y,
            Z: 0.0,
        })?;
        let size = Vector2 {
            X: shape.width,
            Y: shape.height,
        };
        self.visual.SetSize(size)?;
        self.geometry.SetSize(size)?;
        self.geometry.SetCornerRadius(Vector2 {
            X: shape.radius,
            Y: shape.radius,
        })?;
        self.visual.SetOpacity(shape.opacity)?;
        self.visual.SetIsVisible(true)
    }
}

impl HostBackdrop {
    pub(crate) fn new(main_window: &Window, backdrop_window: &Arc<Window>) -> Result<Self, String> {
        let compositor = backdrop_compositor()
            .ok_or_else(|| "Windows host backdrop compositor is unavailable".to_string())?;
        let main_hwnd = window_hwnd(main_window)?;
        let backdrop_hwnd = window_hwnd(backdrop_window)?;
        if !enable_host_backdrop(backdrop_hwnd) {
            return Err("DWM host backdrop support could not be enabled".to_string());
        }
        let interop: ICompositorDesktopInterop = compositor
            .cast()
            .map_err(|error| format!("ICompositorDesktopInterop is unavailable: {error}"))?;
        let target = unsafe {
            // SAFETY: backdrop_hwnd belongs to the companion window and has no other composition tree.
            interop.CreateDesktopWindowTarget(backdrop_hwnd, false)
        }
        .map_err(|error| format!("CreateDesktopWindowTarget failed: {error}"))?;
        let root = compositor
            .CreateContainerVisual()
            .map_err(|error| format!("CreateContainerVisual failed: {error}"))?;
        let brush = compositor
            .CreateHostBackdropBrush()
            .map_err(|error| format!("CreateHostBackdropBrush failed: {error}"))?;
        let primary = ClippedVisual::new(&compositor, &brush, &root)?;
        let extras = [
            ClippedVisual::new(&compositor, &brush, &root)?,
            ClippedVisual::new(&compositor, &brush, &root)?,
        ];
        target
            .SetRoot(&root)
            .map_err(|error| format!("Host backdrop root assignment failed: {error}"))?;
        Ok(Self {
            _window: backdrop_window.clone(),
            main_hwnd,
            backdrop_hwnd,
            target,
            _root: root,
            primary,
            extras,
            last_geometry: RefCell::new(None),
        })
    }

    pub(crate) fn update(&self, params: HostBackdropParams) -> windows::core::Result<()> {
        let primary = (params.enabled && params.width > 0.0 && params.height > 0.0).then_some(
            BackdropShape {
                screen_x: params.screen_x,
                screen_y: params.screen_y,
                width: params.width,
                height: params.height,
                radius: params.radius,
                opacity: 1.0,
            },
        );
        let extras = params.extras.map(|shape| {
            shape.filter(|shape| shape.width > 0.0 && shape.height > 0.0 && shape.opacity > 0.0)
        });
        let mut bounds = std::iter::once(primary)
            .chain(extras)
            .flatten()
            .map(|shape| {
                (
                    shape.screen_x,
                    shape.screen_y,
                    shape.screen_x + shape.width,
                    shape.screen_y + shape.height,
                )
            });
        let Some(first) = bounds.next() else {
            self.hide();
            return Ok(());
        };
        let (left, top, right, bottom) = bounds.fold(first, |acc, shape| {
            (
                acc.0.min(shape.0),
                acc.1.min(shape.1),
                acc.2.max(shape.2),
                acc.3.max(shape.3),
            )
        });
        let screen_x = left.floor();
        let screen_y = top.floor();
        let place = |shape: BackdropShape| ShapeGeometry {
            x: quantize(shape.screen_x - screen_x + HOST_BACKDROP_INSET),
            y: quantize(shape.screen_y - screen_y + HOST_BACKDROP_INSET),
            width: quantize((shape.width - HOST_BACKDROP_INSET * 2.0).max(0.0)),
            height: quantize((shape.height - HOST_BACKDROP_INSET * 2.0).max(0.0)),
            radius: quantize((shape.radius - HOST_BACKDROP_INSET).max(0.0)),
            opacity: quantize(shape.opacity.clamp(0.0, 1.0)),
        };
        let geometry = BackdropGeometry {
            screen_x: screen_x as i32,
            screen_y: screen_y as i32,
            window_width: (right - screen_x).ceil().max(1.0) as i32,
            window_height: (bottom - screen_y).ceil().max(1.0) as i32,
            primary: primary.map(place),
            extras: extras.map(|shape| shape.map(place)),
        };
        if self.last_geometry.borrow().as_ref() == Some(&geometry) {
            return Ok(());
        }
        self.primary.apply(geometry.primary)?;
        for (visual, shape) in self.extras.iter().zip(geometry.extras) {
            visual.apply(shape)?;
        }
        unsafe {
            // SAFETY: Both HWND values belong to live windows on this thread. Placing the backdrop
            // immediately behind the owned foreground window preserves z-order without activation.
            SetWindowPos(
                self.backdrop_hwnd,
                Some(self.main_hwnd),
                geometry.screen_x,
                geometry.screen_y,
                geometry.window_width,
                geometry.window_height,
                SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )?;
        }
        *self.last_geometry.borrow_mut() = Some(geometry);
        Ok(())
    }

    pub(crate) fn hide(&self) {
        if self.last_geometry.borrow_mut().take().is_none() {
            return;
        }
        let _ = self.primary.visual.SetIsVisible(false);
        for extra in &self.extras {
            let _ = extra.visual.SetIsVisible(false);
        }
        unsafe {
            // SAFETY: The backdrop HWND remains owned by `_window`; this only hides it.
            let _ = SetWindowPos(
                self.backdrop_hwnd,
                None,
                0,
                0,
                0,
                0,
                SWP_HIDEWINDOW | SWP_NOACTIVATE | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER,
            );
        }
    }
}

impl Drop for HostBackdrop {
    fn drop(&mut self) {
        self.hide();
        let _ = self.target.Close();
    }
}

fn backdrop_compositor() -> Option<Compositor> {
    BACKDROP_COMPOSITION.with(|cell| {
        cell.get_or_init(|| match create_backdrop_composition_context() {
            Ok(context) => Some(context),
            Err(error) => {
                log::warn!("Windows host backdrop initialization failed: {error}");
                None
            }
        })
        .as_ref()
        .map(|context| context.compositor.clone())
    })
}

fn create_backdrop_composition_context() -> Result<BackdropCompositionContext, String> {
    let options = DispatcherQueueOptions {
        dwSize: size_of::<DispatcherQueueOptions>() as u32,
        threadType: DQTYPE_THREAD_CURRENT,
        apartmentType: DQTAT_COM_NONE,
    };
    let dispatcher_queue = unsafe {
        // SAFETY: winit initializes the main thread's STA before renderer creation. The options
        // attach a dispatcher queue to that current thread without changing its COM apartment.
        CreateDispatcherQueueController(options)
    }
    .map_err(|error| format!("CreateDispatcherQueueController failed: {error}"))?;
    let compositor = Compositor::new().map_err(|error| format!("Compositor failed: {error}"))?;
    Ok(BackdropCompositionContext {
        _dispatcher_queue: dispatcher_queue,
        compositor,
    })
}

fn window_hwnd(window: &Window) -> Result<HWND, String> {
    let handle = window
        .window_handle()
        .map_err(|error| format!("Window handle unavailable: {error}"))?;
    match handle.as_raw() {
        RawWindowHandle::Win32(handle) => Ok(HWND(handle.hwnd.get() as _)),
        _ => Err("Host backdrop requires a Win32 window".to_string()),
    }
}
