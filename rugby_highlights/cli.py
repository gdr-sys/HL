"""Uso da riga di comando (utile per prove): python -m rugby_highlights video.mp4 ..."""

import argparse
import sys

from .ffmpeg_utils import export_montage
from .media import Media, natural_key
from .models import Expected, Settings
from .pipeline import analyze
from .planner import fit_to_target


def fmt(t):
    t = int(round(t))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rugby_highlights")
    ap.add_argument("video", nargs="+", help="uno o piu' file della partita, in ordine")
    ap.add_argument("--meta", type=int, default=0, help="mete totali da tabellino")
    ap.add_argument("--calci", type=int, default=0, help="calci a punti totali")
    ap.add_argument("--out", help="file di uscita; se manca mostra solo le clip trovate")
    ap.add_argument("--target", type=float, default=180.0, help="durata massima in secondi")
    ap.add_argument("--no-fit", action="store_true", help="non accorciare per stare nel target")
    a = ap.parse_args(argv)

    s = Settings(target_seconds=a.target)

    def prog(f, text):
        print(f"\r{text:<60} {f * 100:5.1f}%", end="", file=sys.stderr, flush=True)

    media = Media.from_paths(sorted(a.video, key=natural_key) if len(a.video) > 1 else a.video)
    res = analyze(media, s, Expected(a.meta, a.calci), prog)
    print(file=sys.stderr)
    for m in res.messages:
        print(m)
    for c in res.clips:
        flag = " " if c.enabled else "x"
        print(f"[{flag}] {c.label:<18} {fmt(c.start)} - {fmt(c.end)}  ({c.duration:.0f}s)  {c.note}")
    if a.out:
        if not a.no_fit and fit_to_target(res.clips, s.target_seconds, s.min_clip_seconds):
            print(f"Clip accorciate per stare in {s.target_seconds:.0f}s")
        ranges = [(c.start, c.end) for c in res.clips if c.enabled]
        export_montage(media, ranges, a.out, fade=s.fade, crf=s.crf,
                       progress=lambda f: print(f"\rMontaggio {f * 100:5.1f}%", end="",
                                                file=sys.stderr, flush=True))
        print(f"\nCreato {a.out}")


if __name__ == "__main__":
    main()
