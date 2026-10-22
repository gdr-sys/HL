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
