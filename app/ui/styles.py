"""Shared professional UI theme for Inventory Transfer Pro."""

from pathlib import Path
from PySide6.QtWidgets import QTableWidget, QHeaderView, QAbstractItemView
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt

# Slate / teal professional palette (high-contrast, light business desktop)
COLORS = {
    "bg": "#eef1f4",
    "surface": "#ffffff",
    "border": "#9aa5b5",
    "border_strong": "#64748b",
    "text": "#0f172a",
    "text_muted": "#334155",
    "primary": "#0f766e",
    "primary_hover": "#0d9488",
    "primary_pressed": "#115e59",
    "secondary": "#1e293b",
    "secondary_hover": "#334155",
    "danger": "#b42318",
    "danger_hover": "#912018",
    "warning": "#b54708",
    "success": "#067647",
    "info": "#175cd3",
    "row_alt": "#f1f5f9",
    "selection": "#0f766e",
    "selection_text": "#ffffff",
    "selection_soft": "#5eead4",
    "header_bg": "#e2e8f0",
    "placeholder": "#475569",
}

_ASSETS = Path(__file__).resolve().parent / "assets"
_SPIN_UP = (_ASSETS / "spin_up.png").as_posix()
_SPIN_DOWN = (_ASSETS / "spin_down.png").as_posix()


def app_stylesheet() -> str:
    c = COLORS
    return f"""
    QWidget {{
        color: {c['text']};
        font-size: 13px;
    }}
    QMainWindow, QDialog {{
        background-color: {c['bg']};
    }}
    QLabel#PageTitle {{
        font-size: 20px;
        font-weight: 700;
        color: {c['text']};
    }}
    QLabel#PageSubtitle {{
        font-size: 12px;
        color: {c['text_muted']};
        font-weight: 500;
    }}
    QLabel#MutedLabel {{
        color: {c['text_muted']};
        font-size: 12px;
        font-weight: 600;
    }}
    QLabel#StatusLabel {{
        color: {c['text']};
        font-size: 12px;
        font-weight: 500;
        padding: 4px 2px;
    }}
    QLabel#CartSummary {{
        font-size: 13px;
        font-weight: 700;
        color: {c['primary_pressed']};
    }}
    QLabel#RouteArrow {{
        font-size: 18px;
        font-weight: 700;
        color: {c['primary']};
        padding: 0 8px;
    }}
    QFrame#ToolbarCard, QFrame#FooterCard, QFrame#RouteCard {{
        background-color: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 8px;
    }}
    QGroupBox {{
        background-color: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        margin-top: 14px;
        padding-top: 12px;
        font-weight: 700;
        color: {c['text']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: {c['text']};
    }}
    QLineEdit, QComboBox, QDateEdit {{
        background-color: {c['surface']};
        color: {c['text']};
        border: 1px solid {c['border_strong']};
        border-radius: 6px;
        padding: 7px 10px;
        min-height: 18px;
        selection-background-color: {c['selection']};
        selection-color: {c['selection_text']};
    }}
    QLineEdit::placeholder {{
        color: {c['placeholder']};
    }}
    QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{
        border: 2px solid {c['primary']};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 28px;
    }}
    QDoubleSpinBox, QSpinBox {{
        background-color: {c['surface']};
        color: {c['text']};
        border: 1px solid {c['border_strong']};
        border-radius: 6px;
        padding: 4px 6px;
        min-height: 22px;
        font-weight: 600;
        selection-background-color: {c['selection']};
        selection-color: {c['selection_text']};
    }}
    QDoubleSpinBox:focus, QSpinBox:focus {{
        border: 2px solid {c['primary']};
    }}
    QDoubleSpinBox::up-button, QSpinBox::up-button,
    QDoubleSpinBox::down-button, QSpinBox::down-button {{
        subcontrol-origin: border;
        width: 22px;
        background-color: {c['secondary']};
        border-left: 1px solid {c['text']};
    }}
    QDoubleSpinBox::up-button, QSpinBox::up-button {{
        subcontrol-position: top right;
        border-top-right-radius: 5px;
    }}
    QDoubleSpinBox::down-button, QSpinBox::down-button {{
        subcontrol-position: bottom right;
        border-bottom-right-radius: 5px;
    }}
    QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
    QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {{
        background-color: {c['primary']};
    }}
    QDoubleSpinBox::up-button:pressed, QSpinBox::up-button:pressed,
    QDoubleSpinBox::down-button:pressed, QSpinBox::down-button:pressed {{
        background-color: {c['primary_pressed']};
    }}
    QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {{
        image: url("{_SPIN_UP}");
        width: 10px;
        height: 10px;
    }}
    QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {{
        image: url("{_SPIN_DOWN}");
        width: 10px;
        height: 10px;
    }}
    QPushButton {{
        background-color: {c['surface']};
        color: {c['text']};
        border: 1px solid {c['border_strong']};
        border-radius: 6px;
        padding: 8px 14px;
        font-weight: 700;
        min-height: 18px;
    }}
    QPushButton:hover {{
        background-color: {c['header_bg']};
        border-color: {c['secondary']};
    }}
    QPushButton:pressed {{
        background-color: {c['border']};
    }}
    QPushButton:disabled {{
        color: #64748b;
        background-color: #f1f5f9;
        border-color: {c['border']};
    }}
    QPushButton#PrimaryButton {{
        background-color: {c['primary']};
        color: white;
        border: 1px solid {c['primary']};
    }}
    QPushButton#PrimaryButton:hover {{
        background-color: {c['primary_hover']};
        border-color: {c['primary_hover']};
    }}
    QPushButton#PrimaryButton:pressed {{
        background-color: {c['primary_pressed']};
    }}
    QPushButton#SecondaryButton {{
        background-color: {c['secondary']};
        color: white;
        border: 1px solid {c['secondary']};
    }}
    QPushButton#SecondaryButton:hover {{
        background-color: {c['secondary_hover']};
    }}
    QPushButton#BackButton {{
        background-color: {c['surface']};
        color: {c['text']};
        border: 1px solid {c['border_strong']};
        font-weight: 700;
        padding: 8px 16px;
        min-width: 150px;
    }}
    QPushButton#BackButton:hover {{
        background-color: {c['header_bg']};
        border-color: {c['primary']};
        color: {c['primary']};
    }}
    QPushButton#DangerButton {{
        background-color: {c['danger']};
        color: white;
        border: 1px solid {c['danger']};
        font-size: 14px;
        padding: 12px 22px;
    }}
    QPushButton#DangerButton:hover {{
        background-color: {c['danger_hover']};
    }}
    QPushButton#GhostDanger {{
        color: {c['danger']};
        border: 1px solid #f97066;
        background-color: #fef3f2;
        padding: 4px 10px;
        font-weight: 700;
    }}
    QPushButton#GhostDanger:hover {{
        background-color: #fee4e2;
    }}
    QTableWidget {{
        background-color: {c['surface']};
        color: {c['text']};
        alternate-background-color: {c['row_alt']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        gridline-color: #cbd5e1;
        selection-background-color: {c['selection']};
        selection-color: {c['selection_text']};
        outline: none;
    }}
    QTableWidget::item:selected {{
        background-color: {c['selection']};
        color: {c['selection_text']};
    }}
    QTableWidget::item:selected:!active {{
        background-color: {c['primary_pressed']};
        color: {c['selection_text']};
    }}
    QListView::item:selected, QTreeView::item:selected {{
        background-color: {c['selection']};
        color: {c['selection_text']};
    }}
    QCalendarWidget QAbstractItemView:enabled {{
        selection-background-color: {c['selection']};
        selection-color: {c['selection_text']};
    }}
    QCalendarWidget QWidget {{
        selection-background-color: {c['selection']};
        selection-color: {c['selection_text']};
    }}
    QHeaderView::section {{
        background-color: {c['header_bg']};
        color: {c['text']};
        padding: 8px 10px;
        border: none;
        border-right: 1px solid {c['border']};
        border-bottom: 1px solid {c['border']};
        font-weight: 700;
    }}
    QTabWidget::pane {{
        border: 1px solid {c['border']};
        border-radius: 8px;
        background: {c['surface']};
        top: -1px;
    }}
    QTabBar::tab {{
        background: {c['header_bg']};
        border: 1px solid {c['border']};
        border-bottom: none;
        padding: 9px 16px;
        margin-right: 2px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        color: {c['text']};
        font-weight: 700;
    }}
    QTabBar::tab:selected {{
        background: {c['surface']};
        color: {c['primary_pressed']};
        border-bottom: 2px solid {c['primary']};
    }}
    QTabBar::tab:!selected {{
        color: {c['text_muted']};
    }}
    QSplitter::handle {{
        background: {c['border_strong']};
        width: 2px;
    }}
    QStatusBar {{
        background: {c['surface']};
        border-top: 1px solid {c['border']};
    }}
    QFrame#StatCard {{
        background-color: {c['surface']};
        border: 1px solid {c['border_strong']};
        border-radius: 8px;
    }}
    """


def configure_table(table: QTableWidget, stretch_last: bool = True):
    """Apply consistent table behavior for professional UX."""
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSortingEnabled(True)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.setFocusPolicy(Qt.StrongFocus)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.ElideRight)
    table.verticalHeader().setDefaultSectionSize(34)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setStretchLastSection(stretch_last)
    header.setSectionResizeMode(QHeaderView.Interactive)
    header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)


def title_font() -> QFont:
    font = QFont()
    font.setPointSize(14)
    font.setBold(True)
    return font


def status_color(status: str) -> QColor:
    s = (status or "").lower()
    if "out" in s:
        return QColor(COLORS["danger"])
    if "low" in s:
        return QColor(COLORS["warning"])
    if "over" in s or "surplus" in s or "recommended" in s:
        return QColor(COLORS["info"])
    if "healthy" in s or "balanced" in s:
        return QColor(COLORS["success"])
    return QColor(COLORS["text"])
