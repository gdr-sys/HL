"""Prova la logica di lettura dei risultati vocali con un finto Vosk.

Il riconoscimento vero (modello italiano) si verifica solo con audio reale.
"""

import json
import sys
import types

from rugby_highlights.models import Settings


def _install_fake_vosk(monkeypatch, seen):
    class FakeRec:
        def __init__(self, model, sr, grammar=None):
            seen["grammar"] = grammar
            self.n = 0

        def SetWords(self, flag):
            pass

        def AcceptWaveform(self, data):
            self.n += 1
            return self.n == 2

        def Result(self):
            return json.dumps({"result": [
                {"word": "meta", "start": 1.5, "end": 1.9, "conf": 0.95},
                {"word": "calcio", "start": 3.0, "end": 3.4, "conf": 0.3},   # troppo incerta
                {"word": "ciao", "start": 4.0, "end": 4.2, "conf": 1.0},     # non una parola chiave
            ]})

        def FinalResult(self):
            return json.dumps({"result": [
                {"word": "calcio", "start": 9.0, "end": 9.4, "conf": 0.8}]})

    fake = types.ModuleType("vosk")
    fake.Model = lambda path: object()
    fake.KaldiRecognizer = FakeRec
    fake.SetLogLevel = lambda level: None
    monkeypatch.setitem(sys.modules, "vosk", fake)


def test_find_markers_filters_by_word_and_confidence(monkeypatch, tmp_path):
    seen = {}
    _install_fake_vosk(monkeypatch, seen)
    from rugby_highlights.speech import find_markers

    raw = tmp_path / "a.raw"
    raw.write_bytes(b"\x00\x00" * 16000 * 3)   # 3 s di silenzio
    progress = []
    markers = find_markers(str(raw), "modello-finto", Settings(use_grammar=True), progress.append)
    assert [(m.kind, m.time) for m in markers] == [("meta", 1.5), ("calcio", 3.0), ("calcio", 9.0)]
    grammar = json.loads(seen["grammar"])
    assert "meta" in grammar and "calcio" in grammar and "[unk]" in grammar
    assert progress and progress[-1] == 1.0


def test_full_vocabulary_option_and_log(monkeypatch, tmp_path):
    seen = {}
    _install_fake_vosk(monkeypatch, seen)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    from rugby_highlights.speech import find_markers, log_path, write_log

    raw = tmp_path / "a.raw"
    raw.write_bytes(b"\x00\x00" * 16000 * 3)
    s = Settings(use_grammar=False)
    markers = find_markers(str(raw), "modello-finto", s)
    assert seen["grammar"] is None
    write_log(markers, markers[:2], s)
    log = open(log_path(), encoding="utf-8").read()
    assert "scartata" in log and "tenuta" in log          # il log mostra anche le parole scartate


def test_voice_filter_keeps_loud_short_words_and_drops_noise():
    import numpy as np
    from rugby_highlights.models import Marker
    from rugby_highlights.voice_filter import filter_markers
    rms = np.full(2000, -40.0)            # 200 s di rumore di fondo
    rms[500:505] = -20.0                   # la tua voce a 50 s: +20 dB
    ms = [Marker(50.0, "meta", "meta", 0.9, 0.5),      # voce vera
          Marker(100.0, "meta", "meta", 0.9, 0.5),     # nessun picco: rumore
          Marker(50.0, "meta", "meta", 0.9, 3.0)]      # troppo lunga
    kept, dropped = filter_markers(ms, rms, Settings())
    assert [m.time for m in kept] == [50.0] and len(dropped) == 2
    assert kept[0].conf > 0.8
