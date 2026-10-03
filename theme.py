"""Shared design tokens and Qt stylesheet for BuddyDesk."""

BG_DEEP = "#f6f7f9"
BG_PRIMARY = BG_DEEP
BG_SUBTLE = "#eceff3"
BG_CARD = "#ffffff"
TEXT_PRIMARY = "#222933"
TEXT_SECONDARY = "#4f5967"
TEXT_MUTED = "#667181"
TEXT_META = "#788292"
TEXT_ON_ACCENT = "#ffffff"
ACCENT = "#a96231"
ACCENT_BRIGHT = "#925126"
ACCENT_GLOW = "rgba(169,98,49,0.25)"
ACCENT_SOFT = "rgba(169,98,49,0.10)"
GREEN = "#39805c"
GREEN_GLOW = "rgba(144,185,155,0.20)"
GREEN_SOFT = "rgba(144,185,155,0.10)"
RED = "#b24d4c"
RED_SOFT = "rgba(178,77,76,0.07)"
AMBER = "#e8be81"
AMBER_SOFT = "rgba(232,190,129,0.10)"
GOLD = AMBER
GOLD_SOFT = AMBER_SOFT
DANGER = RED
DANGER_SOFT = RED_SOFT
WHITE = "#ffffff"
WARM_CAT_LIGHT = "#fff8f0"
WARM_CAT_MID = "#fbe9d6"
WARM_CAT_DEEP = "#f7dab8"
WARM_CAT_TEXT = ACCENT
FONT_FAMILY = "'Microsoft YaHei UI', 'Segoe UI', sans-serif"
FONT_MONO = "'Cascadia Code', Consolas, monospace"
SHADOW_SM = "0 1px 2px rgba(0,0,0,0.20)"
SHADOW_MD = "0 4px 16px rgba(28,40,56,0.08)"
SHADOW_LG = "0 8px 28px rgba(28,40,56,0.12)"
SHADOW_INSET = "inset 0 1px 0 rgba(255,255,255,0.04)"
EASE_OUT = "cubic-bezier(0.22, 1, 0.36, 1)"
EASE_SPRING = "cubic-bezier(0.34, 1.56, 0.64, 1)"
BORDER = "#d9dfe7"
BORDER_SUBTLE = "#e5e9ef"
RADIUS_SM = 10
RADIUS_MD = 16
RADIUS_LG = 22
RADIUS_PILL = 9999
ANIM_FADE_MS = 200
ANIM_SPRING_MS = 450
ANIM_EASING_SHOW = "OutCubic"
ANIM_EASING_SPRING = "OutBack"
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
        color: {TEXT_ON_ACCENT};
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
        background-color: {BG_CARD} !important;
        color: {TEXT_PRIMARY} !important;
        selection-background-color: {ACCENT_SOFT} !important;
        selection-color: {ACCENT} !important;
        border: 1px solid {BORDER} !important;
        outline: 0;
        border-radius: {RADIUS_SM}px;
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

    QToolTip {{
        background-color: #f9fafb;
        color: #303640;
        border: 1px solid #d9dfe7;
        border-radius: 6px;
        padding: 5px 8px;
        font-family: "Microsoft YaHei UI";
        font-size: 12px;
    }}

    /* ── Menus ── */
    QCheckBox {{
        background:transparent;
        border:none;
        spacing:8px;
        color:{TEXT_SECONDARY};
    }}
    QCheckBox::indicator {{
        width:15px;
        height:15px;
        border:1px solid {BORDER};
        border-radius:4px;
        background:{BG_SUBTLE};
    }}
    QCheckBox::indicator:checked {{
        background:{ACCENT};
        border-color:{ACCENT};
    }}

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
