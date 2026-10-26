"""Componenti grafici riutilizzabili."""

import os

import numpy as np
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from . import theme
from .media import VIDEO_EXT, natural_key
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
    """Zona dove trascinare uno o piu' video, oppure cliccare per sceglierli."""
    filesChosen = Signal(list)
    EXT = ("Video (*.mp4 *.mov *.mkv *.avi *.mts *.m2ts *.mpg *.mpeg *.wmv *.m4v);;"
           "Tutti i file (*.*)")

    def __init__(self):
        super().__init__()
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(150)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(6)
        self.icon = QLabel("+")
        self.icon.setObjectName("plus")
        self.icon.setAlignment(Qt.AlignCenter)
        self.title = QLabel()
        self.title.setObjectName("h2")
        self.sub = QLabel()
        self.sub.setObjectName("muted")
        for w in (self.icon, self.title, self.sub):
            lay.addWidget(w, 0, Qt.AlignHCenter)
        self.reset()

    def reset(self):
        self.icon.setText("+")
        self.title.setText("Trascina qui i video della partita")
        self.sub.setText("anche più file (es. file da 17 minuti), oppure clicca per sceglierli")
        self.setProperty("loaded", False)
        repolish(self)

    def show_files(self, title, info):
        self.icon.setText("✓")
        self.title.setText(title)
        self.sub.setText(info + "  ·  clicca per aggiungerne altri")
        self.setProperty("loaded", True)
        repolish(self)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            paths, _ = QFileDialog.getOpenFileNames(
                self, "Scegli i video della partita", "", self.EXT)
            if paths:
                self.filesChosen.emit(list(paths))

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
        paths = expand_paths([u.toLocalFile() for u in e.mimeData().urls()])
        if paths:
            self.filesChosen.emit(paths)


def expand_paths(paths):
    """File cosi' come sono; per le cartelle, i video che contengono."""
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += [os.path.join(p, f) for f in sorted(os.listdir(p), key=natural_key)
                    if f.lower().endswith(VIDEO_EXT)]
        elif os.path.isfile(p):
            out.append(p)
    return out


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
    """Tutta la partita in una riga: rumore del campo, fischi, parole sentite e clip.

    Clic = vai li'. Trascina = crea una clip su quel tratto. Rotella = ingrandisci.
    Tasto destro trascinato = sposta la vista. Doppio clic = tutta la partita.
    """
    clipClicked = Signal(int)
    seekRequested = Signal(float)
    markerClicked = Signal(object)
    rangeSelected = Signal(float, float)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(112)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.duration = 0.0
        self.v0 = self.v1 = 0.0          # parte di partita visibile
        self.energy = np.zeros(0)
        self.whistles = []
        self.clips = []
        self.used = []                   # parole usate (meta, calcio, inizio)
        self.others = []                 # parole sentite ma non usate
        self.sel = -1
        self.playhead = 0.0
        self._bars = None
        self._press = None               # (x, t) alla pressione del tasto sinistro
        self._drag = None                # (t0, t1) mentre si trascina
        self._pan = None                 # (x, v0) col tasto destro

    # dati
    def set_data(self, duration, energy, whistles):
        self.duration = float(duration)
        self.v0, self.v1 = 0.0, self.duration
        self.energy = np.asarray(energy, dtype=float)
        self.whistles = list(whistles)
        self._bars = None
        self.update()

    def set_markers(self, used, others):
        self.used = [m for m in used if m.kind in ("meta", "calcio", "inizio")]
        self.others = [m for m in others if m.kind in ("meta", "calcio")]
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

    def _span(self):
        return max(1e-6, self.v1 - self.v0)

    def _x(self, t):
        r = self._plot()
        return r.left() + r.width() * ((t - self.v0) / self._span() if self.duration else 0)

    def _t(self, x):
        r = self._plot()
        return max(0.0, min(self.duration, self.v0 + (x - r.left()) / r.width() * self._span()))

    def _set_view(self, v0, v1):
        span = min(max(v1 - v0, 30.0), self.duration)
        v0 = max(0.0, min(v0, self.duration - span))
        self.v0, self.v1 = v0, v0 + span
        self._bars = None
        self.update()

    def _rebuild_bars(self):
        w = int(self._plot().width())
        a, b = int(self.v0), int(self.v1) + 1
        seg = self.energy[a:b]
        if len(seg) < 1 or w < 2:
            self._bars = np.zeros(max(w, 1))
            return
        lo, hi = np.percentile(self.energy, 5), np.percentile(self.energy, 99.5)
        norm = np.clip((seg - lo) / max(hi - lo, 1e-6), 0, 1)
        idx = np.linspace(0, len(norm), w + 1).astype(int)[:-1]
        idx = np.minimum(idx, len(norm) - 1)
        self._bars = np.maximum.reduceat(norm, idx) if len(norm) >= w else norm[idx]

    def resizeEvent(self, e):
        self._bars = None
        super().resizeEvent(e)

    def _marker_at(self, x, tol=7):
        best = None
        for m in self.used + self.others:
            d = abs(self._x(m.time) - x)
            if d <= tol and (best is None or d < best[0]):
                best = (d, m)
        return best[1] if best else None

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
        p.setClipRect(self.rect())
        if self._bars is None:
            self._rebuild_bars()
        # rumore del campo
        p.setBrush(QColor("#34455A"))
        n = len(self._bars)
        for i, v in enumerate(self._bars):
            h = 3 + v * (r.height() - 3)
            p.drawRect(QRectF(r.left() + i * r.width() / n, r.bottom() - h,
                              max(1.0, r.width() / n - 0.4), h))
        p.setClipRect(QRectF(r.left() - 1, 0, r.width() + 2, self.height()))
        # clip
        for i, c in enumerate(self.clips):
            if c.end < self.v0 or c.start > self.v1:
                continue
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
        # tratto che stai scegliendo
        if self._drag:
            a, b = sorted(self._drag)
            sel_col = QColor(kind_color("manuale"))
            sel_col.setAlpha(90)
            p.setBrush(sel_col)
            p.setPen(QPen(QColor(kind_color("manuale")), 1.5))
            p.drawRect(QRectF(self._x(a), r.top(), max(2.0, self._x(b) - self._x(a)), r.height()))
        # fischi
        p.setPen(QPen(QColor(theme.WARN), 1.5))
        for w in self.whistles:
            if self.v0 <= w.start <= self.v1:
                x = self._x(w.start)
                p.drawLine(int(x), int(r.bottom() - 7), int(x), int(r.bottom()))
        # parole sentite ma non usate (cerchi vuoti) e usate (pieni)
        for m in self.others:
            if self.v0 <= m.time <= self.v1:
                col = QColor(kind_color(m.kind))
                col.setAlpha(150)
                p.setPen(QPen(col, 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QRectF(self._x(m.time) - 4, r.top() + 5, 8, 8))
        for m in self.used:
            if self.v0 <= m.time <= self.v1:
                col = QColor(kind_color(m.kind))
                p.setPen(QPen(QColor(theme.BG), 1.5))
                p.setBrush(col)
                p.drawEllipse(QRectF(self._x(m.time) - 5, r.top() + 4, 10, 10))
        p.setClipping(False)
        # tempo
        p.setPen(QColor(theme.MUTED))
        span = self._span()
        step = 10 if span <= 120 else 60 if span <= 600 else 300 if span <= 1800 else 600
        if span <= 120 and span > 60:
            step = 20
        t = int(self.v0 // step) * step
        while t <= self.v1:
            if t >= self.v0:
                x = self._x(t)
                p.drawLine(int(x), int(r.bottom() + 3), int(x), int(r.bottom() + 7))
                lx = min(max(x - 30, 2), self.width() - 62)
                p.drawText(QRectF(lx, r.bottom() + 8, 60, 16), Qt.AlignHCenter, fmt_time(t))
            t += step
        # cursore
        if self.v0 <= self.playhead <= self.v1:
            x = self._x(self.playhead)
            p.setPen(QPen(QColor("#FFFFFF"), 2))
            p.drawLine(int(x), int(r.top() - 4), int(x), int(r.bottom() + 2))

    # mouse
    def mousePressEvent(self, e):
        if self.duration <= 0:
            return
        x = e.position().x()
        if e.button() in (Qt.RightButton, Qt.MiddleButton):
            self._pan = (x, self.v0)
            return
        if e.button() != Qt.LeftButton:
            return
        m = self._marker_at(x)
        if m is not None:
            self.markerClicked.emit(m)
            return
        hit = None
        for i, c in enumerate(self.clips):
            if self._x(c.start) - 3 <= x <= max(self._x(c.end), self._x(c.start) + 4) + 3:
                hit = i
                break
        # clic su una clip = selezionala; trascinando si crea invece un nuovo tratto
        self._press = (x, self._t(x), hit)

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._pan is not None:
            r = self._plot()
            dt = (x - self._pan[0]) / r.width() * self._span()
            self._set_view(self._pan[1] - dt, self._pan[1] - dt + self._span())
            return
        if self._press is not None and abs(x - self._press[0]) > 5:
            self._drag = (self._press[1], self._t(x))
            self.update()
            return
        m = self._marker_at(x)
        if m is not None:
            used = m in self.used
            self.setToolTip(f"{m.kind} · {fmt_time(m.time, True)} · sicurezza {m.conf * 100:.0f}%"
                            + ("" if used else " · sentita ma non usata"))
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setToolTip("")
            self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, e):
        if e.button() in (Qt.RightButton, Qt.MiddleButton):
            self._pan = None
            return
        if e.button() != Qt.LeftButton or self._press is None:
            return
        press, drag = self._press, self._drag
        self._press, self._drag = None, None
        self.update()
        if drag and abs(drag[1] - drag[0]) >= 2.0:
            a, b = sorted(drag)
            self.rangeSelected.emit(a, b)
        elif press[2] is not None:
            self.clipClicked.emit(press[2])
        else:
            self.seekRequested.emit(press[1])

    def wheelEvent(self, e):
        if self.duration <= 0:
            return
        dy = e.angleDelta().y()
        if dy == 0:
            return
        anchor = self._t(e.position().x())
        factor = 0.75 if dy > 0 else 1 / 0.75
        span = min(self.duration, max(30.0, self._span() * factor))
        ratio = (anchor - self.v0) / self._span()
        self._set_view(anchor - ratio * span, anchor - ratio * span + span)
        e.accept()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton and self.duration > 0:
            self._set_view(0.0, self.duration)


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
