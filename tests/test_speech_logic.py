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
    assert [(m.kind, m.time) for m in markers] == [("meta", 1.5), ("calcio", 9.0)]
    grammar = json.loads(seen["grammar"])
    assert "meta" in grammar and "calcio" in grammar and "[unk]" in grammar
    assert progress and progress[-1] == 1.0


def test_default_uses_full_vocabulary_and_writes_log(monkeypatch, tmp_path):
    seen = {}
    _install_fake_vosk(monkeypatch, seen)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    from rugby_highlights.speech import find_markers, log_path

    raw = tmp_path / "a.raw"
    raw.write_bytes(b"\x00\x00" * 16000 * 3)
    markers = find_markers(str(raw), "modello-finto", Settings())
    assert seen["grammar"] is None                       # nessuna grammatica: meno falsi positivi
    assert len(markers) == 2
    log = open(log_path(), encoding="utf-8").read()
    assert "scartata" in log and "tenuta" in log          # il log mostra anche le parole scartate
