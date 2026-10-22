"""Prova di costruzione dell'interfaccia. Salta se non c'e' Tk o uno schermo."""

import pytest

tk = pytest.importorskip("tkinter")


def test_gui_builds_and_edits_clips(synthetic_video, monkeypatch):
    from tkinter import messagebox

    from rugby_highlights.gui import App
    from rugby_highlights.models import Clip

    monkeypatch.setattr(messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: None)
    try:
        app = App()
    except tk.TclError as e:
        pytest.skip(f"nessuno schermo disponibile: {e}")
    try:
        app.withdraw()
        app.video = str(synthetic_video)
        app.duration = 120.0
        app.clips = [Clip(10, 40, "meta", label="Meta 1"),
                     Clip(80, 100, "calcio", label="Calcio 1")]
        app._refresh_tree()
        assert "Totale: 0:50" in app.total.get()

        app.tree.selection_set("0")
        app.update()
        assert app.sel == 0

        # Con la finestra nascosta Tk non richiama da solo il comando del cursore:
        # lo chiamo io, come farebbe il movimento col mouse.
        app.s_start.set(15.0)
        app._on_start(None)
        assert abs(app.clips[0].start - 15.0) < 0.01
        app.s_end.set(35.0)
        app._on_end(None)
        assert abs(app.clips[0].end - 35.0) < 0.01

        app.clips[1].enabled = False
        app._update_total()
        assert "1 clip" in app.total.get()

        app._delete()
        assert len(app.clips) == 1 and app.clips[0].label == "Calcio 1"

        app.opt["target"].set("20")
        app.clips[0].enabled = True
        app.clips[0].start, app.clips[0].end = 0, 60
        app._fit()
        assert app.clips[0].duration < 60
    finally:
        app.destroy()
