"""Colori e stile dell'interfaccia (tema scuro)."""

from string import Template

BG = "#10141A"
SURFACE = "#18202A"
SURFACE2 = "#222C38"
BORDER = "#2C3746"
TEXT = "#E9EDF2"
MUTED = "#8C98A8"
ACCENT = "#34C77B"
ACCENT_DARK = "#06210F"
WARN = "#F5A524"
DANGER = "#F2665C"

KIND_COLORS = {
    "meta": "#34C77B",      # verde
    "calcio": "#4DA3FF",    # azzurro
    "dubbio": "#F5A524",    # ambra
    "manuale": "#B18CFF",   # viola
}


def kind_color(kind: str) -> str:
    return KIND_COLORS.get(kind.split("+")[0], ACCENT)


QSS_TEMPLATE = Template("""
* { font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt; }
QWidget { background: transparent; color: $text; }
QMainWindow, QDialog { background: $bg; }
QScrollArea { background: transparent; border: none; }
QLabel { background: transparent; }
QLabel#title { font-size: 24pt; font-weight: 700; }
QLabel#brand { font-size: 13pt; font-weight: 700; }
QLabel#h2 { font-size: 13pt; font-weight: 600; }
QLabel#muted { color: $muted; }
QLabel#big { font-size: 18pt; font-weight: 700; }
QLabel#plus { font-size: 26pt; color: $accent; background: $surface2; border-radius: 28px;
              min-width: 56px; max-width: 56px; min-height: 56px; max-height: 56px; }
QLabel#stepOn { color: $text; font-weight: 600; }
QLabel#stepOff { color: $muted; }
QLabel#stepDot { background: $surface2; color: $muted; border-radius: 12px;
                 min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; }
QLabel#stepDotOn { background: $accent; color: $accentdark; border-radius: 12px; font-weight: 700;
                   min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; }

QFrame#card { background: $surface; border: 1px solid $border; border-radius: 14px; }
QFrame#banner { background: #2A2412; border: 1px solid #5A4A1A; border-radius: 12px; }
QFrame#drop { background: $surface; border: 2px dashed #3A4659; border-radius: 16px; }
QFrame#drop[hover="true"] { border-color: $accent; background: $surface2; }
QFrame#drop[loaded="true"] { border: 2px solid $accent; }
QFrame#video { background: #000000; border-radius: 12px; }

QPushButton { background: $surface2; border: 1px solid $border; border-radius: 9px;
              padding: 9px 18px; color: $text; }
QPushButton:hover { background: #2B3644; }
QPushButton:pressed { background: #1C2430; }
QPushButton:disabled { color: #5B6675; background: $surface; }
QPushButton#primary { background: $accent; color: $accentdark; border: none; font-weight: 700;
                      padding: 11px 26px; }
QPushButton#primary:hover { background: #46D98C; }
QPushButton#primary:disabled { background: #25473A; color: #6E8F80; }
QPushButton#small { padding: 5px 11px; border-radius: 8px; }
QPushButton#round { border-radius: 16px; padding: 0; min-width: 32px; max-width: 32px;
                    min-height: 32px; max-height: 32px; font-size: 14pt; }
QPushButton#flat { background: transparent; border: none; color: $muted; padding: 6px 4px; }
QPushButton#flat:hover { color: $text; }

QProgressBar { background: $surface2; border: none; border-radius: 6px; min-height: 12px;
               max-height: 12px; text-align: center; color: transparent; }
QProgressBar::chunk { background: $accent; border-radius: 6px; }
QProgressBar[over="true"]::chunk { background: $warn; }

QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { border-radius: 10px; margin: 2px 0; }
QListWidget::item:selected { background: $surface2; }
QListWidget::item:hover:!selected { background: #1E2631; }

QSpinBox, QDoubleSpinBox { background: $surface2; border: 1px solid $border; border-radius: 8px;
                           padding: 6px 10px; min-width: 90px; min-height: 22px; }
QSpinBox:focus, QDoubleSpinBox:focus { border-color: $accent; }

QCheckBox { background: transparent; spacing: 8px; }
QCheckBox::indicator { width: 20px; height: 20px; border-radius: 6px; border: 2px solid #4A586B; }
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent;
                               image: url("$tick"); }

QLineEdit { background: $surface2; border: 1px solid $border; border-radius: 8px; padding: 8px 10px;
            selection-background-color: $accent; selection-color: $accentdark; }
QLineEdit:focus { border-color: $accent; }
QSlider::groove:horizontal { height: 6px; background: $surface2; border-radius: 3px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 3px; }
QSlider::handle:horizontal { background: #FFFFFF; width: 16px; height: 16px; margin: -5px 0;
                             border-radius: 8px; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #324052; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: $surface2; color: $text; border: 1px solid $border; padding: 4px 8px; }
""")


def _tick_icon():
    """Disegna la spunta bianca/scura per le caselle e restituisce il percorso del file."""
    import os
    import tempfile

    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

    path = os.path.join(tempfile.gettempdir(), "rugbyhl_tick.png")
    pm = QPixmap(40, 40)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(ACCENT_DARK), 5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.drawPolyline([QPointF(10, 21), QPointF(17, 28), QPointF(30, 12)])
    p.end()
    pm.save(path)
    return path.replace("\\", "/")


def build_qss():
    """Da chiamare dopo aver creato QApplication."""
    return QSS_TEMPLATE.substitute(
        bg=BG, surface=SURFACE, surface2=SURFACE2, border=BORDER, text=TEXT, muted=MUTED,
        accent=ACCENT, accentdark=ACCENT_DARK, warn=WARN, tick=_tick_icon(),
    )
