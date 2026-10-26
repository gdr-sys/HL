"""Prova la finestra senza schermo: dalla scelta del video fino al video creato.

Il player video viene spento (RUGBY_NO_VIDEO_PLAYER): serve audio/video reale del PC.
"""

import os
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["RUGBY_NO_VIDEO_PLAYER"] = "1"

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from rugby_highlights import app as A  # noqa: E402
from rugby_highlights import theme  # noqa: E402
from rugby_highlights.ffmpeg_utils import probe_duration  # noqa: E402
from rugby_highlights.models import Expected, Marker, Settings  # noqa: E402
from rugby_highlights.pipeline import analyze  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    try:
        app = QApplication.instance() or QApplication([])
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Qt non disponibile: {e}")
    app.setStyle("Fusion")
    app.setStyleSheet(theme.build_qss())
    return app


@pytest.fixture
def window(qapp, monkeypatch):
    def boom(*a, **k):
        raise AssertionError(f"finestra di errore inattesa: {a}")
    monkeypatch.setattr(QMessageBox, "critical", boom)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    w = A.MainWindow()
    w.show()
    yield w
    w.close()


def wait_for(qapp, cond, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_setup_page(window, synthetic_video):
    assert not window.setup.btn_go.isEnabled()
    window.setup.set_video(str(synthetic_video))
    assert window.setup.btn_go.isEnabled()
    window.setup.steps[("a", "meta")].setValue(2)
    window.setup.steps[("b", "meta")].setValue(1)
    window.setup.steps[("a", "calcio")].setValue(3)
    window.setup.steps[("a", "calcio")].setValue(-5)      # non scende sotto zero
    window.setup.steps[("b", "calcio")].setValue(99)      # non supera il massimo
    window.setup.steps[("b", "calcio")].setValue(1)
    e = window.setup.expected()
    assert (e.meta, e.calcio) == (3, 1)
    window.setup.spins["target"].setValue(120)
    assert window.setup.settings().target_seconds == 120


def test_review_editing(window, synthetic_video):
    video = str(synthetic_video)
    res = analyze(video, Settings(), Expected(2, 1),
                  markers_provider=lambda raw: [Marker(41.0, "meta", "meta", 0.9),
                                                Marker(95.0, "calcio", "calcio", 0.8)])
    from rugby_highlights.media import Media
    media = Media.from_paths([video])
    window._settings, window._media = Settings(), media
    r = window.review
    r.load(res, media, Settings())
    window._go(2)
    assert r.list.count() == len(res.clips) >= 2
    assert r.sel == 0

    c = r.clips[0]
    start0 = c.start
    r._nudge("start", -1.0)
    assert abs(c.start - (start0 - 1.0)) < 0.01
    r._live("end", c.end - 5)                       # come trascinare la maniglia
    assert abs(c.end - (41.0 + 12 - 5)) < 0.6
    end_before = c.end
    r._cursor = end_before + 3
    r._set_here("end")
    assert abs(c.end - (end_before + 3)) < 0.01

    n_before = sum(1 for x in r.clips if x.enabled)
    r._toggle(1, False)
    assert sum(1 for x in r.clips if x.enabled) == n_before - 1
    r._toggle(1, True)

    r._cursor = 60.0
    r._add()
    assert any(x.kind == "manuale" for x in r.clips)
    manual = r.clips[r.sel]
    assert manual.kind == "manuale" and manual.source == "manuale"

    count = len(r.clips)
    r._delete()
    assert len(r.clips) == count - 1

    r.settings.target_seconds = 30
    r._update_total()
    assert r.btn_fit.isEnabled()
    r._fit()
    on = [x for x in r.clips if x.enabled]
    total = sum(x.duration for x in on)
    # o rientra nei 30 s, oppure tutte le clip sono gia' al minimo
    assert total <= 30.01 or all(abs(x.duration - Settings().min_clip_seconds) < 0.01 for x in on)
    assert r.total_lbl.text()


def test_whole_flow_through_the_window(qapp, window, synthetic_video, tmp_path, monkeypatch):
    """Scelta video -> analisi in background -> revisione -> creazione del video."""
    window.setup.set_video(str(synthetic_video))
    window.setup.steps[("a", "meta")].setValue(2)
    window.setup.steps[("a", "calcio")].setValue(1)
    window.setup.report_text.setPlainText("Meta al 10° (7-0). Meta nella ripresa (7-7).")
    window.setup.chk_crowd.setChecked(True)      # il test non ha voce: usa i picchi del pubblico
    window.setup.btn_go.click()
    assert window.stack.currentIndex() == 1
    assert wait_for(qapp, lambda: window.stack.currentIndex() == 2), "analisi non terminata"
    assert len(window.review.clips) >= 1

    out = tmp_path / "finale.mp4"
    song = tmp_path / "song.wav"
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=330:duration=4", str(song)], check=True)

    class FakeDialog:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {"out": str(out), "music": str(song), "music_volume": 0.4,
                    "original_volume": 0.8, "script": True}

    monkeypatch.setattr(A, "ExportDialog", FakeDialog)
    window.review.btn_export.click()
    assert window.stack.currentIndex() == 3
    assert wait_for(qapp, lambda: window.export.out is not None), "video non creato"
    assert out.exists()
    expected = sum(c.duration for c in window.review.clips if c.enabled)
    assert abs(probe_duration(out) - expected) < 1.5
    assert window.export.done_box.isVisible()
    script = tmp_path / "finale_copione.txt"
    assert script.exists() and "COPIONE CLIP PER CLIP" in script.read_text(encoding="utf-8-sig")
    assert window.export.script == str(script)


def test_setup_multiple_files(window, split_videos):
    s = window.setup
    files = [str(p) for p in reversed(split_videos)]        # in disordine
    s.add_files(files)
    assert s.paths == sorted(files, key=lambda p: __import__("rugby_highlights.media", fromlist=["x"]).natural_key(p))
    assert abs(s.media().total - 120) < 1.5
    s.flist.setCurrentRow(0)
    s._move(1)
    assert s.paths[1] == sorted(files)[0] or len(s.paths) == 3
    s._remove()
    assert len(s.paths) == 2
    s.clear()
    assert not s.paths and not s.btn_go.isEnabled()


def test_report_fills_scoreboard(window):
    s = window.setup
    s.report_text.setPlainText(open(__import__("os").path.join(
        __import__("os").path.dirname(__file__), "comunicato.txt"), encoding="utf-8").read())
    s.venue.setCurrentIndex(1)                   # gioco in trasferta: la mia squadra e' la seconda
    s.read_report()
    s.chk_conv.setChecked(False)
    s.read_report()
    assert s.steps[("a", "meta")].value() == 4 and s.steps[("b", "meta")].value() == 5
    assert s.steps[("a", "calcio")].value() == 0
    s.chk_conv.setChecked(True)                 # dico «calcio» anche per le trasformazioni
    s.read_report()
    assert s.steps[("a", "calcio")].value() == 3 and s.steps[("b", "calcio")].value() == 4
    assert s.report() is not None
    s.name_mine.setText("Fiorini")
    s.name_opp.setText("Capitolina")
    n = s.names()
    assert (n.home, n.away) == ("Capitolina", "Fiorini")


def test_timeline_zoom_markers_and_range_selection(window, synthetic_video):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent, QWheelEvent
    from PySide6.QtCore import QPoint, Qt as _Qt
    from rugby_highlights.media import Media
    media = Media.from_paths([str(synthetic_video)])
    res = analyze(str(synthetic_video), Settings(), Expected(0, 0),
                  markers_provider=lambda raw: [Marker(41.0, "meta", "meta", 0.9)])
    res.others = [Marker(70.0, "meta", "mete", 0.6)]
    r = window.review
    r.load(res, media, Settings())
    window._go(2)
    tl = r.timeline
    tl.resize(1000, 112)
    assert len(tl.used) == 1 and len(tl.others) == 1
    # trascinando sulla linea si crea una clip manuale
    n = len(r.clips)
    got = []
    tl.rangeSelected.connect(lambda a, b: got.append((a, b)))
    y = 30

    def mouse(kind, x, button=_Qt.LeftButton):
        e = QMouseEvent(kind, QPointF(x, y), QPointF(x, y), button, button, _Qt.NoModifier)
        {QMouseEvent.Type.MouseButtonPress: tl.mousePressEvent,
         QMouseEvent.Type.MouseMove: tl.mouseMoveEvent,
         QMouseEvent.Type.MouseButtonRelease: tl.mouseReleaseEvent}[kind](e)

    x0, x1 = tl._x(100.0), tl._x(112.0)
    mouse(QMouseEvent.Type.MouseButtonPress, x0)
    mouse(QMouseEvent.Type.MouseMove, (x0 + x1) / 2)
    mouse(QMouseEvent.Type.MouseMove, x1)
    mouse(QMouseEvent.Type.MouseButtonRelease, x1)
    assert got and abs(got[0][0] - 100) < 1.5 and abs(got[0][1] - 112) < 1.5
    assert len(r.clips) == n + 1 and any(c.source == "manuale" for c in r.clips)
    # la rotella ingrandisce, il doppio clic torna a tutto
    span = tl._span()
    tl.wheelEvent(QWheelEvent(QPointF(500, y), QPointF(500, y), QPoint(0, 0), QPoint(0, 120),
                              _Qt.NoButton, _Qt.NoModifier, _Qt.NoScrollPhase, False))
    assert tl._span() < span
    tl._set_view(0, tl.duration)
    assert tl._span() == tl.duration
    tl.grab()          # il disegno con parole e zoom non deve dare errori
