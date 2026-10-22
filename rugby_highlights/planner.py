"""Dalle parole dette a voce (e dai fischi) alle clip da montare."""

from .models import Clip

NAMES = {"meta": "Meta", "calcio": "Calcio", "dubbio": "Da verificare",
         "manuale": "Manuale"}


def dedupe_markers(markers, gap):
    out = []
    for m in sorted(markers, key=lambda m: m.time):
        if out and out[-1].kind == m.kind and m.time - out[-1].time < gap:
            if m.conf > out[-1].conf:
                out[-1] = m
            continue
        out.append(m)
    return out


def merge_overlapping(clips, gap):
    out = []
    for c in sorted(clips, key=lambda c: c.start):
        if out and c.start - out[-1].end <= gap:
            p = out[-1]
            p.end = max(p.end, c.end)
            p.kind = p.kind + "+" + c.kind
            p.conf = min(p.conf, c.conf)
            p.note = (p.note + "; unita alla clip vicina").strip("; ")
        else:
            out.append(c)
    return out


def relabel(clips):
    counters = {}
    clips = sorted(clips, key=lambda c: c.start)
    for c in clips:
        parts = []
        for k in c.kind.split("+"):
            counters[k] = counters.get(k, 0) + 1
            parts.append(f"{NAMES.get(k, k)} {counters[k]}")
        c.label = " + ".join(parts)
    return clips


def plan_clips(markers, whistles, duration, s):
    """Una clip per ogni parola riconosciuta."""
    clips = []
    for m in dedupe_markers(markers, s.dedupe_seconds):
        t = max(0.0, m.time - s.delay_correction)
        if m.kind == "meta":
            lo, hi = t - s.meta_lookback_max, t - s.meta_lookback_min
            cands = [w for w in whistles if lo <= w.start <= hi]
            if cands:
                w = max(cands, key=lambda w: w.start)
                start, note = w.start - s.whistle_margin, "inizio dal fischio precedente"
            else:
                start, note = t - s.meta_lookback_default, "inizio stimato (nessun fischio trovato)"
            end = t + s.meta_post
        else:
            start, end, note = t - s.calcio_pre, t + s.calcio_post, ""
        start = max(0.0, start)
        end = min(duration, end)
        if end - start < 1:
            continue
        clips.append(Clip(start, end, m.kind, source="voce", note=note, conf=m.conf))
    return relabel(merge_overlapping(clips, s.merge_gap))


def compare_expected(clips, expected):
    """Confronta le clip trovate col tabellino.

    Restituisce (messaggi, mancanti_totali). Se ne trova piu' del previsto,
    disattiva quelle con minor sicurezza.
    """
    messages, missing_total = [], 0
    if not expected.any:
        return messages, 0
    for kind, name, exp in (("meta", "Mete", expected.meta),
                            ("calcio", "Calci a punti", expected.calcio)):
        voice = [c for c in clips if c.source == "voce"]
        found = sum(c.kind.split("+").count(kind) for c in voice)
        if found == exp:
            messages.append(f"{name}: trovate {found} su {exp}, come da tabellino.")
        elif found < exp:
            missing_total += exp - found
            messages.append(f"{name}: trovate {found} su {exp}. Ne mancano {exp - found}.")
        else:
            extra = found - exp
            pure = sorted((c for c in voice if c.kind == kind), key=lambda c: c.conf)
            disabled = pure[:extra]
            for c in disabled:
                c.enabled = False
                c.note = "sopra il tabellino: probabile falso positivo"
            msg = f"{name}: trovate {found} ma il tabellino ne indica {exp}."
            if disabled:
                msg += f" Ho disattivato le {len(disabled)} meno sicure: controllale."
            if len(disabled) < extra:
                msg += (" Alcune sono finite in clip unite a quelle vicine: "
                        "controlla le clip con '+' nel nome.")
            messages.append(msg)
    return messages, missing_total


def suggest_from_audio(peaks, clips, n, duration, s, pad=10.0):
    """Clip 'da verificare' dai picchi di rumore del pubblico, dove manca qualcosa."""
    out = []
    if n <= 0:
        return out
    for t, score in sorted(peaks, key=lambda p: -p[1]):
        if len(out) >= n:
            break
        if any(c.start - pad <= t <= c.end + pad for c in clips + out):
            continue
        out.append(Clip(max(0.0, t - 25), min(duration, t + 10), "dubbio",
                        source="audio", conf=0.3,
                        note=f"picco di rumore del pubblico (+{score:.0f} dB)"))
    return out


def fit_to_target(clips, target, min_clip):
    """Accorcia le clip (dall'inizio, tenendo i festeggiamenti) per stare nel target.

    Restituisce True se ha modificato qualcosa.
    """
    on = [c for c in clips if c.enabled]
    total = sum(c.duration for c in on)
    if total <= target:
        return False
    reducible = sum(max(0.0, c.duration - min_clip) for c in on)
    if reducible <= 0:
        return False
    ratio = min(1.0, (total - target) / reducible)
    for c in on:
        cut = max(0.0, c.duration - min_clip) * ratio
        c.start += cut
    return True
