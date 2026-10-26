"""Analisi completa di una partita: audio -> parole -> fischi -> clip."""

import os
import shutil
import tempfile

from .audio_analysis import analyze_audio
from .ffmpeg_utils import extract_audio_media, has_audio
from .media import Media
from .models import AnalysisResult
from .paths import find_vosk_model
from .voice_filter import filter_markers
from .planner import plan_clips, compare_expected, relabel, suggest_from_audio


def as_media(video) -> Media:
    """Accetta un percorso, un elenco di percorsi (partita a piu' file) o una Media."""
    if isinstance(video, Media):
        return video
    if isinstance(video, (str, os.PathLike)):
        return Media.from_paths([video])
    return Media.from_paths(list(video))


def analyze(video, settings, expected, progress=None, markers_provider=None,
            model_dir=None) -> AnalysisResult:
    """video: un file, un elenco di file (in ordine) o una Media.

    progress(frazione, testo). Puo' sollevare Cancelled per interrompere.

    markers_provider(raw_path) -> list[Marker] sostituisce il riconoscimento
    vocale (usato nei test).
    """
    def report(a, b, text):
        if not progress:
            return None
        return lambda f: progress(a + (b - a) * f, text)

    if progress:
        progress(0.0, "Leggo il video…")
    media = as_media(video)
    duration = media.total
    if not any(has_audio(p) for p in media.paths):
        raise RuntimeError("Il video non ha una traccia audio.")

    messages = []
    tmp = tempfile.mkdtemp(prefix="rugbyhl_")
    try:
        raw = os.path.join(tmp, "audio.raw")
        extract_audio_media(media, raw, report(0.02, 0.20, "Estraggo l'audio…"))
        feats = analyze_audio(raw, report(0.20, 0.40, "Cerco fischi e rumore del pubblico…"))

        markers = []
        if markers_provider is not None:
            markers = markers_provider(raw)
        else:
            model = model_dir or find_vosk_model()
            if not model:
                messages.append(
                    "Modello vocale non trovato: non ho potuto riconoscere le parole "
                    "'meta' e 'calcio'. Uso solo l'audio del pubblico.")
            else:
                try:
                    from .speech import find_markers
                    markers = find_markers(raw, model, settings,
                                           report(0.40, 0.97, "Ascolto le parole 'meta' e 'calcio'…"))
                except ImportError:
                    messages.append("Riconoscimento vocale non disponibile (libreria mancante).")
        if markers and markers_provider is None:
            heard = list(markers)
            markers, _dropped = filter_markers(markers, feats.rms_db, settings)
            try:
                from .speech import log_path, write_log
                write_log(heard, markers, settings)
                if len(markers) != len(heard):
                    messages.append(
                        f"Ho sentito {len(heard)} parole chiave e ne ho tenute {len(markers)} "
                        "(le altre erano troppo brevi, troppo lunghe o più deboli del rumore). "
                        f"Elenco completo: {log_path()}")
            except OSError:
                pass
        if progress:
            progress(0.98, "Preparo le clip…")

        heard = sum(1 for m in markers if m.kind in ("meta", "calcio"))
        if heard > 30 and (not expected.any or heard > 3 * (expected.meta + expected.calcio)):
            messages.append(
                f"Ho sentito {heard} parole «meta» o «calcio»: sono troppe, in gran parte "
                "sarà rumore. Controlla il tabellino e alza la «sicurezza minima delle parole» "
                "nelle impostazioni avanzate.")
        clips = plan_clips(markers, feats.whistles, duration, settings)
        if not markers and markers_provider is None and not messages:
            messages.append("Non ho sentito nessuna parola 'meta' o 'calcio'.")
        exp_msgs, missing = compare_expected(clips, expected)
        messages += exp_msgs
        if missing > 0:
            extra = suggest_from_audio(feats.peaks, clips, missing, duration, settings)
            if extra:
                messages.append(
                    f"Ho aggiunto {len(extra)} clip 'da verificare' dai picchi del pubblico: "
                    "guardale e tieni solo quelle giuste.")
                clips = relabel(clips + extra)
        if progress:
            progress(1.0, "Fatto")
        per_sec = len(feats.rms_db) // 10
        energy = (feats.rms_db[:per_sec * 10].reshape(per_sec, 10).max(axis=1).tolist()
                  if per_sec else [])
        return AnalysisResult(duration, clips, markers, feats.whistles, feats.peaks,
                              messages, energy)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
