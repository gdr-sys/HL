"""Una partita puo' essere fatta da piu' file (es. file da 17 minuti): qui diventano
un'unica linea del tempo continua."""

import os
import re
from dataclasses import dataclass

from .ffmpeg_utils import probe_duration

VIDEO_EXT = (".mp4", ".mov", ".mkv", ".avi", ".mts", ".m2ts", ".mpg", ".mpeg", ".wmv", ".m4v")


def natural_key(path):
    """Ordine 'umano' dei nomi: clip2 prima di clip10."""
    name = os.path.basename(str(path)).lower()
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


@dataclass
class Source:
    path: str
    duration: float
    offset: float      # dove inizia questo file sulla linea del tempo della partita


class Media:
    def __init__(self, sources):
        self.sources = list(sources)

    @classmethod
    def from_paths(cls, paths, durations=None):
        durations = durations or {}
        sources, offset = [], 0.0
        for p in paths:
            p = str(p)
            d = durations.get(p)
            if d is None:
                d = probe_duration(p)
            sources.append(Source(p, d, offset))
            offset += d
        return cls(sources)

    @property
    def total(self):
        return sum(s.duration for s in self.sources)

    @property
    def paths(self):
        return [s.path for s in self.sources]

    def locate(self, t):
        """Tempo della partita -> (indice del file, secondi dentro quel file)."""
        t = max(0.0, min(float(t), self.total))
        for i, s in enumerate(self.sources):
            if t < s.offset + s.duration or i == len(self.sources) - 1:
                return i, max(0.0, min(t - s.offset, s.duration))
        return 0, 0.0

    def split_range(self, start, end):
        """Intervallo della partita -> pezzi (percorso, inizio, fine) uno per file toccato."""
        pieces = []
        for s in self.sources:
            a, b = max(start, s.offset), min(end, s.offset + s.duration)
            if b - a > 0.05:
                pieces.append((s.path, a - s.offset, b - s.offset))
        return pieces
