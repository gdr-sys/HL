"""Interfaccia grafica (Tkinter, inclusa in Python: nessuna dipendenza in piu')."""

import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import __version__
from .ffmpeg_utils import export_montage, extract_frame, probe_duration
from .models import Cancelled, Clip, Expected, Settings
from .paths import find_binary, find_vosk_model
from .pipeline import analyze
from .planner import fit_to_target, relabel


def fmt(t):
    t = int(round(max(0, t)))
    if t >= 3600:
        return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"
    return f"{t // 60}:{t % 60:02d}"


def parse_time(text):
    parts = [float(p.replace(",", ".")) for p in text.strip().split(":")]
    secs = 0.0
    for p in parts:
        secs = secs * 60 + p
    return secs


def open_path(path):
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Rugby Highlights {__version__}")
        self.geometry("1020x800")
        self.minsize(920, 720)
        self.video = None
        self.duration = 0.0
        self.clips = []
        self.sel = None
        self._updating = False
        self.cancel_flag = False
        self.busy = False
        self.q = queue.Queue()
        self.tmp = tempfile.mkdtemp(prefix="rugbyhl_ui_")
        self.thumb_token = {"start": 0, "end": 0}
        self.thumb_imgs = {}
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._poll)
        self.after(300, self._startup_check)

    # ------------------------------------------------------------------ UI
    def _build(self):
        pad = {"padx": 10, "pady": 5}

        f1 = ttk.LabelFrame(self, text="1. Video della partita")
        f1.pack(fill="x", **pad)
        self.video_var = tk.StringVar()
        ttk.Entry(f1, textvariable=self.video_var).pack(
            side="left", fill="x", expand=True, padx=8, pady=8)
        ttk.Button(f1, text="Sfoglia…", command=self._browse).pack(side="left", padx=8)

        row = ttk.Frame(self)
        row.pack(fill="x", **pad)

        f2 = ttk.LabelFrame(row, text="2. Tabellino (punti segnati)")
        f2.pack(side="left", fill="y", padx=(0, 10))
        ttk.Label(f2, text="Mete").grid(row=0, column=1, padx=8, pady=(6, 0))
        ttk.Label(f2, text="Calci a punti").grid(row=0, column=2, padx=8, pady=(6, 0))
        self.exp = {}
        for r, (name, key) in enumerate((("La mia squadra", "a"), ("Avversari", "b")), start=1):
            ttk.Label(f2, text=name).grid(row=r, column=0, sticky="w", padx=8, pady=4)
            for c, kind in ((1, "meta"), (2, "calcio")):
                var = tk.StringVar(value="0")
                self.exp[(key, kind)] = var
                ttk.Spinbox(f2, from_=0, to=30, width=5, textvariable=var).grid(
                    row=r, column=c, padx=8, pady=4)
        ttk.Label(f2, text="Calci a punti = trasformazioni, punizioni, drop.\n"
                           "Serve per controllare che non manchi nulla.",
                  foreground="#555").grid(row=3, column=0, columnspan=3, padx=8, pady=(2, 6))

        f3 = ttk.LabelFrame(row, text="3. Opzioni")
        f3.pack(side="left", fill="both", expand=True)
        self.opt = {}
        options = (
            ("target", "Durata massima highlights (secondi)", 180, 30, 900),
            ("meta_post", "Dopo la meta, festeggiamenti (secondi)", 12, 0, 60),
            ("calcio_pre", "Prima del calcio (secondi)", 14, 2, 60),
            ("calcio_post", "Dopo il calcio (secondi)", 7, 0, 60),
            ("delay", "La parola la dico con ritardo di (secondi)", 0, 0, 20),
        )
        for r, (key, text, default, lo, hi) in enumerate(options):
            ttk.Label(f3, text=text).grid(row=r, column=0, sticky="w", padx=8, pady=3)
            var = tk.StringVar(value=str(default))
            self.opt[key] = var
            ttk.Spinbox(f3, from_=lo, to=hi, width=6, textvariable=var).grid(
                row=r, column=1, padx=8, pady=3)

        f_run = ttk.Frame(self)
        f_run.pack(fill="x", **pad)
        self.btn_analyze = ttk.Button(f_run, text="Analizza la partita", command=self._start_analyze)
        self.btn_analyze.pack(side="left")
        self.btn_cancel = ttk.Button(f_run, text="Annulla", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=8)
        self.progress = ttk.Progressbar(f_run, maximum=1.0)
        self.progress.pack(side="left", fill="x", expand=True, padx=8)
        self.status = tk.StringVar(value="Scegli il video e premi «Analizza la partita».")
        ttk.Label(self, textvariable=self.status, wraplength=960, justify="left").pack(
            fill="x", padx=12)

        f4 = ttk.LabelFrame(self, text="4. Clip trovate (clicca la casella per includere/escludere)")
        f4.pack(fill="both", expand=True, **pad)
        cols = ("use", "name", "start", "end", "dur", "note")
        self.tree = ttk.Treeview(f4, columns=cols, show="headings", selectmode="browse", height=8)
        for col, text, width, anchor in (
                ("use", "Incl.", 50, "center"), ("name", "Azione", 150, "w"),
                ("start", "Inizio", 80, "center"), ("end", "Fine", 80, "center"),
                ("dur", "Durata", 70, "center"), ("note", "Note", 520, "w")):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor=anchor, stretch=(col == "note"))
        sb = ttk.Scrollbar(f4, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        sb.pack(side="left", fill="y", pady=8, padx=(0, 8))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Button-1>", self._on_tree_click)

        f5 = ttk.LabelFrame(self, text="Modifica la clip selezionata")
        f5.pack(fill="x", **pad)
        sliders = ttk.Frame(f5)
        sliders.pack(side="left", fill="x", expand=True, padx=8, pady=6)
        self.lbl_start = tk.StringVar()
        self.lbl_end = tk.StringVar()
        ttk.Label(sliders, textvariable=self.lbl_start).grid(row=0, column=0, sticky="w")
        self.s_start = tk.Scale(sliders, orient="horizontal", resolution=0.5, showvalue=False,
                                command=self._on_start, length=420)
        self.s_start.grid(row=1, column=0, sticky="ew")
        ttk.Label(sliders, textvariable=self.lbl_end).grid(row=2, column=0, sticky="w")
        self.s_end = tk.Scale(sliders, orient="horizontal", resolution=0.5, showvalue=False,
                              command=self._on_end, length=420)
        self.s_end.grid(row=3, column=0, sticky="ew")
        sliders.columnconfigure(0, weight=1)
        for sc in (self.s_start, self.s_end):
            sc.bind("<ButtonRelease-1>", lambda _e: self._load_thumbs())
            sc.bind("<KeyRelease>", lambda _e: self._load_thumbs())
        thumbs = ttk.Frame(f5)
        thumbs.pack(side="left", padx=8, pady=6)
        self.img_start = ttk.Label(thumbs, text="(inizio)", anchor="center")
        self.img_start.grid(row=0, column=0, padx=4)
        self.img_end = ttk.Label(thumbs, text="(fine)", anchor="center")
        self.img_end.grid(row=0, column=1, padx=4)
        btns = ttk.Frame(f5)
        btns.pack(side="left", padx=8, pady=6)
        ttk.Button(btns, text="Anteprima clip", command=self._preview).pack(fill="x", pady=2)
        ttk.Button(btns, text="Elimina clip", command=self._delete).pack(fill="x", pady=2)
        ttk.Button(btns, text="Aggiungi clip a mano…", command=self._add_manual).pack(fill="x", pady=2)

        f6 = ttk.Frame(self)
        f6.pack(fill="x", padx=10, pady=(5, 12))
        self.total = tk.StringVar()
        ttk.Label(f6, textvariable=self.total, font=("", 10, "bold")).pack(side="left")
        self.btn_export = ttk.Button(f6, text="Crea highlights…", command=self._export)
        self.btn_export.pack(side="right")
        self.btn_fit = ttk.Button(f6, text="Adatta alla durata massima", command=self._fit)
        self.btn_fit.pack(side="right", padx=8)
        self._update_total()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _num(var, default, kind=float):
        try:
            return kind(str(var.get()).replace(",", "."))
        except (ValueError, tk.TclError):
            return default

    def _settings(self):
        s = Settings()
        s.target_seconds = self._num(self.opt["target"], 180.0)
        s.meta_post = self._num(self.opt["meta_post"], 12.0)
        s.calcio_pre = self._num(self.opt["calcio_pre"], 14.0)
        s.calcio_post = self._num(self.opt["calcio_post"], 7.0)
        s.delay_correction = self._num(self.opt["delay"], 0.0)
        return s

    def _expected(self):
        meta = sum(self._num(self.exp[(k, "meta")], 0, int) for k in "ab")
        calcio = sum(self._num(self.exp[(k, "calcio")], 0, int) for k in "ab")
        return Expected(meta, calcio)

    def _set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_analyze, self.btn_export, self.btn_fit):
            b.configure(state=state)
        self.btn_cancel.configure(state="normal" if busy else "disabled")

    def _startup_check(self):
        problems = []
        try:
            find_binary("ffmpeg")
        except FileNotFoundError:
            problems.append("ffmpeg non trovato: il programma non puo' funzionare. Reinstallalo.")
        if not find_vosk_model():
            problems.append("Modello vocale non trovato: non potro' riconoscere 'meta' e 'calcio'.")
        if problems:
            messagebox.showwarning("Attenzione", "\n".join(problems))

    # ------------------------------------------------------------ analysis
    def _browse(self):
        path = filedialog.askopenfilename(
            title="Scegli il video della partita",
            filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi *.mts *.m2ts *.mpg *.mpeg *.wmv"),
                       ("Tutti i file", "*.*")])
        if path:
            self.video_var.set(path)

    def _progress_cb(self, frac, text=""):
        if self.cancel_flag:
            raise Cancelled()
        self.q.put(("progress", frac, text))

    def _start_analyze(self):
        path = self.video_var.get().strip().strip('"')
        if not path or not os.path.isfile(path):
            messagebox.showerror("Video", "Scegli un file video valido.")
            return
        self.video = path
        self.cancel_flag = False
        self.clips = []
        self.sel = None
        self._refresh_tree()
        self._set_busy(True)
        settings, expected = self._settings(), self._expected()

        def work():
            try:
                res = analyze(path, settings, expected, self._progress_cb)
                self.q.put(("analyzed", res))
            except Cancelled:
                self.q.put(("cancelled",))
            except Exception as e:  # noqa: BLE001
                self.q.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _cancel(self):
        self.cancel_flag = True
        self.status.set("Annullo…")

    # -------------------------------------------------------------- tree
    def _refresh_tree(self, keep=None):
        self.tree.delete(*self.tree.get_children())
        for i, c in enumerate(self.clips):
            self.tree.insert("", "end", iid=str(i), values=self._row(c))
        if keep is not None and 0 <= keep < len(self.clips):
            self.tree.selection_set(str(keep))
        self._update_total()

    @staticmethod
    def _row(c):
        return ("☑" if c.enabled else "☐", c.label, fmt(c.start), fmt(c.end),
                f"{c.duration:.0f} s", c.note)

    def _update_total(self):
        total = sum(c.duration for c in self.clips if c.enabled)
        target = self._num(self.opt["target"], 180.0) if hasattr(self, "opt") else 180.0
        n = sum(1 for c in self.clips if c.enabled)
        warn = "  (oltre il massimo: usa «Adatta»)" if total > target + 1 else ""
        self.total.set(f"Totale: {fmt(total)} in {n} clip · massimo {fmt(target)}{warn}")

    def _on_tree_click(self, e):
        if self.tree.identify("region", e.x, e.y) != "cell" or self.tree.identify_column(e.x) != "#1":
            return
        iid = self.tree.identify_row(e.y)
        if iid:
            c = self.clips[int(iid)]
            c.enabled = not c.enabled
            self.tree.item(iid, values=self._row(c))
            self._update_total()

    def _on_select(self, _e=None):
        sel = self.tree.selection()
        if not sel:
            return
        self.sel = int(sel[0])
        c = self.clips[self.sel]
        lo, hi = max(0.0, c.start - 60), min(self.duration, c.end + 60)
        self._updating = True
        for sc in (self.s_start, self.s_end):
            sc.configure(from_=lo, to=hi)
        self.s_start.set(c.start)
        self.s_end.set(c.end)
        self._updating = False
        self._update_labels()
        self._load_thumbs()

    def _update_labels(self):
        if self.sel is None:
            return
        c = self.clips[self.sel]
        self.lbl_start.set(f"Inizio: {fmt(c.start)}")
        self.lbl_end.set(f"Fine: {fmt(c.end)}   (durata {c.duration:.0f} s)")

    def _on_start(self, _v):
        if self._updating or self.sel is None:
            return
        c = self.clips[self.sel]
        v = float(self.s_start.get())
        if abs(v - c.start) < 0.26:      # solo arrotondamento del cursore, non un movimento
            return
        c.start = min(v, c.end - 2)
        self._after_slider(c)

    def _on_end(self, _v):
        if self._updating or self.sel is None:
            return
        c = self.clips[self.sel]
        v = float(self.s_end.get())
        if abs(v - c.end) < 0.26:
            return
        c.end = max(v, c.start + 2)
        self._after_slider(c)

    def _after_slider(self, c):
        self.tree.item(str(self.sel), values=self._row(c))
        self._update_labels()
        self._update_total()

    # ---------------------------------------------------------- thumbnails
    def _load_thumbs(self):
        if self.sel is None or not self.video:
            return
        c = self.clips[self.sel]
        for which, t in (("start", c.start + 0.3), ("end", c.end - 0.3)):
            self.thumb_token[which] += 1
            token = self.thumb_token[which]
            out = os.path.join(self.tmp, f"{which}_{token}.png")

            def work(which=which, t=t, out=out, token=token):
                if extract_frame(self.video, t, out, width=240):
                    self.q.put(("thumb", which, out, token))

            threading.Thread(target=work, daemon=True).start()

    def _show_thumb(self, which, path, token):
        if token == self.thumb_token[which]:
            try:
                img = tk.PhotoImage(file=path)
                self.thumb_imgs[which] = img
                (self.img_start if which == "start" else self.img_end).configure(image=img, text="")
            except tk.TclError:
                pass
        try:
            os.remove(path)
        except OSError:
            pass

    # ------------------------------------------------------------- actions
    def _preview(self):
        if self.sel is None or not self.video:
            messagebox.showinfo("Anteprima", "Seleziona prima una clip.")
            return
        c = self.clips[self.sel]
        out = os.path.join(self.tmp, "anteprima.mp4")
        self._set_busy(True)
        self.status.set("Preparo l'anteprima…")

        def work():
            try:
                export_montage(self.video, [(c.start, c.end)], out, fade=0.0, preview=True)
                self.q.put(("preview", out))
            except Exception as e:  # noqa: BLE001
                self.q.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _delete(self):
        if self.sel is None:
            return
        del self.clips[self.sel]
        self.clips = relabel(self.clips)
        self.sel = None
        self._refresh_tree()

    def _add_manual(self):
        if not self.video:
            messagebox.showinfo("Clip a mano", "Scegli prima il video.")
            return
        text = simpledialog.askstring(
            "Aggiungi clip a mano",
            "A che punto del VIDEO succede l'azione? (mm:ss oppure h:mm:ss)\n"
            "Nota: e' il tempo del video, non il tempo di gioco del tabellino.",
            parent=self)
        if not text:
            return
        try:
            t = parse_time(text)
            if not self.duration:
                self.duration = probe_duration(self.video)
        except ValueError:
            messagebox.showerror("Clip a mano", "Formato non valido. Esempio: 23:45")
            return
        except RuntimeError as e:
            messagebox.showerror("Clip a mano", str(e))
            return
        c = Clip(max(0.0, t - 20), min(self.duration, t + 10), "manuale",
                 source="manuale", note="aggiunta a mano")
        self.clips = relabel(self.clips + [c])
        idx = self.clips.index(c)
        self._refresh_tree(keep=idx)

    def _fit(self):
        s = self._settings()
        if fit_to_target(self.clips, s.target_seconds, s.min_clip_seconds):
            self._refresh_tree(keep=self.sel)
            self.status.set("Clip accorciate (dall'inizio) per stare nella durata massima.")
        else:
            self.status.set("Non serve accorciare, oppure le clip sono gia' al minimo.")

    def _export(self):
        ranges = [(c.start, c.end) for c in self.clips if c.enabled]
        if not ranges:
            messagebox.showinfo("Highlights", "Nessuna clip selezionata.")
            return
        base = os.path.splitext(os.path.basename(self.video or "partita"))[0]
        out = filedialog.asksaveasfilename(
            title="Salva gli highlights", defaultextension=".mp4",
            initialfile=f"{base}_highlights.mp4", filetypes=[("Video MP4", "*.mp4")])
        if not out:
            return
        s = self._settings()
        self.cancel_flag = False
        self._set_busy(True)

        def work():
            try:
                export_montage(self.video, ranges, out, fade=s.fade, crf=s.crf,
                               progress=lambda f: self._progress_cb(f, "Creo il video…"))
                self.q.put(("exported", out))
            except Cancelled:
                self.q.put(("cancelled",))
            except Exception as e:  # noqa: BLE001
                self.q.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    # ---------------------------------------------------------- event loop
    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    self.progress["value"] = msg[1]
                    if msg[2]:
                        self.status.set(f"{msg[2]} {msg[1] * 100:.0f}%")
                elif kind == "analyzed":
                    res = msg[1]
                    self.duration = res.duration
                    self.clips = res.clips
                    self._set_busy(False)
                    self.progress["value"] = 0
                    self._refresh_tree(keep=0 if self.clips else None)
                    lines = list(res.messages) or ["Analisi completata."]
                    lines.append("Controlla le clip qui sotto, regola inizio e fine se serve, "
                                 "poi premi «Crea highlights».")
                    self.status.set("\n".join(lines))
                elif kind == "thumb":
                    self._show_thumb(msg[1], msg[2], msg[3])
                elif kind == "preview":
                    self._set_busy(False)
                    self.status.set("Anteprima pronta.")
                    open_path(msg[1])
                elif kind == "exported":
                    self._set_busy(False)
                    self.progress["value"] = 0
                    self.status.set(f"Highlights creati: {msg[1]}")
                    if messagebox.askyesno("Fatto", "Highlights creati.\nVuoi aprire la cartella?"):
                        open_path(os.path.dirname(msg[1]))
                elif kind == "cancelled":
                    self._set_busy(False)
                    self.progress["value"] = 0
                    self.status.set("Operazione annullata.")
                elif kind == "error":
                    self._set_busy(False)
                    self.progress["value"] = 0
                    self.status.set("Errore.")
                    messagebox.showerror("Errore", msg[1])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _close(self):
        self.cancel_flag = True
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.destroy()


def main():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
    App().mainloop()
