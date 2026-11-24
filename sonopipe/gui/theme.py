"""
Material Design 3 (MD3) tonal color tokens and shared QSS helpers for Sonopipe.
"""

from __future__ import annotations

MD3 = {
    # Surfaces (tonal elevation instead of heavy shadows)
    "surface": "#111318",
    "surface_dim": "#0D0F14",
    "surface_container_low": "#191C22",
    "surface_container": "#1D2026",
    "surface_container_high": "#272A31",
    "surface_container_highest": "#32353D",

    # Content
    "on_surface": "#E3E2E9",
    "on_surface_variant": "#C4C6D0",
    "muted": "#8E9099",

    # Outlines
    "outline": "#8E9099",
    "outline_variant": "#3D414A",

    # Primary (Ocean Sky MD3 tonal family)
    "primary": "#8CD0FF",
    "on_primary": "#00344D",
    "primary_container": "#004C6E",
    "on_primary_container": "#C7E7FF",

    # Secondary
    "secondary": "#B6C9D8",
    "secondary_container": "#374955",
    "on_secondary_container": "#D2E5F4",

    # Semantic / Status
    "success": "#7DD8A6",
    "success_container": "#0D4D30",
    "on_success_container": "#B7F3CE",

    "warning": "#F5C469",
    "error": "#FFB4AB",
    "error_container": "#93000A",
    "on_error_container": "#FFDAD6",

    # Typography
    "font_sans": '"Roboto", "Noto Sans", "Segoe UI", sans-serif',
    "font_mono": '"JetBrains Mono", "Roboto Mono", "Fira Code", monospace',
}


def md3_base_stylesheet() -> str:
    """Shared MD3 dark-theme stylesheet for windows and dialogs."""
    c = MD3
    return f"""
        QMainWindow, QDialog {{
            background-color: {c['surface']};
            color: {c['on_surface']};
            font-family: {c['font_sans']};
        }}
        QWidget {{
            color: {c['on_surface']};
            font-family: {c['font_sans']};
        }}
        QLabel {{
            color: {c['on_surface']};
        }}
        QLineEdit, QSpinBox, QComboBox {{
            background-color: {c['surface_container_high']};
            color: {c['on_surface']};
            border: 1px solid {c['outline_variant']};
            border-radius: 12px;
            padding: 8px 12px;
            font-size: 13px;
            selection-background-color: {c['primary_container']};
            selection-color: {c['on_primary_container']};
        }}
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
            border: 1px solid {c['primary']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {c['surface_container_high']};
            color: {c['on_surface']};
            border: 1px solid {c['outline_variant']};
            border-radius: 12px;
            padding: 6px;
            selection-background-color: {c['primary_container']};
            selection-color: {c['on_primary_container']};
            outline: none;
        }}
        QTabWidget::pane {{
            background-color: {c['surface_container']};
            border: 1px solid {c['outline_variant']};
            border-radius: 16px;
            padding: 12px;
            top: -1px;
        }}
        QTabBar::tab {{
            background-color: transparent;
            color: {c['on_surface_variant']};
            padding: 10px 18px;
            margin-right: 4px;
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
            font-weight: 600;
            font-size: 12px;
        }}
        QTabBar::tab:hover {{
            background-color: {c['surface_container_low']};
            color: {c['on_surface']};
        }}
        QTabBar::tab:selected {{
            background-color: {c['secondary_container']};
            color: {c['on_secondary_container']};
        }}
        QMenu {{
            background-color: {c['surface_container_high']};
            color: {c['on_surface']};
            border: 1px solid {c['outline_variant']};
            border-radius: 14px;
            padding: 6px;
        }}
        QMenu::item {{
            padding: 9px 16px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 500;
        }}
        QMenu::item:selected {{
            background-color: {c['primary_container']};
            color: {c['on_primary_container']};
        }}
        QMenu::separator {{
            height: 1px;
            background: {c['outline_variant']};
            margin: 6px 10px;
        }}
        QScrollArea {{
            border: none;
            background: transparent;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 6px;
            margin: 4px 0;
        }}
        QScrollBar::handle:vertical {{
            background: {c['outline_variant']};
            border-radius: 3px;
            min-height: 24px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
    """
