"""Componenti grafici riutilizzabili."""

import numpy as np
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from . import theme
from .theme import kind_color


def fmt_time(t, decimals=False):
    t = max(0.0, float(t))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    sec = f"{s:04.1f}" if decimals else f"{int(s):02d}"
    if h >= 1:
        return f"{int(h)}:{int(m):02d}:{sec}"
    return f"{int(m)}:{sec}"


def repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


# ----------------------------------------------------------------------------------
class Stepper(QWidget):
    """Numero con pulsanti - e +."""
    changed = Signal(int)

    def __init__(self, label, maximum=30):
        super().__init__()
        self._v, self._max = 0, maximum
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        name = QLabel(label)
        name.setObjectName("muted")
        self.minus = QPushButton("−")
        self.plus = QPushButton("+")
        for b in (self.minus, self.plus):
            b.setObjectName("round")
            b.setCursor(Qt.PointingHandCursor)
        self.lbl = QLabel("0")
        self.lbl.setObjectName("big")
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setMinimumWidth(36)
        lay.addWidget(name, 1)
        lay.addWidget(self.minus)
        lay.addWidget(self.lbl)
        lay.addWidget(self.plus)
        self.minus.clicked.connect(lambda: self.setValue(self._v - 1))
        self.plus.clicked.connect(lambda: self.setValue(self._v + 1))

    def value(self):
        return self._v

    def setValue(self, v):
        v = max(0, min(self._max, int(v)))
        if v != self._v:
            self._v = v
            self.lbl.setText(str(v))
            self.changed.emit(v)


class NumberStepper(QWidget):
    """Valore con pulsanti - e +, con passo, limiti e unita' (es. secondi)."""
    changed = Signal(int)

    def __init__(self, value, lo, hi, step=1, suffix=""):
        super().__init__()
        self._lo, self._hi, self._step, self._suffix = lo, hi, step, suffix
        self._v = max(lo, min(hi, value))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.minus, self.plus = QPushButton("−"), QPushButton("+")
        for b in (self.minus, self.plus):
            b.setObjectName("round")
            b.setCursor(Qt.PointingHandCursor)
        self.lbl = QLabel()
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setMinimumWidth(64)
        self.lbl.setStyleSheet("font-weight:600;")
        lay.addWidget(self.minus)
        lay.addWidget(self.lbl)
        lay.addWidget(self.plus)
        self.minus.clicked.connect(lambda: self.setValue(self._v - self._step))
        self.plus.clicked.connect(lambda: self.setValue(self._v + self._step))
        self._show()

    def _show(self):
        self.lbl.setText(f"{self._v}{self._suffix}")

    def value(self):
        return self._v

    def setValue(self, v):
        v = max(self._lo, min(self._hi, int(v)))
        if v != self._v:
            self._v = v
            self._show()
            self.changed.emit(v)


# ----------------------------------------------------------------------------------
class DropArea(QFrame):
    """Zona dove trascinare il video, oppure cliccare per sceglierlo."""
    fileChosen = Signal(str)
    EXT = "Video (*.mp4 *.mov *.mkv *.avi *.mts *.m2ts *.mpg *.mpeg *.wmv *.m4v);;Tutti i file (*.*)"

    def __init__(self):
        super().__init__()
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(170)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(6)
        self.icon = QLabel("+")
        self.icon.setObjectName("plus")
        self.icon.setAlignment(Qt.AlignCenter)
        self.title = QLabel("Trascina qui il video della partita")
        self.title.setObjectName("h2")
        self.sub = QLabel("oppure clicca per sceglierlo dal computer")
        self.sub.setObjectName("muted")
        for w in (self.icon, self.title, self.sub):
            lay.addWidget(w, 0, Qt.AlignHCenter)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            path, _ = QFileDialog.getOpenFileName(self, "Scegli il video della partita", "", self.EXT)
            if path:
                self.fileChosen.emit(path)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.setProperty("hover", True)
            repolish(self)

    def dragLeaveEvent(self, _e):
        self.setProperty("hover", False)
        repolish(self)

    def dropEvent(self, e):
        self.setProperty("hover", False)
        repolish(self)
        urls = e.mimeData().urls()
        if urls:
            self.fileChosen.emit(urls[0].toLocalFile())

    def show_file(self, name, info):
        self.icon.setText("✓")
        self.title.setText(name)
        self.sub.setText(info + "  ·  clicca per cambiare video")
        self.setProperty("loaded", True)
        repolish(self)


# ----------------------------------------------------------------------------------
class StepBar(QWidget):
    def __init__(self, names):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.dots, self.labels = [], []
        for i, name in enumerate(names):
            if i:
                line = QFrame()
                line.setFixedSize(34, 2)
                line.setStyleSheet(f"background:{theme.BORDER};")
                lay.addWidget(line)
            dot = QLabel(str(i + 1))
            dot.setAlignment(Qt.AlignCenter)
            lbl = QLabel(name)
            lay.addWidget(dot)
            lay.addWidget(lbl)
            self.dots.append(dot)
            self.labels.append(lbl)
        self.set_step(0)

    def set_step(self, current):
        for i, (d, l) in enumerate(zip(self.dots, self.labels)):
            on = i <= current
            d.setObjectName("stepDotOn" if on else "stepDot")
            l.setObjectName("stepOn" if i == current else "stepOff")
            d.setText("✓" if i < current else str(i + 1))
            repolish(d)
            repolish(l)


# ----------------------------------------------------------------------------------
class ClipTimeline(QWidget):
    """Tutta la partita in una riga: rumore del campo, fischi e clip colorate."""
    clipClicked = Signal(int)
    seekRequested = Signal(float)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(104)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.duration = 0.0
        self.energy = np.zeros(0)
        self.whistles = []
        self.clips = []
        self.sel = -1
        self.playhead = 0.0
        self._bars = None

    # dati
    def set_data(self, duration, energy, whistles):
        self.duration = float(duration)
        self.energy = np.asarray(energy, dtype=float)
        self.whistles = list(whistles)
        self._bars = None
        self.update()

    def set_clips(self, clips, sel):
        self.clips, self.sel = clips, sel
        self.update()

    def set_playhead(self, t):
        self.playhead = t
        self.update()

    # geometria
    def _plot(self):
        return QRectF(10, 10, max(10, self.width() - 20), self.height() - 36)

    def _x(self, t):
        r = self._plot()
        return r.left() + r.width() * (t / self.duration if self.duration else 0)

    def _t(self, x):
        r = self._plot()
        return max(0.0, min(self.duration, (x - r.left()) / r.width() * self.duration))

    def _rebuild_bars(self):
        w = int(self._plot().width())
        if len(self.energy) < 2 or w < 2:
            self._bars = np.zeros(max(w, 1))
            return
        lo, hi = np.percentile(self.energy, 5), np.percentile(self.energy, 99.5)
        norm = np.clip((self.energy - lo) / max(hi - lo, 1e-6), 0, 1)
        idx = np.linspace(0, len(norm), w + 1).astype(int)[:-1]
        idx = np.minimum(idx, len(norm) - 1)
        self._bars = np.maximum.reduceat(norm, idx)

    def resizeEvent(self, e):
        self._bars = None
        super().resizeEvent(e)

    # disegno
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.SURFACE))
        p.drawRoundedRect(self.rect(), 12, 12)
        if self.duration <= 0:
            return
        r = self._plot()
        if self._bars is None:
            self._rebuild_bars()
        # rumore del campo
        p.setBrush(QColor("#34455A"))
        n = len(self._bars)
        for i, v in enumerate(self._bars):
            h = 3 + v * (r.height() - 3)
            p.drawRect(QRectF(r.left() + i * r.width() / n, r.bottom() - h,
                              max(1.0, r.width() / n - 0.4), h))
        # clip
        for i, c in enumerate(self.clips):
            x0, x1 = self._x(c.start), self._x(c.end)
            col = QColor(kind_color(c.kind))
            sel = i == self.sel
            fill = QColor(col)
            fill.setAlpha(150 if sel else (80 if c.enabled else 28))
            p.setBrush(fill)
            p.setPen(QPen(col, 2) if sel else Qt.NoPen)
            p.drawRoundedRect(QRectF(x0, r.top(), max(4.0, x1 - x0), r.height()), 4, 4)
            p.setPen(Qt.NoPen)
            p.setBrush(col if c.enabled else QColor(theme.MUTED))
            p.drawRect(QRectF(x0, r.top(), max(4.0, x1 - x0), 3))
        # fischi
        pen = QPen(QColor(theme.WARN), 1.5)
        p.setPen(pen)
        for w in self.whistles:
            x = self._x(w.start)
            p.drawLine(int(x), int(r.bottom() - 7), int(x), int(r.bottom()))
        # tempo
        p.setPen(QColor(theme.MUTED))
        step = 600 if self.duration > 2400 else 300 if self.duration > 900 else 60
        t = 0
        while t <= self.duration:
            x = self._x(t)
            p.drawLine(int(x), int(r.bottom() + 3), int(x), int(r.bottom() + 7))
            lx = min(max(x - 30, 2), self.width() - 62)
            p.drawText(QRectF(lx, r.bottom() + 8, 60, 16), Qt.AlignHCenter, fmt_time(t))
            t += step
        # cursore
        x = self._x(self.playhead)
        p.setPen(QPen(QColor("#FFFFFF"), 2))
        p.drawLine(int(x), int(r.top() - 4), int(x), int(r.bottom() + 2))

    def mousePressEvent(self, e):
        if self.duration <= 0 or e.button() != Qt.LeftButton:
            return
        x = e.position().x()
        for i, c in enumerate(self.clips):
            if self._x(c.start) - 3 <= x <= max(self._x(c.end), self._x(c.start) + 4) + 3:
                self.clipClicked.emit(i)
                return
        self.seekRequested.emit(self._t(x))


# ----------------------------------------------------------------------------------
class TrimSlider(QWidget):
    """Finestra intorno alla clip: trascina le maniglie per cambiare inizio e fine."""
    seekRequested = Signal(float)
    startChanged = Signal(float)
    endChanged = Signal(float)
    released = Signal()

    PAD = 16

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(64)
        self.setMouseTracking(True)
        self.w0, self.w1 = 0.0, 1.0
        self.start, self.end, self.playhead = 0.0, 1.0, 0.0
        self.color = theme.ACCENT
        self._drag = None

    def set_window(self, w0, w1):
        self.w0, self.w1 = w0, max(w1, w0 + 1)
        self.update()

    def set_range(self, start, end, color=None):
        self.start, self.end = start, end
        if color:
            self.color = color
        self.update()

    def set_playhead(self, t):
        self.playhead = t
        self.update()

    def _x(self, t):
        return self.PAD + (self.width() - 2 * self.PAD) * (t - self.w0) / (self.w1 - self.w0)

    def _t(self, x):
        f = (x - self.PAD) / max(1, self.width() - 2 * self.PAD)
        return self.w0 + max(0.0, min(1.0, f)) * (self.w1 - self.w0)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cy = self.height() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.SURFACE2))
        p.drawRoundedRect(QRectF(self.PAD, cy - 5, self.width() - 2 * self.PAD, 10), 5, 5)
        xs, xe = self._x(self.start), self._x(self.end)
        col = QColor(self.color)
        fill = QColor(col)
        fill.setAlpha(170)
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(xs, cy - 5, max(2.0, xe - xs), 10), 5, 5)
        # maniglie
        for x in (xs, xe):
            p.setBrush(col)
            p.drawRoundedRect(QRectF(x - 6, cy - 17, 12, 34), 5, 5)
            p.setBrush(QColor(theme.ACCENT_DARK))
            p.drawRoundedRect(QRectF(x - 1, cy - 8, 2, 16), 1, 1)
        # cursore
        x = self._x(self.playhead)
        if self.PAD - 2 <= x <= self.width() - self.PAD + 2:
            p.setPen(QPen(QColor("#FFFFFF"), 2))
            p.drawLine(int(x), int(cy - 21), int(x), int(cy + 21))

    def _hit(self, x):
        ds, de = abs(x - self._x(self.start)), abs(x - self._x(self.end))
        if min(ds, de) <= 11:
            return "start" if ds <= de else "end"
        return "seek"

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag is None:
            self.setCursor(Qt.SizeHorCursor if self._hit(x) != "seek" else Qt.PointingHandCursor)
            return
        t = round(self._t(x) * 2) / 2     # passi di mezzo secondo
        if self._drag == "start":
            self.start = max(self.w0, min(t, self.end - 2))
            self.startChanged.emit(self.start)
        elif self._drag == "end":
            self.end = min(self.w1, max(t, self.start + 2))
            self.endChanged.emit(self.end)
        else:
            self.seekRequested.emit(self._t(x))
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = self._hit(e.position().x())
            self.mouseMoveEvent(e)

    def mouseReleaseEvent(self, _e):
        if self._drag is not None:
            self._drag = None
            self.released.emit()


# ----------------------------------------------------------------------------------
class ClipRow(QWidget):
    """Una riga dell'elenco clip."""
    toggled = Signal(bool)

    def __init__(self, clip):
        super().__init__()
        self.clip = clip
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)
        self.check = QCheckBox()
        self.check.toggled.connect(self.toggled)
        self.bar = QFrame()
        self.bar.setFixedWidth(4)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight:600;")
        self.sub = QLabel()
        self.sub.setObjectName("muted")
        self.note = QLabel()
        self.note.setObjectName("muted")
        self.note.setStyleSheet("font-size:9pt;")
        text.addWidget(self.title)
        text.addWidget(self.sub)
        text.addWidget(self.note)
        lay.addWidget(self.check)
        lay.addWidget(self.bar)
        lay.addLayout(text, 1)
        self.refresh()

    def refresh(self):
        c = self.clip
        self.check.blockSignals(True)
        self.check.setChecked(c.enabled)
        self.check.blockSignals(False)
        self.bar.setStyleSheet(
            f"background:{kind_color(c.kind) if c.enabled else theme.BORDER};border-radius:2px;")
        self.title.setText(c.label or c.kind)
        self.title.setStyleSheet("font-weight:600;" + ("" if c.enabled else f"color:{theme.MUTED};"))
        self.sub.setText(f"{fmt_time(c.start)} – {fmt_time(c.end)} · {c.duration:.0f} s")
        self.note.setVisible(bool(c.note))
        self.note.setText(self.note.fontMetrics().elidedText(c.note, Qt.ElideRight, 250))
        self.note.setToolTip(c.note)
