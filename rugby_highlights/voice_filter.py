"""Scelta delle parole «meta»/«calcio»/«inizio» davvero dette da te.

Il riconoscitore, con tanto rumore, "sente" parole che non ci sono. La tua voce vicino al
microfono, pero', ha tre caratteristiche: dura circa mezzo secondo, e' piu' forte del rumore
intorno, ed e' riconosciuta con una certa sicurezza. Qui si tengono le parole che le hanno,
e a ognuna si da un punteggio (usato poi per scartare le meno sicure se il tabellino ne
prevede meno).
"""

import numpy as np

from .audio_analysis import HOP_S

MIN_DUR, MAX_DUR = 0.15, 1.4


def prominence_db(rms_db, start, end, around=15.0):
    """Livello medio della parola meno la mediana del rumore nei `around` secondi intorno."""
    n = len(rms_db)
    a, b = int(start / HOP_S), max(int(start / HOP_S) + 1, int(end / HOP_S))
    if a >= n:
        return 0.0
    word = float(np.mean(rms_db[a:min(b, n)]))
    lo, hi = max(0, a - int(around / HOP_S)), min(n, b + int(around / HOP_S))
    ctx = np.concatenate([rms_db[lo:a], rms_db[min(b, n):hi]])
    return word - float(np.median(ctx)) if ctx.size else 0.0


def score(conf, prom):
    return 0.4 * min(1.0, max(0.0, conf)) + 0.6 * min(1.0, max(0.0, prom / 12.0))


def filter_markers(markers, rms_db, settings):
    """Ritorna (tenute, scartate). Aggiorna prom e conf (= punteggio) di ogni parola."""
    kept, dropped = [], []
    for m in markers:
        m.prom = prominence_db(rms_db, m.time, m.time + max(m.dur, 0.1))
        ok = (MIN_DUR <= m.dur <= MAX_DUR if m.dur > 0 else True) \
            and m.conf >= settings.voice_min_conf * 0.5 \
            and m.prom >= settings.voice_min_prominence
        m.conf = score(m.conf, m.prom)
        (kept if ok else dropped).append(m)
    return kept, dropped
