"""Riconoscimento vocale offline (Vosk) delle parole "meta" e "calcio"."""

import json
import os

from .models import KEYWORDS, Marker

SR = 16000


def speech_available() -> bool:
    try:
        import vosk  # noqa: F401
        return True
    except Exception:
        return False


def find_markers(raw_path, model_dir, settings, progress=None):
    from vosk import KaldiRecognizer, Model, SetLogLevel

    SetLogLevel(-1)
    word_kind = {w: kind for kind, words in KEYWORDS.items() for w in words}
    model = Model(model_dir)
    if settings.use_grammar:
        rec = KaldiRecognizer(model, SR, json.dumps(sorted(word_kind) + ["[unk]"]))
    else:
        rec = KaldiRecognizer(model, SR)
    rec.SetWords(True)

    markers = []

    def collect(result_json):
        for w in json.loads(result_json).get("result", []):
            kind = word_kind.get(w.get("word"))
            conf = float(w.get("conf", 1.0))
            if kind and conf >= settings.voice_min_conf:
                markers.append(Marker(float(w["start"]), kind, w["word"], conf))

    total = max(1, os.path.getsize(raw_path))
    done = 0
    with open(raw_path, "rb") as f:
        while True:
            chunk = f.read(SR)  # 0.5 s di audio
            if not chunk:
                break
            done += len(chunk)
            if rec.AcceptWaveform(chunk):
                collect(rec.Result())
            if progress:
                progress(min(1.0, done / total))
    collect(rec.FinalResult())
    return markers
