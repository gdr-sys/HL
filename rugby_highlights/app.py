"""Finestra principale: scegli il video -> analisi -> revisione -> video finale."""

import os
import subprocess
import sys
import threading

from PySide6.QtCore import QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
                               QSlider, QStackedWidget, QVBoxLayout, QWidget)

from . import __version__, theme
from .ffmpeg_utils import export_montage, probe_duration
from .media import Media, natural_key
from .models import Cancelled, Clip, Expected, Settings
from .narration import Names, ReportError, build_script, parse_report
from .paths import find_binary, find_vosk_model
from .pipeline import analyze
from .planner import fit_to_target, relabel
from .player import VideoPlayer
from . import premiere, timecodes
from .widgets import (ClipRow, ClipTimeline, DropArea, NumberStepper, StepBar, Stepper,
                      TrimSlider, fmt_time, repolish)


def open_folder_of(path):
    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


def card():
    f = QFrame()
    f.setObjectName("card")
    return f


class Worker(QObject):
    """Esegue una funzione lunga in un thread e riporta avanzamento e risultato."""
    progress = Signal(float, str)
    done = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self._cancel = False

    def callback(self, frac, text=""):
        if self._cancel:
            raise Cancelled()
        self.progress.emit(float(frac), text)

    def cancel(self):
        self._cancel = True

    def start(self):
        def run():
            try:
                self.done.emit(self.fn(self.callback))
            except Cancelled:
                self.cancelled.emit()
            except Exception as e:  # noqa: BLE001
                self.failed.emit(str(e))
        threading.Thread(target=run, daemon=True).start()


# ------------------------------------------------------------------------ pagina 1
class SetupPage(QWidget):
    analyzeRequested = Signal()

    def __init__(self):
        super().__init__()
        self.paths, self.durations, self._manual = [], {}, False
        inner = QWidget()
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.addWidget(scroll)
        outer = QHBoxLayout(inner)
        outer.addStretch(1)
        col = QVBoxLayout()
        col.setSpacing(14)
        colw = QWidget()
        colw.setLayout(col)
        colw.setMaximumWidth(820)
        colw.setMinimumWidth(640)
        outer.addWidget(colw, 4)
        outer.addStretch(1)

        title = QLabel("Highlights della partita")
        title.setObjectName("title")
        sub = QLabel("Carica la registrazione: trovo le azioni da punti e preparo il montaggio.")
        sub.setObjectName("muted")
        col.addSpacing(10)
        col.addWidget(title)
        col.addWidget(sub)
        col.addSpacing(6)

        self.drop = DropArea()
        self.drop.filesChosen.connect(self.add_files)
        col.addWidget(self.drop)

        # elenco dei file della partita (ordinabile)
        self.files_card = card()
        fl = QVBoxLayout(self.files_card)
        fl.setContentsMargins(16, 12, 16, 12)
        fl.setSpacing(8)
        top = QHBoxLayout()
        fh = QLabel("File della partita")
        fh.setObjectName("h2")
        self.files_info = QLabel("")
        self.files_info.setObjectName("muted")
        top.addWidget(fh)
        top.addStretch(1)
        top.addWidget(self.files_info)
        fl.addLayout(top)
        self.flist = QListWidget()
        self.flist.setMinimumHeight(64)
        self.flist.setMaximumHeight(150)
        fl.addWidget(self.flist)
        fb = QHBoxLayout()
        for text, fn in (("↑ Su", lambda: self._move(-1)), ("↓ Giù", lambda: self._move(1)),
                         ("Rimuovi", self._remove), ("Svuota", self.clear)):
            b = QPushButton(text)
            b.setObjectName("small")
            b.clicked.connect(fn)
            fb.addWidget(b)
        fb.addStretch(1)
        fl.addLayout(fb)
        self.files_card.hide()
        col.addWidget(self.files_card)

        # tabellino
        box = card()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(20, 16, 20, 18)
        bl.setSpacing(10)
        h = QLabel("Tabellino")
        h.setObjectName("h2")
        hint = QLabel("Quante azioni da punti ci sono state. Serve per controllare che non ne manchi nessuna.")
        hint.setObjectName("muted")
        bl.addWidget(h)
        bl.addWidget(hint)
        bl.addSpacing(8)
        teams = QHBoxLayout()
        teams.setSpacing(36)
        self.steps = {}
        for key, name in (("a", "La mia squadra"), ("b", "Avversari")):
            tl = QVBoxLayout()
            tl.setSpacing(6)
            t = QLabel(name)
            t.setStyleSheet("font-weight:600;")
            tl.addWidget(t)
            for kind, text in (("meta", "Mete"), ("calcio", "Calci a punti")):
                s = Stepper(text)
                self.steps[(key, kind)] = s
                tl.addWidget(s)
            teams.addLayout(tl, 1)
        bl.addLayout(teams)
        self.chk_conv = QCheckBox("Dico «calcio» anche per la trasformazione dopo la meta")
        self.chk_conv.setChecked(True)
        bl.addWidget(self.chk_conv)
        explain = QLabel("Calci a punti: punizioni, drop e (se spuntato) trasformazioni. "
                         "Il calcio dopo la meta viene unito alla clip della meta.")
        explain.setObjectName("muted")
        explain.setWordWrap(True)
        bl.addWidget(explain)
        col.addWidget(box)

        # comunicato (facoltativo)
        cbox = card()
        cl = QVBoxLayout(cbox)
        cl.setContentsMargins(20, 16, 20, 18)
        cl.setSpacing(8)
        ch = QLabel("Comunicato stampa (facoltativo)")
        ch.setObjectName("h2")
        chint = QLabel("Incollalo qui: ne ricavo i punti per il tabellino e preparo il copione da "
                       "leggere e il riassunto della partita.")
        chint.setObjectName("muted")
        chint.setWordWrap(True)
        cl.addWidget(ch)
        cl.addWidget(chint)
        names = QGridLayout()
        names.setHorizontalSpacing(12)
        self.name_mine, self.name_opp = QLineEdit(), QLineEdit()
        self.name_mine.setPlaceholderText("La mia squadra (es. Fiorini Pesaro)")
        self.name_opp.setPlaceholderText("Avversari (es. Capitolina)")
        self.venue = QComboBox()
        self.venue.addItems(["Gioco in casa", "Gioco in trasferta"])
        names.addWidget(self.name_mine, 0, 0)
        names.addWidget(self.name_opp, 0, 1)
        names.addWidget(self.venue, 0, 2)
        names.setColumnStretch(0, 1)
        names.setColumnStretch(1, 1)
        cl.addLayout(names)
        self.report_text = QPlainTextEdit()
        self.report_text.setPlaceholderText("Incolla qui il comunicato…")
        self.report_text.setMinimumHeight(110)
        self.report_text.setMaximumHeight(200)
        cl.addWidget(self.report_text)
        rb = QHBoxLayout()
        self.btn_report = QPushButton("Leggi i punti dal comunicato")
        self.btn_report.clicked.connect(self.read_report)
        self.report_info = QLabel("")
        self.report_info.setObjectName("muted")
        self.report_info.setWordWrap(True)
        rb.addWidget(self.btn_report)
        rb.addWidget(self.report_info, 1)
        cl.addLayout(rb)
        col.addWidget(cbox)

        # impostazioni avanzate
        self.btn_adv = QPushButton("Impostazioni avanzate  ▾")
        self.btn_adv.setObjectName("flat")
        self.btn_adv.setCursor(Qt.PointingHandCursor)
        self.btn_adv.clicked.connect(self._toggle_adv)
        col.addWidget(self.btn_adv, 0, Qt.AlignLeft)
        self.adv = card()
        grid = QGridLayout(self.adv)
        grid.setContentsMargins(20, 14, 20, 14)
        grid.setHorizontalSpacing(18)
        self.spins = {}
        rows = (("target", "Durata massima degli highlights", 180, 30, 900, " s"),
                ("meta_post", "Dopo la meta (festeggiamenti)", 12, 0, 60, " s"),
                ("calcio_pre", "Prima del calcio", 14, 2, 60, " s"),
                ("calcio_post", "Dopo il calcio", 7, 0, 60, " s"),
                ("delay", "Ritardo con cui dico «meta» o «calcio»", 0, 0, 20, " s"),
                ("conf", "Sicurezza minima delle parole (più alta = meno errori)", 70, 30, 98, " %"))
        for r, (key, label, default, lo, hi, suffix) in enumerate(rows):
            lab = QLabel(label)
            sp = NumberStepper(default, lo, hi, 15 if key == "target" else 1, suffix)
            self.spins[key] = sp
            grid.addWidget(lab, r, 0)
            grid.addWidget(sp, r, 1)
        self.chk_crowd = QCheckBox("Se manca qualche azione, proponi i picchi di rumore del pubblico")
        grid.addWidget(self.chk_crowd, len(rows), 0, 1, 2)
        grid.setColumnStretch(0, 1)
        self.adv.hide()
        col.addWidget(self.adv)

        col.addStretch(1)
        self.btn_go = QPushButton("Analizza la partita  →")
        self.btn_go.setObjectName("primary")
        self.btn_go.setCursor(Qt.PointingHandCursor)
        self.btn_go.setEnabled(False)
        self.btn_go.clicked.connect(self.analyzeRequested)
        foot = QHBoxLayout()
        self.note = QLabel("Scegli prima il video (o i video) della partita.")
        self.note.setObjectName("muted")
        foot.addWidget(self.note, 1)
        foot.addWidget(self.btn_go)
        col.addLayout(foot)
        col.addSpacing(10)

    def _toggle_adv(self):
        show = self.adv.isHidden()
        self.adv.setVisible(show)
        self.btn_adv.setText("Impostazioni avanzate  " + ("▴" if show else "▾"))

    # ---- file della partita
    def add_files(self, paths):
        bad = []
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for p in paths:
                if p in self.paths or not os.path.isfile(p):
                    continue
                try:
                    self.durations[p] = probe_duration(p)
                except Exception:  # noqa: BLE001
                    bad.append(os.path.basename(p))
                    continue
                self.paths.append(p)
        finally:
            QApplication.restoreOverrideCursor()
        if not self._manual:
            self.paths.sort(key=natural_key)
        if bad:
            QMessageBox.warning(self, "Video", "Non riesco a leggere questi file:\n" + "\n".join(bad))
        self._refresh_files()

    def set_video(self, path):
        self.add_files([path])

    def _refresh_files(self, select=None):
        self.flist.clear()
        for i, p in enumerate(self.paths, start=1):
            self.flist.addItem(f"{i}.   {os.path.basename(p)}      {fmt_time(self.durations[p])}")
        n = len(self.paths)
        self.files_card.setVisible(n > 0)
        self.btn_go.setEnabled(n > 0)
        if n == 0:
            self.drop.reset()
            self.note.setText("Scegli prima il video (o i video) della partita.")
            return
        total = sum(self.durations[p] for p in self.paths)
        size = sum(os.path.getsize(p) for p in self.paths if os.path.exists(p))
        self.drop.show_files(os.path.basename(self.paths[0]) if n == 1 else f"{n} file",
                             f"{fmt_time(total)}  ·  {human_size(size)}")
        self.files_info.setText("in ordine di nome: puoi cambiarlo" if n > 1 else "")
        self.note.setText("Per una partita intera l'analisi richiede qualche minuto.")
        if select is not None:
            self.flist.setCurrentRow(select)

    def _move(self, delta):
        i = self.flist.currentRow()
        j = i + delta
        if i < 0 or not (0 <= j < len(self.paths)):
            return
        self.paths[i], self.paths[j] = self.paths[j], self.paths[i]
        self._manual = True
        self._refresh_files(select=j)

    def _remove(self):
        i = self.flist.currentRow()
        if i >= 0:
            del self.paths[i]
            self._refresh_files(select=min(i, len(self.paths) - 1))

    def clear(self):
        self.paths, self.durations, self._manual = [], {}, False
        self._refresh_files()

    def media(self):
        return Media.from_paths(self.paths, self.durations)

    def settings(self):
        s = Settings()
        s.target_seconds = float(self.spins["target"].value())
        s.meta_post = float(self.spins["meta_post"].value())
        s.calcio_pre = float(self.spins["calcio_pre"].value())
        s.calcio_post = float(self.spins["calcio_post"].value())
        s.delay_correction = float(self.spins["delay"].value())
        s.voice_min_conf = self.spins["conf"].value() / 100.0
        s.suggest_from_crowd = self.chk_crowd.isChecked()
        return s

    # ---- comunicato
    def _mine_is_home(self):
        return self.venue.currentIndex() == 0

    def names(self):
        mine, opp = self.name_mine.text(), self.name_opp.text()
        return Names(mine, opp) if self._mine_is_home() else Names(opp, mine)

    def report(self):
        """Il comunicato letto, oppure None se non c'e' (o non si capisce)."""
        text = self.report_text.toPlainText().strip()
        if not text:
            return None
        try:
            return parse_report(text)
        except ReportError:
            return None

    def read_report(self):
        text = self.report_text.toPlainText().strip()
        if not text:
            self.report_info.setText("Incolla prima il comunicato.")
            return None
        try:
            rep = parse_report(text)
        except ReportError as e:
            self.report_info.setText(str(e))
            return None
        mine = "home" if self._mine_is_home() else "away"
        for key, side in (("a", mine), ("b", "away" if mine == "home" else "home")):
            for kind in ("meta", "calcio"):
                n = rep.count(kind, side)
                if kind == "calcio" and self.chk_conv.isChecked():
                    n += rep.conversions(side)
                self.steps[(key, kind)].setValue(n)
        warn = ("  ⚠ " + " ".join(rep.warnings)) if rep.warnings else ""
        self.report_info.setText(
            f"Trovati {len(rep.events)} punteggi: {rep.count('meta')} mete e "
            f"{rep.count('calcio') + (rep.conversions() if self.chk_conv.isChecked() else 0)} "
            "calci a punti. Ho compilato il tabellino: controllalo." + warn)
        return rep

    def expected(self):
        return Expected(
            sum(self.steps[(k, "meta")].value() for k in "ab"),
            sum(self.steps[(k, "calcio")].value() for k in "ab"))


# ------------------------------------------------------------------------ pagina 2
class AnalysisPage(QWidget):
    cancelRequested = Signal()
    PHASES = ("Leggo il video e l'audio", "Cerco fischi e rumore del pubblico",
              "Ascolto le parole «meta» e «calcio»", "Preparo le clip")

    def __init__(self):
        super().__init__()
        outer = QHBoxLayout(self)
        outer.addStretch(1)
        col = QVBoxLayout()
        colw = QWidget()
        colw.setLayout(col)
        colw.setFixedWidth(560)
        outer.addWidget(colw)
        outer.addStretch(1)
        col.addStretch(2)
        t = QLabel("Sto analizzando la partita")
        t.setObjectName("title")
        s = QLabel("Quando ha finito vedrai le azioni trovate e potrai controllarle una per una.")
        s.setObjectName("muted")
        s.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(s)
        col.addSpacing(14)
        box = card()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(22, 20, 22, 20)
        bl.setSpacing(10)
        self.marks, self.names = [], []
        for name in self.PHASES:
            row = QHBoxLayout()
            m = QLabel("○")
            m.setFixedWidth(22)
            n = QLabel(name)
            row.addWidget(m)
            row.addWidget(n, 1)
            bl.addLayout(row)
            self.marks.append(m)
            self.names.append(n)
        bl.addSpacing(6)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        bl.addWidget(self.bar)
        self.pct = QLabel("0%")
        self.pct.setObjectName("muted")
        bl.addWidget(self.pct)
        col.addWidget(box)
        col.addSpacing(10)
        cancel = QPushButton("Annulla")
        cancel.clicked.connect(self.cancelRequested)
        col.addWidget(cancel, 0, Qt.AlignRight)
        col.addStretch(3)
        self.reset()

    def reset(self):
        self.update_progress(0.0)

    def update_progress(self, f, _text=""):
        idx = 0 if f < 0.20 else 1 if f < 0.40 else 2 if f < 0.97 else 3
        for i, (m, n) in enumerate(zip(self.marks, self.names)):
            if i < idx:
                m.setText("✓")
                m.setStyleSheet(f"color:{theme.ACCENT};")
                n.setStyleSheet(f"color:{theme.MUTED};")
            elif i == idx:
                m.setText("●")
                m.setStyleSheet(f"color:{theme.ACCENT};")
                n.setStyleSheet("font-weight:600;")
            else:
                m.setText("○")
                m.setStyleSheet(f"color:{theme.MUTED};")
                n.setStyleSheet(f"color:{theme.MUTED};")
        self.bar.setValue(int(f * 1000))
        self.pct.setText(f"{f * 100:.0f}%")


# ------------------------------------------------------------------------ pagina 3
class ReviewPage(QWidget):
    exportRequested = Signal(list)
    timecodesRequested = Signal()
    newMatchRequested = Signal()

    def __init__(self):
        super().__init__()
        self.media = None
        self.duration = 0.0
        self.clips = []
        self.sel = -1
        self.settings = Settings()
        self.rows = []
        self._cursor = 0.0

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 8, 26, 18)
        root.setSpacing(12)
        body = QHBoxLayout()
        body.setSpacing(18)

        # ---- sinistra: elenco clip
        left = QVBoxLayout()
        left.setSpacing(8)
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QVBoxLayout(self.banner)
        bl.setContentsMargins(14, 10, 14, 10)
        self.banner_lbl = QLabel()
        self.banner_lbl.setWordWrap(True)
        self.banner_lbl.setStyleSheet(f"color:{theme.WARN};")
        bl.addWidget(self.banner_lbl)
        left.addWidget(self.banner)
        head = QHBoxLayout()
        h = QLabel("Azioni trovate")
        h.setObjectName("h2")
        self.count = QLabel("")
        self.count.setObjectName("muted")
        head.addWidget(h)
        head.addStretch(1)
        head.addWidget(self.count)
        left.addLayout(head)
        hint = QLabel("Togli la spunta per escludere un'azione.")
        hint.setObjectName("muted")
        left.addWidget(hint)
        self.list = QListWidget()
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.currentRowChanged.connect(self._select)
        left.addWidget(self.list, 1)
        btns = QHBoxLayout()
        self.btn_add = QPushButton("+ Aggiungi dal punto attuale")
        self.btn_add.setObjectName("small")
        self.btn_add.setToolTip("Sposta il video dove succede l'azione e premi qui")
        self.btn_add.clicked.connect(self._add)
        self.btn_del = QPushButton("Elimina")
        self.btn_del.setObjectName("small")
        self.btn_del.clicked.connect(self._delete)
        btns.addWidget(self.btn_add, 1)
        btns.addWidget(self.btn_del)
        left.addLayout(btns)
        leftw = QWidget()
        leftw.setLayout(left)
        leftw.setFixedWidth(372)
        body.addWidget(leftw)

        # ---- destra: player, regolazione, linea del tempo
        right = QVBoxLayout()
        right.setSpacing(10)
        self.player = VideoPlayer()
        self.player.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.player.positionChanged.connect(self._on_player_pos)
        self.player.playingChanged.connect(self._on_playing)
        right.addWidget(self.player, 1)
        transport = QHBoxLayout()
        self.btn_play = QPushButton("▶  Guarda la clip")
        self.btn_play.clicked.connect(self._toggle_play)
        self.cur_lbl = QLabel("0:00.0")
        self.cur_lbl.setObjectName("muted")
        self.dur_lbl = QLabel("")
        self.dur_lbl.setObjectName("muted")
        transport.addWidget(self.btn_play)
        transport.addWidget(self.cur_lbl)
        transport.addStretch(1)
        transport.addWidget(self.dur_lbl)
        right.addLayout(transport)
        self.trim = TrimSlider()
        self.trim.seekRequested.connect(self._seek)
        self.trim.startChanged.connect(lambda t: self._live("start", t))
        self.trim.endChanged.connect(lambda t: self._live("end", t))
        self.trim.released.connect(self._after_drag)
        right.addWidget(self.trim)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        self.ctrl = []
        self.start_lbl, self.end_lbl = QLabel("0:00.0"), QLabel("0:00.0")
        for r, (which, name, lbl) in enumerate((("start", "Inizio", self.start_lbl),
                                                ("end", "Fine", self.end_lbl))):
            n = QLabel(name)
            n.setObjectName("muted")
            lbl.setStyleSheet("font-weight:600;")
            lbl.setMinimumWidth(60)
            grid.addWidget(n, r, 0)
            grid.addWidget(lbl, r, 1)
            for c, (txt, delta) in enumerate((("−1 s", -1.0), ("+1 s", 1.0))):
                b = QPushButton(txt)
                b.setObjectName("small")
                b.clicked.connect(lambda _=False, w=which, d=delta: self._nudge(w, d))
                grid.addWidget(b, r, 2 + c)
                self.ctrl.append(b)
            here = QPushButton("Imposta qui")
            here.setObjectName("small")
            here.setToolTip("Usa il punto in cui si trova il video adesso")
            here.clicked.connect(lambda _=False, w=which: self._set_here(w))
            grid.addWidget(here, r, 4)
            self.ctrl.append(here)
        grid.setColumnStretch(5, 1)
        right.addLayout(grid)

        tl_label = QLabel("Tutta la partita")
        tl_label.setObjectName("muted")
        right.addWidget(tl_label)
        self.timeline = ClipTimeline()
        self.timeline.clipClicked.connect(self.list.setCurrentRow)
        self.timeline.seekRequested.connect(self._seek)
        right.addWidget(self.timeline)
        body.addLayout(right, 1)
        root.addLayout(body, 1)

        # ---- barra in basso
        bar = card()
        bb = QHBoxLayout(bar)
        bb.setContentsMargins(18, 12, 18, 12)
        bb.setSpacing(14)
        tv = QVBoxLayout()
        tv.setSpacing(2)
        self.total_lbl = QLabel("")
        self.total_lbl.setObjectName("h2")
        self.target_lbl = QLabel("")
        self.target_lbl.setObjectName("muted")
        tv.addWidget(self.total_lbl)
        tv.addWidget(self.target_lbl)
        bb.addLayout(tv)
        self.total_bar = QProgressBar()
        self.total_bar.setRange(0, 1000)
        self.total_bar.setMinimumWidth(200)
        bb.addWidget(self.total_bar, 1)
        self.btn_times = QPushButton("Minutaggi")
        self.btn_times.setToolTip("Salva i tempi precisi di «meta», «calcio» e «inizio» "
                                  "sulla registrazione intera")
        self.btn_times.clicked.connect(self.timecodesRequested)
        bb.addWidget(self.btn_times)
        self.btn_fit = QPushButton("Adatta alla durata massima")
        self.btn_fit.clicked.connect(self._fit)
        new = QPushButton("Nuova partita")
        new.setObjectName("flat")
        new.clicked.connect(self.newMatchRequested)
        self.btn_export = QPushButton("Crea highlights  →")
        self.btn_export.setObjectName("primary")
        self.btn_export.clicked.connect(self._export)
        bb.addWidget(self.btn_fit)
        bb.addWidget(new)
        bb.addWidget(self.btn_export)
        root.addWidget(bar)

        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self._toggle_play)
        self._enable_edit(False)

    # ---- caricamento
    def load(self, result, media, settings):
        self.media, self.duration, self.settings = media, result.duration, settings
        self.clips = result.clips
        self._cursor = 0.0
        self.timeline.set_data(result.duration, result.energy, result.whistles)
        msgs = [m for m in result.messages if m]
        self.banner.setVisible(bool(msgs))
        self.banner_lbl.setText("\n".join("• " + m for m in msgs))
        self.player.load(media)
        self._populate(0 if self.clips else -1)

    def stop(self):
        self.player.pause()

    # ---- elenco
    def _populate(self, select):
        self.list.blockSignals(True)
        self.list.clear()
        self.rows = []
        for i, c in enumerate(self.clips):
            item = QListWidgetItem()
            row = ClipRow(c)
            row.toggled.connect(lambda on, i=i: self._toggle(i, on))
            item.setSizeHint(QSize(340, 80 if c.note else 60))
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
            self.rows.append(row)
        self.list.blockSignals(False)
        self.count.setText(f"{len(self.clips)} azioni" if self.clips else "nessuna")
        self.sel = -1
        if 0 <= select < len(self.clips):
            self.list.setCurrentRow(select)
        else:
            self._enable_edit(False)
            self.timeline.set_clips(self.clips, -1)
        self._update_total()

    def _enable_edit(self, on):
        for w in (self.btn_play, self.btn_del, *self.ctrl):
            w.setEnabled(on)
        self.btn_add.setEnabled(bool(self.media))
        self.trim.setEnabled(on)

    def _select(self, row):
        self.sel = row
        if not (0 <= row < len(self.clips)):
            self._enable_edit(False)
            return
        self._enable_edit(True)
        c = self.clips[row]
        self._fit_window(c)
        self.trim.set_range(c.start, c.end, theme.kind_color(c.kind))
        self._labels()
        self._seek(c.start)
        self.timeline.set_clips(self.clips, row)

    def _fit_window(self, c):
        self.trim.set_window(max(0.0, c.start - 12), min(self.duration, c.end + 12))

    def _labels(self):
        c = self.clips[self.sel]
        self.start_lbl.setText(fmt_time(c.start, True))
        self.end_lbl.setText(fmt_time(c.end, True))
        self.dur_lbl.setText(f"clip di {c.duration:.0f} s")

    def _refresh_all(self):
        for r in self.rows:
            r.refresh()
        self.timeline.set_clips(self.clips, self.sel)
        self._update_total()

    def _toggle(self, i, on):
        self.clips[i].enabled = on
        self.rows[i].refresh()
        self.timeline.set_clips(self.clips, self.sel)
        self._update_total()

    # ---- regolazione
    def _set_bounds(self, start=None, end=None):
        c = self.clips[self.sel]
        s = c.start if start is None else start
        e = c.end if end is None else end
        s = max(0.0, min(s, e - 2))
        e = min(self.duration, max(e, s + 2))
        c.start, c.end = s, e
        self.trim.set_range(s, e)
        self._labels()
        self.rows[self.sel].refresh()
        self.timeline.set_clips(self.clips, self.sel)
        self._update_total()

    def _live(self, which, t):
        if self.sel < 0:
            return
        self._set_bounds(**{which: t})
        self._seek(t if which == "start" else max(0.0, t - 0.5))

    def _after_drag(self):
        if self.sel >= 0:
            self._fit_window(self.clips[self.sel])

    def _nudge(self, which, delta):
        if self.sel < 0:
            return
        c = self.clips[self.sel]
        t = (c.start if which == "start" else c.end) + delta
        self._set_bounds(**{which: t})
        self._fit_window(self.clips[self.sel])
        c = self.clips[self.sel]
        self._seek(c.start if which == "start" else max(0.0, c.end - 0.5))

    def _set_here(self, which):
        if self.sel < 0:
            return
        self._set_bounds(**{which: self._cursor})
        self._fit_window(self.clips[self.sel])

    # ---- player
    def _seek(self, t):
        self.player.seek(t)
        self._moved(t)

    def _moved(self, t):
        self._cursor = t
        self.trim.set_playhead(t)
        self.timeline.set_playhead(t)
        self.cur_lbl.setText(fmt_time(t, True))

    def _on_player_pos(self, t):
        self._moved(t)

    def _on_playing(self, playing):
        self.btn_play.setText("⏸  Pausa" if playing else "▶  Guarda la clip")

    def _toggle_play(self):
        if self.sel < 0 or not self.isVisible():
            return
        if self.player.is_playing():
            self.player.pause()
            return
        c = self.clips[self.sel]
        pos = self.player.position()
        if not (c.start <= pos < c.end - 0.3):
            pos = c.start
        self.player.play_range(pos, c.end)

    # ---- azioni
    def _add(self):
        if not self.media:
            return
        t = self._cursor
        c = Clip(max(0.0, t - 20), min(self.duration, t + 10), "manuale",
                 source="manuale", note="aggiunta a mano")
        self.clips = relabel(self.clips + [c])
        self._populate(self.clips.index(c))

    def _delete(self):
        if self.sel < 0:
            return
        del self.clips[self.sel]
        self.clips = relabel(self.clips)
        self._populate(min(self.sel, len(self.clips) - 1))

    def _fit(self):
        if fit_to_target(self.clips, self.settings.target_seconds, self.settings.min_clip_seconds):
            self._refresh_all()
            if self.sel >= 0:
                c = self.clips[self.sel]
                self._fit_window(c)
                self.trim.set_range(c.start, c.end)
                self._labels()

    def _update_total(self):
        total = sum(c.duration for c in self.clips if c.enabled)
        n = sum(1 for c in self.clips if c.enabled)
        target = max(1.0, self.settings.target_seconds)
        over = total > target + 1
        self.total_lbl.setText(f"{fmt_time(total)}  ·  {n} clip")
        self.target_lbl.setText(
            f"Oltre il massimo di {fmt_time(target)}" if over else f"Massimo {fmt_time(target)}")
        self.target_lbl.setStyleSheet(f"color:{theme.WARN};" if over else "")
        self.total_bar.setValue(int(min(1.0, total / target) * 1000))
        self.total_bar.setProperty("over", over)
        repolish(self.total_bar)
        self.btn_fit.setEnabled(over)
        self.btn_export.setEnabled(n > 0)

    def _export(self):
        ranges = [(c.start, c.end) for c in self.clips if c.enabled]
        if ranges:
            self.player.pause()
            self.exportRequested.emit(ranges)


# ------------------------------------------------------------------ finestra di esportazione
class ExportDialog(QDialog):
    def __init__(self, parent, default_out, has_report=False):
        super().__init__(parent)
        self.setWindowTitle("Crea highlights")
        self.setMinimumWidth(600)
        self.music = None
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(10)
        t = QLabel("Crea il video")
        t.setObjectName("big")
        v.addWidget(t)
        lab = QLabel("Salva come")
        lab.setObjectName("muted")
        v.addWidget(lab)
        row = QHBoxLayout()
        self.out = QLineEdit(default_out)
        change = QPushButton("Cambia…")
        change.clicked.connect(self._choose_out)
        row.addWidget(self.out, 1)
        row.addWidget(change)
        v.addLayout(row)

        v.addSpacing(8)
        self.chk = QCheckBox("Aggiungi musica (facoltativo)")
        self.chk.toggled.connect(self._sync)
        v.addWidget(self.chk)
        self.mbox = QFrame()
        self.mbox.setObjectName("card")
        ml = QGridLayout(self.mbox)
        ml.setContentsMargins(16, 14, 16, 14)
        ml.setHorizontalSpacing(12)
        ml.setVerticalSpacing(10)
        self.song = QLabel("Nessun brano scelto")
        self.song.setObjectName("muted")
        pick = QPushButton("Scegli brano…")
        pick.clicked.connect(self._choose_song)
        ml.addWidget(self.song, 0, 0, 1, 2)
        ml.addWidget(pick, 0, 2)
        self.v_music, self.v_orig = QSlider(Qt.Horizontal), QSlider(Qt.Horizontal)
        for r, (name, sl, val) in enumerate((("Volume musica", self.v_music, 35),
                                             ("Audio del campo", self.v_orig, 100)), start=1):
            sl.setRange(0, 100)
            sl.setValue(val)
            val_lbl = QLabel(f"{val}%")
            val_lbl.setMinimumWidth(40)
            sl.valueChanged.connect(lambda x, l=val_lbl: l.setText(f"{x}%"))
            ml.addWidget(QLabel(name), r, 0)
            ml.addWidget(sl, r, 1)
            ml.addWidget(val_lbl, r, 2)
        ml.setColumnStretch(1, 1)
        note = QLabel("Se pubblichi il video online usa musica libera da diritti: "
                      "un brano commerciale può far silenziare o rimuovere il video.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        ml.addWidget(note, 3, 0, 1, 3)
        v.addWidget(self.mbox)
        self.chk_script = QCheckBox("Crea anche il copione e il riassunto (file di testo)")
        self.chk_script.setChecked(True)
        self.chk_script.setVisible(has_report)
        v.addWidget(self.chk_script)
        v.addSpacing(8)
        foot = QHBoxLayout()
        foot.addStretch(1)
        cancel = QPushButton("Annulla")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Crea video")
        ok.setObjectName("primary")
        ok.clicked.connect(self._accept)
        foot.addWidget(cancel)
        foot.addWidget(ok)
        v.addLayout(foot)
        self._sync(False)

    def _sync(self, on):
        self.mbox.setEnabled(on)
        self.mbox.setVisible(on)
        self.adjustSize()

    def _choose_out(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salva gli highlights", self.out.text(),
                                              "Video MP4 (*.mp4)")
        if path:
            self.out.setText(path if path.lower().endswith(".mp4") else path + ".mp4")

    def _choose_song(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Scegli il brano", "", "Audio (*.mp3 *.wav *.m4a *.aac *.flac *.ogg);;Tutti i file (*.*)")
        if path:
            self.music = path
            self.song.setText(os.path.basename(path))
            self.song.setStyleSheet("")

    def _accept(self):
        if self.chk.isChecked() and not self.music:
            QMessageBox.information(self, "Musica", "Scegli un brano, oppure togli la spunta.")
            return
        if not self.out.text().strip():
            return
        self.accept()

    def values(self):
        on = self.chk.isChecked()
        return {"out": self.out.text().strip(),
                "music": self.music if on else None,
                "music_volume": self.v_music.value() / 100.0,
                "original_volume": self.v_orig.value() / 100.0,
                "script": self.chk_script.isVisibleTo(self) and self.chk_script.isChecked()}


# ------------------------------------------------------------------------ pagina 4
class ExportPage(QWidget):
    cancelRequested = Signal()
    backRequested = Signal()
    newRequested = Signal()

    def __init__(self):
        super().__init__()
        self.out = None
        outer = QHBoxLayout(self)
        outer.addStretch(1)
        col = QVBoxLayout()
        colw = QWidget()
        colw.setLayout(col)
        colw.setFixedWidth(560)
        outer.addWidget(colw)
        outer.addStretch(1)
        col.addStretch(2)
        self.title = QLabel("Sto creando il video")
        self.title.setObjectName("title")
        self.sub = QLabel("")
        self.sub.setObjectName("muted")
        self.sub.setWordWrap(True)
        col.addWidget(self.title)
        col.addWidget(self.sub)
        col.addSpacing(14)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        col.addWidget(self.bar)
        self.pct = QLabel("0%")
        self.pct.setObjectName("muted")
        col.addWidget(self.pct)
        col.addSpacing(12)
        self.cancel = QPushButton("Annulla")
        self.cancel.clicked.connect(self.cancelRequested)
        col.addWidget(self.cancel, 0, Qt.AlignRight)
        self.done_box = QWidget()
        dl = QVBoxLayout(self.done_box)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(8)
        self.btn_watch = QPushButton("▶  Guarda il video")
        self.btn_watch.setObjectName("primary")
        self.btn_watch.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.out)))
        self.btn_folder = QPushButton("Mostra nella cartella")
        self.btn_folder.clicked.connect(lambda: open_folder_of(self.out))
        self.script = None
        self.btn_script = QPushButton("Apri il copione")
        self.btn_script.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.script)))
        back = QPushButton("Torna alle clip")
        back.clicked.connect(self.backRequested)
        new = QPushButton("Nuova partita")
        new.setObjectName("flat")
        new.clicked.connect(self.newRequested)
        for b in (self.btn_watch, self.btn_folder, self.btn_script, back, new):
            dl.addWidget(b)
        col.addWidget(self.done_box)
        col.addStretch(3)
        self.start()

    def start(self, info=""):
        self.out = None
        self.script = None
        self.title.setText("Sto creando il video")
        self.sub.setText(info)
        self.bar.setValue(0)
        self.pct.setText("0%")
        self.bar.show()
        self.pct.show()
        self.cancel.show()
        self.done_box.hide()

    def update_progress(self, f, _text=""):
        self.bar.setValue(int(f * 1000))
        self.pct.setText(f"{f * 100:.0f}%")

    def finished(self, out):
        self.out = out
        self.title.setText("Highlights pronti")
        self.sub.setText(out)
        self.bar.hide()
        self.pct.hide()
        self.cancel.hide()
        self.btn_script.setVisible(bool(self.script))
        self.done_box.show()


# ------------------------------------------------------------------------ finestra
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rugby Highlights")
        self.resize(1260, 820)
        self.setMinimumSize(1060, 720)
        self._worker = None
        self._mode = None
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.setContentsMargins(30, 18, 30, 8)
        brand = QLabel("Rugby Highlights")
        brand.setObjectName("brand")
        self.steps = StepBar(["Partita", "Analisi", "Revisione"])
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("muted")
        header.addWidget(brand, 1)
        header.addWidget(self.steps)
        header.addWidget(ver, 1, Qt.AlignRight)
        v.addLayout(header)
        self.stack = QStackedWidget()
        v.addWidget(self.stack, 1)
        self.setup = SetupPage()
        self.analysis = AnalysisPage()
        self.review = ReviewPage()
        self.export = ExportPage()
        for p in (self.setup, self.analysis, self.review, self.export):
            self.stack.addWidget(p)

        self.setup.analyzeRequested.connect(self._start_analysis)
        self.analysis.cancelRequested.connect(self._cancel)
        self.export.cancelRequested.connect(self._cancel)
        self.review.exportRequested.connect(self._start_export)
        self.review.timecodesRequested.connect(self._save_timecodes)
        self.review.newMatchRequested.connect(self._new_match)
        self.export.backRequested.connect(lambda: self._go(2))
        self.export.newRequested.connect(self._new_match)
        QTimer.singleShot(400, self._startup_check)

    def _go(self, page):
        self.stack.setCurrentIndex(page)
        self.steps.set_step(min(page, 2))

    def _startup_check(self):
        try:
            find_binary("ffmpeg")
        except FileNotFoundError:
            QMessageBox.warning(self, "Attenzione",
                                "ffmpeg non trovato: il programma non può funzionare.\n"
                                "Reinstalla Rugby Highlights.")
        if not find_vosk_model():
            self.setup.note.setText(
                "Attenzione: modello vocale non trovato, non potrò riconoscere «meta» e «calcio».")

    # ---- lavori in background
    def _run(self, fn, mode, on_done):
        w = Worker(fn)
        self._worker, self._mode = w, mode
        w.progress.connect(self._on_progress)
        w.done.connect(on_done)
        w.failed.connect(self._on_failed)
        w.cancelled.connect(self._on_cancelled)
        w.start()

    def _on_progress(self, f, text):
        (self.analysis if self._mode == "analysis" else self.export).update_progress(f, text)

    def _cancel(self):
        if self._worker:
            self._worker.cancel()

    def _on_failed(self, msg):
        QMessageBox.critical(self, "Errore", msg)
        self._go(0 if self._mode == "analysis" else 2)

    def _on_cancelled(self):
        if self._mode == "export" and getattr(self, "_out", None) and os.path.exists(self._out):
            try:
                os.remove(self._out)
            except OSError:
                pass
        self._go(0 if self._mode == "analysis" else 2)

    # ---- analisi
    def _start_analysis(self):
        if not self.setup.paths:
            return
        settings, expected = self.setup.settings(), self.setup.expected()
        try:
            media = self.setup.media()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Video", f"Non riesco a leggere i video.\n\n{e}")
            return
        self._settings, self._media = settings, media
        self.analysis.reset()
        self._go(1)
        self._run(lambda cb: analyze(media, settings, expected, cb), "analysis", self._analysis_done)

    def _analysis_done(self, result):
        self._result = result
        self.review.load(result, self._media, self._settings)
        self._go(2)

    # ---- minutaggi
    def _save_timecodes(self):
        base = os.path.splitext(self._media.paths[0])[0] + "_minutaggi"
        path, _ = QFileDialog.getSaveFileName(self, "Salva i minutaggi", base + ".txt",
                                              "Testo (*.txt)")
        if not path:
            return
        try:
            txt, csv = timecodes.save(os.path.splitext(path)[0], self._result, self._media,
                                      self._settings, self.review.clips)
        except OSError as e:
            QMessageBox.warning(self, "Minutaggi", f"Non riesco a salvare il file.\n\n{e}")
            return
        try:
            xml, mcsv = premiere.save(os.path.splitext(path)[0] + "_premiere", self._result,
                                      self._media, self._settings, self.review.clips)
            extra = (f"\n\nPer Premiere:\n{xml}\n{mcsv}\n(File > Importa: l'XML crea una sequenza "
                     "con i marcatori)")
        except Exception:  # noqa: BLE001
            extra = ""
        QMessageBox.information(self, "Minutaggi",
                                f"Salvati:\n{txt}\n{csv}\n\nIl file .csv si apre in Excel.{extra}")
        open_folder_of(txt)

    # ---- esportazione
    def _start_export(self, ranges):
        base = os.path.splitext(self._media.paths[0])[0] + "_highlights.mp4"
        report = self.setup.report()
        dlg = ExportDialog(self, base, has_report=report is not None)
        if dlg.exec() != QDialog.Accepted:
            return
        opts = dlg.values()
        script_clips = [c for c in self.review.clips if c.enabled]
        script_all, result = list(self.review.clips), self._result
        names = self.setup.names()
        script_path = (os.path.splitext(opts["out"])[0] + "_copione.txt") if opts["script"] else None
        out, s, media = opts["out"], self._settings, self._media
        self._out = out
        total = sum(e - s_ for s_, e in ranges)
        self.export.start(f"{len(ranges)} clip · {fmt_time(total)}"
                          + ("  ·  con musica" if opts["music"] else ""))
        self._go(3)

        def job(cb):
            export_montage(media, ranges, out, fade=s.fade, crf=s.crf,
                           progress=lambda f: cb(f, ""), music=opts["music"],
                           music_volume=opts["music_volume"],
                           original_volume=opts["original_volume"])
            try:
                timecodes.save(os.path.splitext(out)[0] + "_minutaggi", result, media, s, script_all)
                premiere.save(os.path.splitext(out)[0] + "_premiere", result, media, s, script_all)
            except Exception:  # noqa: BLE001
                pass            # i minutaggi sono un extra: non fermano il video
            if script_path:
                text = build_script(report, script_clips, names,
                                    title=os.path.splitext(os.path.basename(out))[0].replace("_", " "))
                with open(script_path, "w", encoding="utf-8-sig") as f:
                    f.write(text)
                self.export.script = script_path
            return out

        self._run(job, "export", self.export.finished)

    def _new_match(self):
        self.review.stop()
        self.setup.clear()
        self._go(0)

    def closeEvent(self, e):
        self._cancel()
        self.review.stop()
        super().closeEvent(e)


def _excepthook(exc_type, exc, tb):
    """Errori imprevisti: li mostra e li salva (senza console non si vedrebbero)."""
    import tempfile
    import traceback
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    log = os.path.join(tempfile.gettempdir(), "rugby_highlights_errore.txt")
    try:
        with open(log, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    try:
        QMessageBox.critical(None, "Errore imprevisto",
                             f"Qualcosa è andato storto.\n\n{text[-1000:]}\n\nDettagli salvati in:\n{log}")
    except Exception:  # noqa: BLE001
        pass


def main():
    sys.excepthook = _excepthook
    app = QApplication(sys.argv)
    app.setApplicationName("Rugby Highlights")
    app.setStyle("Fusion")
    app.setStyleSheet(theme.build_qss())
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
