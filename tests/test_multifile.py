import subprocess

import numpy as np

from rugby_highlights.ffmpeg_utils import export_montage, probe_duration
from rugby_highlights.media import Media, natural_key
from rugby_highlights.models import Expected, Marker, Settings
from rugby_highlights.pipeline import analyze


def frame_rgb(path, t, w=640, h=360):
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", str(path),
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(h, w, 3).astype(float)


def test_natural_order():
    names = ["C:/x/clip10.mp4", "C:/x/clip2.mp4", "C:/x/clip1.mp4"]
    assert [n.split("/")[-1] for n in sorted(names, key=natural_key)] == \
        ["clip1.mp4", "clip2.mp4", "clip10.mp4"]


def test_media_timeline(split_videos):
    m = Media.from_paths(split_videos)
    assert abs(m.total - 120) < 1.0
    i, local = m.locate(50)
    assert i == 1 and abs(local - (50 - m.sources[1].offset)) < 0.01
    pieces = m.split_range(35, 50)                 # a cavallo del primo confine
    assert [p[0] for p in pieces] == split_videos[:2]
    assert abs(sum(b - a for _, a, b in pieces) - 15) < 0.01
    assert len(m.split_range(5, 10)) == 1


def test_analysis_runs_over_all_files(split_videos):
    markers = [Marker(41.0, "meta", "meta", 0.9), Marker(95.0, "calcio", "calcio", 0.8)]
    res = analyze(split_videos, Settings(), Expected(1, 1), markers_provider=lambda raw: markers)
    assert abs(res.duration - 120) < 1.0
    starts = sorted(w.start for w in res.whistles)
    assert len(starts) == 3, starts
    for got, want in zip(starts, (18.0, 42.0, 90.0)):
        assert abs(got - want) < 1.0               # i fischi restano al posto giusto
    assert [c.label for c in res.clips] == ["Meta 1", "Calcio 1"]


def test_export_clip_across_files(split_videos, tmp_path):
    m = Media.from_paths(split_videos)
    out = tmp_path / "x.mp4"
    export_montage(m, [(30, 50), (80, 95)], out)   # entrambe attraversano un confine
    assert abs(probe_duration(out) - 35) < 1.0


def test_cuts_are_clean_no_fade_to_black(synthetic_video, tmp_path):
    out = tmp_path / "cuts.mp4"
    export_montage(synthetic_video, [(10, 20), (50, 60)], out)
    assert abs(probe_duration(out) - 20) < 0.6
    # primo fotogramma di ogni clip: pieno, non nero (nessuna dissolvenza)
    for t in (0.04, 10.04):
        assert frame_rgb(out, t).mean() > 40, t
    # a richiesta la dissolvenza esiste ancora
    faded = tmp_path / "faded.mp4"
    export_montage(synthetic_video, [(10, 20)], faded, fade=0.5)
    assert frame_rgb(faded, 0.04).mean() < frame_rgb(out, 0.04).mean() - 20


def test_clip_across_files_has_no_black_in_the_middle(split_videos, tmp_path):
    m = Media.from_paths(split_videos)
    out = tmp_path / "x.mp4"
    boundary = m.sources[1].offset                # 40 s: il punto in cui cambia il file
    export_montage(m, [(boundary - 5, boundary + 5)], out)
    assert abs(probe_duration(out) - 10) < 0.8
    for t in (4.0, 5.0, 5.5):
        assert frame_rgb(out, t).mean() > 40, t
