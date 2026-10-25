import os

import pytest

from rugby_highlights.models import Clip
from rugby_highlights.narration import Names, ReportError, build_script, parse_report

TEXT = open(os.path.join(os.path.dirname(__file__), "comunicato.txt"), encoding="utf-8").read()


def test_parse_events_and_final_score():
    r = parse_report(TEXT)
    assert r.final == (33, 26)               # l'intro cita 33-26 ma non rompe la sequenza
    assert len(r.events) == 9 and r.count("meta") == 9 and r.count("calcio") == 0
    assert [e.side for e in r.events] == ["home", "home", "away", "away", "home",
                                          "away", "home", "away", "home"]
    assert r.events[0].when == "Al 27°" and r.events[2].when.startswith("Allo scadere")
    assert r.events[-1].when == "Sul fischio finale"
    assert r.events[3].when == "Nella ripresa"
    assert r.count("meta", "home") == 5 and r.count("meta", "away") == 4


def test_penalty_and_clean_fragments():
    r = parse_report("Parte forte la squadra di casa (3-0). Poi gli ospiti pareggiano (3-3) "
                     "e chiudono con una meta (3-10).")
    assert [(e.side, e.kind, e.points) for e in r.events] == [
        ("home", "calcio", 3), ("away", "calcio", 3), ("away", "meta", 7)]
    assert r.events[1].fragment == "Gli ospiti pareggiano (3-3)"


def test_errors():
    with pytest.raises(ReportError):
        parse_report("")
    with pytest.raises(ReportError):
        parse_report("Una bella partita senza numeri.")


def test_script_aligns_clips_and_flags_gaps():
    r = parse_report(TEXT)
    clips = [Clip(i * 100, i * 100 + 20, "meta") for i in range(8)]   # ne manca una
    s = build_script(r, clips, Names("Capitolina", "Fiorini Pesaro"))
    assert "RIASSUNTO DELLA PARTITA" in s and "Risultato finale: Capitolina 33, Fiorini Pesaro 26" in s
    assert "CLIP 8" in s and "CLIP 9" not in s
    assert "non hanno una clip" in s
    assert "Da leggere: Al 27°, prima meta per Capitolina." in s


def test_script_without_report_is_generic():
    s = build_script(None, [Clip(0, 20, "meta"), Clip(30, 50, "calcio")])
    assert "Da leggere: Meta." in s and "Da leggere: Calcio a punti." in s


def test_timecodes_since_inizio_and_files():
    from rugby_highlights import timecodes
    from rugby_highlights.media import Media, Source
    from rugby_highlights.models import AnalysisResult, Marker, Settings
    media = Media([Source("a.mp4", 100.0, 0.0), Source("b.mp4", 100.0, 100.0)])
    res = AnalysisResult(200.0, clips=[Clip(40, 60, "meta"), Clip(120, 140, "calcio", enabled=False)],
                         markers=[Marker(20.0, "inizio"), Marker(58.0, "meta"),
                                  Marker(130.0, "calcio"), Marker(150.0, "meta")])
    txt = timecodes.build_text(res, media, Settings(), res.clips)
    assert "0:00:58.0   META 1" in txt and "dall'inizio 0:38.0" in txt
    assert "azione 0:00:40 → 0:01:00" in txt
    assert "(clip scartata)" in txt and "(nessuna clip)" in txt
    assert "[b.mp4 a 0:00:30.0]" in txt
    csv = timecodes.build_csv(res, media, Settings(), res.clips)
    assert csv.splitlines()[0].startswith("Tipo;") and "scartata" in csv


def test_shorthand_scoreboard_log():
    t = ("13’ cp tarv (0-3), 29’ cp Azzolini (3-3), 33’ cp Azzolini (6-3), 38’ m tatrv 6-8, "
         "40’ cp Azzolini (9-8). S.t. 17’ cp Giabardo (9-11), 25’ m tarv tr (9-18), "
         "30‘ m pesaro tr Azzolini (16-18),")
    r = parse_report(t)
    assert r.final == (16, 18) and r.count("meta") == 3 and r.count("calcio") == 5
    assert r.events[1].scorer == "Azzolini" and r.events[1].detail == "punizione"
    assert r.events[5].when == "Al 17° del secondo tempo" and r.events[7].when == "Al 30° del secondo tempo"
    assert r.events[7].detail == "trasformata" and r.events[7].side == "home"
    s = build_script(r, [Clip(0, 20, "calcio")], Names("Pesaro", "Tarvisio"))
    assert "primo calcio di punizione per Tarvisio" in s


def test_separate_conversion_is_part_of_the_try():
    r = parse_report("Meta al 10° (5-0), trasformazione (7-0). Poi un calcio di punizione (7-3).")
    assert [(e.kind, e.points) for e in r.events] == [("meta", 7), ("calcio", 3)]
    assert r.events[0].score == (7, 0) and r.count("calcio") == 1


def test_inizio_snaps_to_whistle():
    from rugby_highlights import timecodes
    from rugby_highlights.models import AnalysisResult, Marker, Settings, Whistle
    res = AnalysisResult(200.0, markers=[Marker(30.0, "inizio"), Marker(100.0, "inizio"),
                                         Marker(110.0, "meta")],
                         whistles=[Whistle(26.0, 27.0), Whistle(60.0, 61.0)])
    rows = timecodes.build_rows(res, None, Settings(), [])
    assert rows[0]["t"] == 26.0 and rows[0]["snapped"]          # aggancia il fischio
    assert rows[1]["t"] == 100.0 and not rows[1]["snapped"]     # nessun fischio vicino
    assert abs(rows[2]["since"] - 10.0) < 1e-6
