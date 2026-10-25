"""Marcatori per Adobe Premiere: file XML (formato Final Cut 7) e CSV del pannello Marcatori.

L'XML contiene una sequenza con i file della partita uno dopo l'altro e, sopra, i marcatori
«Meta 1», «Calcio 2», «Inizio 2° tempo»… Si importa con File > Importa. Il CSV e' un elenco
a tabulazioni che alcune versioni importano direttamente nel pannello Marcatori.
"""

import json
import os
import re
import subprocess
from urllib.parse import quote
from xml.sax.saxutils import escape

from .ffmpeg_utils import _NOWIN
from .paths import find_binary
from . import timecodes


def probe_video(path):
    """(fps reali, larghezza, altezza) del primo flusso video; valori di riserva se non si legge."""
    try:
        r = subprocess.run(
            [find_binary("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=avg_frame_rate,r_frame_rate,width,height", "-of", "json", str(path)],
            stdin=subprocess.DEVNULL, capture_output=True, creationflags=_NOWIN)
        s = json.loads(r.stdout)["streams"][0]
        num, den = (s.get("avg_frame_rate") or s["r_frame_rate"]).split("/")
        fps = float(num) / float(den)
        if not 5 < fps < 240:
            raise ValueError
        return fps, int(s.get("width") or 1920), int(s.get("height") or 1080)
    except Exception:  # noqa: BLE001
        return 25.0, 1920, 1080


def timebase(fps):
    """Frame rate come lo scrive Premiere: (base intera, ntsc)."""
    for real, base in ((23.976, 24), (29.97, 30), (47.952, 48), (59.94, 60)):
        if abs(fps - real) < 0.02:
            return base, True
    return int(round(fps)), False


def pathurl(path):
    p = str(path).replace("\\", "/")
    if not re.match(r"^[A-Za-z]:/", p):
        p = os.path.abspath(p).replace("\\", "/")
    m = re.match(r"^([A-Za-z]):(/.*)$", p)
    if m:
        return "file://localhost/" + m.group(1) + "%3a" + quote(m.group(2), safe="/")
    return "file://localhost" + quote(p, safe="/")


def _tc(t, base):
    f = int(round(t * base))
    s, ff = divmod(f, base)
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{ff:02d}"


def marker_list(rows):
    """[(tempo, nome, commento)] dalle righe dei minutaggi: parola detta + inizio dell'azione."""
    out, n = [], {"meta": 0, "calcio": 0}
    for r in rows:
        if r["kind"] == "inizio":
            name = "Inizio " + (f"{r['period']}° tempo" if r["period"] else "partita")
            out.append((r["t"], name, "fischio d'inizio" if r["snapped"] else "detto a voce"))
            continue
        n[r["kind"]] += 1
        name = f"{r['kind'].capitalize()} {n[r['kind']]}"
        note = f"dall'inizio {timecodes.ms(r['since'])}"
        if r["dropped"]:
            note += " - clip scartata"
        out.append((r["t"], name, note))
        if r["clip"]:
            out.append((r["clip"][0], f"Azione {name}", "inizio dell'azione negli highlights"))
    return sorted(out, key=lambda x: x[0])


def build_xml(rows, media, title="Partita", seq_fps=25.0):
    """seq_fps: frame rate della sequenza di Premiere. Si puo' girare a 50p e montare a 25:
    i tempi in secondi restano gli stessi, cambia solo il conteggio dei fotogrammi."""
    cam_fps, w, h = probe_video(media.paths[0])
    cam_base, cam_ntsc = timebase(cam_fps)
    cam_real = cam_fps if cam_ntsc else float(cam_base)
    cam_rate = (f"<rate><timebase>{cam_base}</timebase><ntsc>{'TRUE' if cam_ntsc else 'FALSE'}</ntsc></rate>")
    base, ntsc = timebase(seq_fps)
    real = seq_fps if ntsc else float(base)
    total = int(round(media.total * real))
    flag = "TRUE" if ntsc else "FALSE"
    rate = f"<rate><timebase>{base}</timebase><ntsc>{flag}</ntsc></rate>"

    clipvideo, clipaudio = [], []
    for i, s in enumerate(media.sources, start=1):
        d = int(round(s.duration * cam_real))           # in fotogrammi della camera
        a = int(round(s.offset * real))                 # posizione sulla sequenza
        b = int(round((s.offset + s.duration) * real))
        name = escape(os.path.basename(s.path))
        file_xml = (f'<file id="file-{i}"><name>{name}</name><pathurl>{escape(pathurl(s.path))}</pathurl>'
                    f"{cam_rate}<duration>{d}</duration><media><video><samplecharacteristics>{cam_rate}"
                    f"<width>{w}</width><height>{h}</height></samplecharacteristics></video>"
                    f"<audio><channelcount>2</channelcount></audio></media></file>")
        clipvideo.append(
            f'<clipitem id="clipitem-v{i}"><name>{name}</name><duration>{d}</duration>{cam_rate}'
            f"<start>{a}</start><end>{b}</end><in>0</in><out>{d}</out>{file_xml}</clipitem>")
        clipaudio.append(
            f'<clipitem id="clipitem-a{i}"><name>{name}</name><duration>{d}</duration>{cam_rate}'
            f'<start>{a}</start><end>{b}</end><in>0</in><out>{d}</out><file id="file-{i}"/>'
            f"<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack></clipitem>")

    markers = "".join(
        f"<marker><name>{escape(name)}</name><comment>{escape(note)}</comment>"
        f"<in>{int(round(t * real))}</in><out>-1</out></marker>"
        for t, name, note in marker_list(rows))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">'
        f'<sequence id="sequence-1"><name>{escape(title)}</name><duration>{total}</duration>{rate}'
        f"<media><video><format><samplecharacteristics>{rate}<width>{w}</width><height>{h}</height>"
        f"</samplecharacteristics></format><track>{''.join(clipvideo)}</track></video>"
        f"<audio><track>{''.join(clipaudio)}</track></audio></media>"
        f"<timecode>{rate}<string>00:00:00:00</string><frame>0</frame></timecode>"
        f"{markers}</sequence></xmeml>\n"), (base, real)


def build_markers_csv(rows, base):
    lines = ["Marker Name\tDescription\tIn\tOut\tDuration\tMarker Type"]
    for t, name, note in marker_list(rows):
        tc = _tc(t, base)
        lines.append(f"{name}\t{note}\t{tc}\t{tc}\t00:00:00:00\tComment")
    return "\n".join(lines) + "\n"


def save(path_base, result, media, settings, clips=None, title="Partita", seq_fps=25.0):
    """Scrive base.xml e base_marcatori.csv. Ritorna (xml, csv)."""
    rows = timecodes.build_rows(result, media, settings, clips)
    xml, (base, _real) = build_xml(rows, media, title, seq_fps)
    xml_path, csv_path = path_base + ".xml", path_base + "_marcatori.csv"
    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(xml)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(build_markers_csv(rows, base))
    return xml_path, csv_path
