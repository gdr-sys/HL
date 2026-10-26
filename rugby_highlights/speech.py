"""Riconoscimento vocale offline (Vosk) delle parole "meta" e "calcio"."""

import json
import os
import tempfile

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
            if kind:
                dur = float(w.get("end", w["start"])) - float(w["start"])
                markers.append(Marker(float(w["start"]), kind, w["word"], conf, dur))

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


def log_path():
    return os.path.join(tempfile.gettempdir(), "rugby_highlights_voce.txt")


def write_log(markers, kept, settings, note=""):
    """Tutte le parole chiave sentite (anche quelle scartate), per capire cosa e' successo."""
    try:
        kept_ids = {id(m) for m in kept}
        with open(log_path(), "w", encoding="utf-8") as f:
            f.write(f"Parole chiave sentite: {len(markers)}, tenute: {len(kept)}  "
                    f"({'solo parole chiave' if settings.use_grammar else 'vocabolario completo'}). "
                    f"{note}\n")
            f.write("tempo\tparola\tsicurezza\tdurata\tvolume sopra il rumore (dB)\tesito\n")
            for m in sorted(markers, key=lambda m: m.time):
                t = m.time
                f.write(f"{int(t // 3600)}:{int(t // 60 % 60):02d}:{t % 60:04.1f}\t{m.word}\t"
                        f"{m.conf:.2f}\t{m.dur:.2f}\t{m.prom:.1f}\t"
                        f"{'tenuta' if id(m) in kept_ids else 'scartata'}\n")
    except OSError:
        pass
