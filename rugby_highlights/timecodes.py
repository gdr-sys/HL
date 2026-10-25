"""Minutaggi precisi delle parole dette (meta, calcio, inizio) sulla registrazione intera.

Servono per montare la partita completa con le grafiche: si trova subito il punto.
I tempi sono quelli della registrazione; se la partita e' fatta da piu' file si indica anche
il file e il punto dentro al file. "Dall'inizio" parte dall'ultima volta che hai detto «inizio».
"""

import os

from .planner import dedupe_markers

LABELS = {"meta": "META", "calcio": "CALCIO", "inizio": "INIZIO"}


def hms(t, decimals=1):
    t = max(0.0, float(t))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    frac = f"{s:0{2 + (decimals + 1 if decimals else 0)}.{decimals}f}"
    return f"{int(h)}:{int(m):02d}:{frac}"


def ms(t):
    t = max(0.0, float(t))
    return f"{int(t // 60)}:{t % 60:04.1f}"


def build_rows(result, media, settings, clips=None):
    """Una riga per ogni parola riconosciuta, in ordine di tempo."""
    clips = result.clips if clips is None else clips
    marks = dedupe_markers(result.markers, settings.dedupe_seconds)
    rows, start_t, start_n = [], None, 0
    for m in marks:
        if m.kind == "inizio":
            start_n += 1
            start_t = m.time
        base = start_t if start_t is not None else 0.0
        row = {"t": m.time, "kind": m.kind, "conf": m.conf,
               "since": m.time - base, "period": start_n, "file": "", "local": None,
               "clip": None, "dropped": False}
        if media is not None and len(media.sources) > 1:
            idx, local = media.locate(m.time)
            row["file"], row["local"] = os.path.basename(media.sources[idx].path), local
        if m.kind != "inizio":
            hit = [c for c in clips if c.start - 0.5 <= m.time <= c.end + 0.5]
            on = [c for c in hit if c.enabled]
            if on:
                row["clip"] = (on[0].start, on[0].end)
            elif hit:
                row["dropped"] = True
        rows.append(row)
    return rows


def build_text(result, media, settings, clips=None, title="Minutaggi della partita"):
    rows = build_rows(result, media, settings, clips)
    out = [title.upper(), "=" * len(title),
           "Tempi sulla registrazione intera (ore:minuti:secondi). «Dall'inizio» parte dall'ultima",
           "volta che hai detto «inizio». «Azione» è il tratto che finisce negli highlights.", ""]
    if not any(r["kind"] == "inizio" for r in rows):
        out += ["Non ho sentito la parola «inizio»: i tempi «dall'inizio» partono dall'avvio della registrazione.", ""]
    multi = media is not None and len(media.sources) > 1
    n_meta = n_calcio = 0
    for r in rows:
        if r["kind"] == "meta":
            n_meta += 1
            tag = f"META {n_meta}"
        elif r["kind"] == "calcio":
            n_calcio += 1
            tag = f"CALCIO {n_calcio}"
        else:
            tag = f"INIZIO {r['period']}"
        line = f"{hms(r['t'])}   {tag:<10}"
        if r["kind"] != "inizio":
            when = f"dall'inizio {ms(r['since'])}"
            if r["period"]:
                when += f" (tempo {r['period']})"
            line += f"  {when}"
            if r["clip"]:
                line += f"   azione {hms(r['clip'][0], 0)} → {hms(r['clip'][1], 0)}"
            elif r["dropped"]:
                line += "   (clip scartata)"
            else:
                line += "   (nessuna clip)"
        if multi:
            line += f"   [{r['file']} a {hms(r['local'])}]"
        out.append(line)
    if not rows:
        out.append("Nessuna parola riconosciuta.")
    return "\n".join(out) + "\n"


def build_csv(result, media, settings, clips=None):
    """CSV con il punto e virgola (si apre direttamente in Excel in italiano)."""
    rows = build_rows(result, media, settings, clips)
    head = ["Tipo", "Tempo registrazione", "Secondi", "Dall'inizio", "Tempo di gioco",
            "Azione da", "Azione a", "File", "Punto nel file", "Clip"]
    lines = [";".join(head)]
    for r in rows:
        stato = "" if r["kind"] == "inizio" else ("tenuta" if r["clip"] else
                                                  "scartata" if r["dropped"] else "nessuna")
        lines.append(";".join([
            LABELS.get(r["kind"], r["kind"]), hms(r["t"]), f"{r['t']:.1f}".replace(".", ","),
            ms(r["since"]) if r["kind"] != "inizio" else "", str(r["period"] or ""),
            hms(r["clip"][0], 0) if r["clip"] else "", hms(r["clip"][1], 0) if r["clip"] else "",
            r["file"], hms(r["local"]) if r["local"] is not None else "", stato]))
    return "\n".join(lines) + "\n"


def save(path_base, result, media, settings, clips=None, title="Minutaggi della partita"):
    """Scrive base.txt e base.csv. Ritorna (txt, csv)."""
    txt, csv = path_base + ".txt", path_base + ".csv"
    with open(txt, "w", encoding="utf-8-sig") as f:
        f.write(build_text(result, media, settings, clips, title))
    with open(csv, "w", encoding="utf-8-sig", newline="") as f:
        f.write(build_csv(result, media, settings, clips))
    return txt, csv
