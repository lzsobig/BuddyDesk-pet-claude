"""
Design tokens + global QSS — BuddyDesk Light Theme.

Single source of truth for the visual system. All windows use the global
QSS from get_stylesheet(); per-widget setStyleSheet calls are limited to
small layout adjustments (margins, spacing) and never to backgrounds or
borders, which would re-introduce QSS color leakage we just removed.
"""

# ── Background layers (warm light) ──
BG_DEEP = "#f8f6f1"        # page background
BG_PRIMARY = "#f8f6f1"     # alias
BG_SUBTLE = "#f2efe9"       # subtle surfaces (input fields, badges)
BG_CARD = "#ffffff"        # raised cards
BG_CARD2 = "#ffffff"
BG_CARD3 = "#e8e5dd"

# ── Text hierarchy ──
TEXT_PRIMARY = "#2a2a28"
TEXT_SECONDARY = "#4a4a46"
TEXT_MUTED = "#9a978e"
TEXT_META = "#b5b2a8"
TEXT_ON_ACCENT = "#ffffff"

# ── Accents ──
ACCENT = "#5cb89a"          # primary sage green
ACCENT_BRIGHT = "#4aaf88"
ACCENT_GLOW = "rgba(92,184,154,0.25)"
ACCENT_SOFT = "rgba(92,184,154,0.10)"
GREEN = "#4aaf88"
GREEN_GLOW = "rgba(74,175,136,0.20)"
GREEN_SOFT = "rgba(74,175,136,0.08)"
RED = "#d47a72"
RED_SOFT = "rgba(212,122,114,0.08)"
AMBER = "#b8a66a"
AMBER_SOFT = "rgba(184,166,106,0.10)"
GOLD = "#b8a66a"
GOLD_SOFT = "rgba(184,166,106,0.10)"
# DANGER — error/warning state (slightly more saturated than RED)
DANGER = "#d47a72"
DANGER_SOFT = "rgba(212,122,114,0.10)"
WHITE = "#ffffff"

# ── Warm cat-tone accents (mascot only) ──
WARM_CAT_LIGHT = "#fff7e6"
WARM_CAT_MID = "#fef3d6"
WARM_CAT_DEEP = "#ffe8b8"
WARM_CAT_TEXT = "#c8845e"

# ── Typography ──
FONT_FAMILY = "'Inter', 'Noto Sans SC', 'Segoe UI', system-ui, sans-serif"
FONT_MONO = "'JetBrains Mono', 'Cascadia Code', Consolas, monospace"

# ── Shadow tiers (used as QSS box-shadow / QGraphicsDropShadowEffect) ──
SHADOW_SM = "0 1px 2px rgba(0,0,0,0.04)"
SHADOW_MD = "0 2px 4px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.06)"
SHADOW_LG = "0 4px 8px rgba(0,0,0,0.06), 0 8px 28px rgba(0,0,0,0.10)"
SHADOW_INSET = "inset 0 1px 0 rgba(255,255,255,0.8)"

# ── Easing curves (informational; used as QSS cubic-bezier strings) ──
EASE_OUT = "cubic-bezier(0.22, 1, 0.36, 1)"
EASE_SPRING = "cubic-bezier(0.34, 1.56, 0.64, 1)"

# ── Border ──
BORDER = "#e8e5dd"
BORDER_SUBTLE = "#efede6"

# ── Radius (统一圆角) ──
RADIUS_SM = 10       # small chips, badges
RADIUS_MD = 16       # cards, inputs, list items (was 14)
RADIUS_LG = 22       # primary button (was 20)
RADIUS_PILL = 9999

# ── Sizing ──
BTN_HEIGHT_PRIMARY = 48
BTN_HEIGHT_SECONDARY = 40
INPUT_HEIGHT = 44


def get_stylesheet() -> str:
    """Single global QSS — every widget pulls from this. No per-widget backgrounds."""
    return f"""
    /* ── Reset ── */
    * {{
        font-family: {FONT_FAMILY};
    }}

    /* ── Base ── */
    QWidget {{
        background-color: {BG_DEEP};
        color: {TEXT_PRIMARY};
        font-size: 14px;
    }}

    QDialog {{
        background-color: {BG_DEEP};
    }}

    /* ── Labels ── */
    QLabel {{
        color: {TEXT_PRIMARY};
        background: transparent;
        border: none;
    }}

    /* ── Frames (cards, dividers, sections) ── */
    QFrame {{
        background: transparent;
        border: none;
    }}

    /* ── Buttons ── */
    QPushButton {{
        background-color: {BG_CARD};
        color: {TEXT_SECONDARY};
        border: 1.5px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        padding: 10px 20px;
        font-weight: 500;
        font-size: 13px;
    }}
    QPushButton:hover {{
        border-color: {ACCENT};
        color: {ACCENT};
        background: {ACCENT_SOFT};
    }}
    QPushButton:pressed {{
        background: {ACCENT};
        color: {WHITE};
    }}

    /* ── Inputs ── */
    QLineEdit {{
        background-color: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1.5px solid {BORDER};
        border-radius: {RADIUS_MD}px;
        padding: 10px 14px;
        font-size: 13px;
        selection-background-color: {ACCENT_SOFT};
        min-height: {INPUT_HEIGHT - 22}px;
    }}
    QLineEdit:focus {{
        border-color: {ACCENT};
    }}

    QPlainTextEdit {{
        background-color: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1.5px solid {BORDER};
        border-radius: {RADIUS_MD}px;
        padding: 10px 14px;
        font-size: 13px;
        font-family: {FONT_FAMILY};
        selection-background-color: {ACCENT_SOFT};
    }}
    QPlainTextEdit:focus {{
        border-color: {ACCENT};
    }}

    /* ── ComboBox ── */
    QComboBox {{
        background-color: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1.5px solid {BORDER};
        border-radius: {RADIUS_MD}px;
        padding: 8px 14px;
        font-size: 13px;
        min-height: {INPUT_HEIGHT - 22}px;
    }}
    QComboBox:hover {{
        border-color: {ACCENT};
    }}
    QComboBox:focus {{
        border-color: {ACCENT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_CARD};
        color: {TEXT_PRIMARY};
        selection-background-color: {ACCENT_SOFT};
        selection-color: {ACCENT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        outline: 0;
    }}

    /* ── Radio buttons (drawn as 20x20 circles) ── */
    QRadioButton {{
        color: {TEXT_PRIMARY};
        spacing: 8px;
        font-size: 13px;
        background: transparent;
        border: none;
    }}
    QRadioButton::indicator {{
        width: 20px;
        height: 20px;
        border-radius: 10px;
        border: 2px solid {BORDER};
        background: {BG_CARD};
    }}
    QRadioButton::indicator:hover {{
        border-color: {ACCENT};
    }}
    QRadioButton::indicator:checked {{
        border: 2px solid {ACCENT};
        background: {ACCENT};
    }}

    /* ── Scrollbar ── */
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER};
        border-radius: 3px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {TEXT_MUTED};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}

    QScrollArea {{
        background: transparent;
        border: none;
    }}

    /* ── Menus ── */
    QMenu {{
        background-color: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        padding: 6px 0;
    }}
    QMenu::item {{
        padding: 8px 24px;
        border-radius: 6px;
        margin: 2px 6px;
    }}
    QMenu::item:selected {{
        background-color: {ACCENT_SOFT};
        color: {ACCENT};
    }}

    /* ── List view (used by chat message list) ── */
    QListView {{
        background-color: {BG_DEEP};
        border: none;
        outline: 0;
        padding: 0;
    }}
    QListView::item {{
        background: transparent;
        border: none;
        padding: 0;
    }}
    """
