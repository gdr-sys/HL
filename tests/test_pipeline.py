import os
import subprocess

from rugby_highlights.audio_analysis import analyze_audio
from rugby_highlights.ffmpeg_utils import (export_montage, extract_audio_raw,
                                           extract_frame, probe_duration)
from rugby_highlights.models import Expected, Marker, Settings
from rugby_highlights.pipeline import analyze
from rugby_highlights.planner import fit_to_target, plan_clips


def _duration(path):
    return probe_duration(path)


def test_whistles_and_peaks(synthetic_video, tmp_path):
    raw = tmp_path / "a.raw"
    extract_audio_raw(synthetic_video, raw, _duration(synthetic_video))
    f = analyze_audio(raw)
    starts = sorted(w.start for w in f.whistles)
    assert len(starts) == 3, starts
    for got, want in zip(starts, (18.0, 42.0, 90.0)):
        assert abs(got - want) < 0.6
    peak_times = [t for t, _ in f.peaks]
    assert any(40 <= t <= 50 for t in peak_times), f.peaks
    assert any(90 <= t <= 100 for t in peak_times), f.peaks


def test_plan_uses_previous_whistle(synthetic_video, tmp_path):
    raw = tmp_path / "a.raw"
    extract_audio_raw(synthetic_video, raw, _duration(synthetic_video))
    f = analyze_audio(raw)
    s = Settings()
    clips = plan_clips([Marker(41.0, "meta"), Marker(95.0, "calcio")], f.whistles, 120.0, s)
    assert [c.label for c in clips] == ["Meta 1", "Calcio 1"]
    assert abs(clips[0].start - (18.0 - s.whistle_margin)) < 0.7   # parte dal fischio delle 18
    assert abs(clips[0].end - (41.0 + s.meta_post)) < 0.01
    assert abs(clips[1].start - (95.0 - s.calcio_pre)) < 0.01


def test_expected_check_and_audio_suggestion(synthetic_video):
    markers = [Marker(41.0, "meta", "meta", 0.9)]
    res = analyze(synthetic_video, Settings(), Expected(meta=1, calcio=1),
                  markers_provider=lambda raw: markers)
    assert any("Calci a punti: trovate 0 su 1" in m for m in res.messages), res.messages
    kinds = [c.kind for c in res.clips]
    assert kinds.count("meta") == 1 and kinds.count("dubbio") == 1
    dub = [c for c in res.clips if c.kind == "dubbio"][0]
    assert 70 <= dub.end <= 110          # il picco del secondo ovazione, ~95 s


def test_too_many_markers_disables_weakest(synthetic_video):
    markers = [Marker(41.0, "meta", "meta", 0.9), Marker(105.0, "meta", "meta", 0.65)]
    res = analyze(synthetic_video, Settings(), Expected(meta=1),
                  markers_provider=lambda raw: markers)
    on = [c for c in res.clips if c.enabled]
    off = [c for c in res.clips if not c.enabled]
    assert len(on) == 1 and len(off) == 1 and off[0].conf == 0.65


def test_too_many_markers_close_together_are_merged_and_flagged(synthetic_video):
    markers = [Marker(41.0, "meta", "meta", 0.9), Marker(70.0, "meta", "meta", 0.65)]
    res = analyze(synthetic_video, Settings(), Expected(meta=1),
                  markers_provider=lambda raw: markers)
    assert len(res.clips) == 1 and res.clips[0].label == "Meta 1 + Meta 2"
    assert any("clip unite" in m for m in res.messages), res.messages


def test_export_montage_and_frame(synthetic_video, tmp_path):
    out = tmp_path / "hl.mp4"
    export_montage(synthetic_video, [(16.5, 53.0), (81.0, 102.0)], out)
    assert abs(_duration(out) - (36.5 + 21.0)) < 1.0
    assert extract_frame(synthetic_video, 30.0, tmp_path / "f.png")
    assert os.path.getsize(tmp_path / "f.png") > 1000
    # la risoluzione dell'originale resta invariata
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
                       capture_output=True, text=True)
    assert r.stdout.strip() == "640,360"


def test_export_with_music_shorter_than_video(synthetic_video, tmp_path):
    song = tmp_path / "song.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=5", str(song)], check=True)   # 5 s: va ripetuta
    out = tmp_path / "hl_music.mp4"
    export_montage(synthetic_video, [(16.5, 36.5), (81.0, 91.0)], out,
                   music=song, music_volume=0.5, original_volume=0.3)
    assert abs(_duration(out) - 30.0) < 1.0
    # niente musica: nessun errore e stessa durata (audio originale solo)
    out2 = tmp_path / "hl_nomusic.mp4"
    export_montage(synthetic_video, [(16.5, 36.5), (81.0, 91.0)], out2)
    assert abs(_duration(out2) - 30.0) < 1.0


def test_fit_to_target():
    from rugby_highlights.models import Clip
    clips = [Clip(0, 60, "meta"), Clip(100, 160, "meta"), Clip(200, 260, "meta")]
    assert fit_to_target(clips, 120, 8)
    total = sum(c.duration for c in clips)
    assert abs(total - 120) < 0.01
    assert all(c.end in (60, 160, 260) for c in clips)   # i festeggiamenti restano
