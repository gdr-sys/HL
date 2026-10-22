"""Analisi dell'audio ambiente: fischi dell'arbitro e picchi di rumore del pubblico.

Solo numpy. I valori soglia sono un punto di partenza: vanno tarati sulle
registrazioni reali (posizione del microfono, rumore di fondo del campo).
"""

from dataclasses import dataclass, field

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .models import Whistle

SR = 16000
FRAME = 2048
HOP = 1600            # 0.1 s
HOP_S = HOP / SR
WHISTLE_BAND = (1800.0, 4800.0)
LOCAL = 41            # bin (~640 Hz) per la mediana locale dello spettro


@dataclass
class AudioFeatures:
    times: np.ndarray
    rms_db: np.ndarray
    whistles: list = field(default_factory=list)
    peaks: list = field(default_factory=list)   # [(tempo, punteggio dB)]
    duration: float = 0.0


def _moving_avg(a, w):
    w = max(1, int(w))
    if w == 1:
        return a.copy()
    pad = np.pad(a, (w // 2, w - 1 - w // 2), mode="edge")
    return np.convolve(pad, np.ones(w) / w, mode="valid")


def detect_whistles(prom_db, peak_db, times, prom_thr=20.0, margin_db=12.0,
                    min_len=0.3, max_gap=0.2):
    floor = float(np.percentile(peak_db, 50))
    flag = (prom_db > prom_thr) & (peak_db > floor + margin_db)
    idx = np.flatnonzero(flag)
    if idx.size == 0:
        return []
    gap_frames = int(round(max_gap / HOP_S))
    runs, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - prev > gap_frames + 1:
            runs.append((start, prev))
            start = i
        prev = i
    runs.append((start, prev))
    out = []
    for a, b in runs:
        if (b - a + 1) * HOP_S >= min_len:
            out.append(Whistle(float(times[a]) - 0.05, float(times[b]) + 0.05,
                               float(np.mean(prom_db[a:b + 1]))))
    return out


def detect_peaks(rms_db, times, thr_db=5.0, min_dist=20.0, max_peaks=300):
    """Momenti in cui il rumore sale nettamente rispetto al livello dell'ultimo minuto."""
    smooth = _moving_avg(rms_db, 15)       # ~1.5 s
    base = _moving_avg(rms_db, 600)        # ~60 s
    surge = smooth - base
    picked = []
    for i in np.argsort(-surge):
        if surge[i] < thr_db or len(picked) >= max_peaks:
            break
        t = float(times[i])
        if all(abs(t - p[0]) >= min_dist for p in picked):
            picked.append((t, float(surge[i])))
    return sorted(picked)


def analyze_audio(raw_path, progress=None) -> AudioFeatures:
    x = np.memmap(raw_path, dtype=np.int16, mode="r")
    n = (len(x) - FRAME) // HOP + 1
    if n < 20:
        raise ValueError("Audio troppo corto o assente.")
    freqs = np.fft.rfftfreq(FRAME, 1.0 / SR)
    band = np.flatnonzero((freqs >= WHISTLE_BAND[0]) & (freqs <= WHISTLE_BAND[1]))
    win = np.hanning(FRAME).astype(np.float32)
    ar = np.arange(FRAME)
    rms_db = np.empty(n, np.float32)
    prom_db = np.empty(n, np.float32)
    peak_db = np.empty(n, np.float32)
    block = 400
    for s in range(0, n, block):
        e = min(n, s + block)
        idx = np.arange(s, e)[:, None] * HOP + ar[None, :]
        seg = x[idx].astype(np.float32) / 32768.0
        rms_db[s:e] = 20 * np.log10(np.sqrt(np.mean(seg ** 2, axis=1)) + 1e-9)
        spec = np.abs(np.fft.rfft(seg * win, axis=1))[:, band]
        # Una nota pura spicca rispetto alle frequenze vicine (mediana locale):
        # il rumore del pubblico, anche se inclinato, no.
        padded = np.pad(spec, ((0, 0), (LOCAL // 2, LOCAL // 2)), mode="edge")
        local = np.median(sliding_window_view(padded, LOCAL, axis=1), axis=2) + 1e-9
        prom_db[s:e] = 20 * np.log10((spec / local).max(axis=1) + 1e-9)
        peak_db[s:e] = 20 * np.log10(spec.max(axis=1) + 1e-9)
        if progress:
            progress(e / n)
    times = (np.arange(n) * HOP + FRAME / 2) / SR
    return AudioFeatures(
        times=times,
        rms_db=rms_db,
        whistles=detect_whistles(prom_db, peak_db, times),
        peaks=detect_peaks(rms_db, times),
        duration=len(x) / SR,
    )
