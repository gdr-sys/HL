"""Usa i minuti del tabellino («13' m Mascetti») e le parole «inizio» per capire quali
«meta» e «calcio» sentiti sono quelli veri.

Il cronometro di gioco si ferma, quindi il minuto 13 cade nel video DOPO 13 minuti dal fischio
d'inizio: il ritardo cresce col passare del tempo (soste, mischie, infortuni). Per ogni punto
si calcola una finestra in cui la tua parola deve cadere; poi si abbinano i punti alle parole
sentite, in ordine e senza incroci, scegliendo le piu' sicure. Le parole fuori finestra, che
non corrispondono a nessun punto, sono rumore.
"""

from functools import lru_cache

HALF_GAP = (35 * 60.0, 80 * 60.0)       # distanza plausibile tra i due «inizio»
EARLY = 45.0                            # la parola puo' cadere poco prima del minuto
LAG_BASE, LAG_PER_MIN = 60.0, 12.0      # ritardo massimo: 60 s + 12 s per ogni minuto di gioco
CONV_BEFORE, CONV_AFTER = 10.0, 120.0   # dove cercare il «calcio» della trasformazione


def pick_halves(markers):
    """(inizio primo tempo, inizio secondo tempo); None se non si capisce."""
    inz = sorted((m for m in markers if m.kind == "inizio"), key=lambda m: m.time)
    if not inz:
        return None, None
    best, pair = -1.0, None
    for i, a in enumerate(inz):
        for b in inz[i + 1:]:
            if HALF_GAP[0] <= b.time - a.time <= HALF_GAP[1] and a.conf + b.conf > best:
                best, pair = a.conf + b.conf, (a.time, b.time)
    if pair:
        return pair
    return max(inz, key=lambda m: m.conf).time, None


def window(event, halves):
    """(da, a) in secondi di video in cui deve cadere la parola; None = senza limiti."""
    t0 = halves[event.half - 1] if len(halves) >= event.half else None
    if t0 is None:
        return None
    if event.minute is None:
        return (t0, float("inf"))
    base = t0 + event.minute * 60.0
    return (base - EARLY, base + LAG_BASE + LAG_PER_MIN * event.minute)


def assign(cands, events, halves):
    """Abbina candidati (ordinati per tempo) e punti in ordine. Ritorna {indice punto: candidato}."""
    cands = sorted(cands, key=lambda m: m.time)
    n, m = len(events), len(cands)
    wins = [window(e, halves) for e in events]

    @lru_cache(maxsize=None)
    def best(i, j):
        if i == n:
            return 0.0, ()
        top = best(i + 1, j)                       # punto senza parola trovata
        for k in range(j, m):
            w = wins[i]
            if w is not None and not (w[0] <= cands[k].time <= w[1]):
                continue
            gain, rest = best(i + 1, k + 1)
            gain += 1.0 + cands[k].conf
            if gain > top[0]:
                top = (gain, ((i, k),) + rest)
        return top

    return {i: cands[k] for i, k in best(0, 0)[1]}


def refine(markers, report, conv_calcio=True):
    """Tiene le parole che corrispondono ai punti del tabellino. Ritorna (parole, messaggi)."""
    events = [(i, e) for i, e in enumerate(report.events)]
    halves = pick_halves(markers)
    if halves[0] is None:
        return markers, ["Non ho sentito «inizio»: non posso usare i minuti del tabellino "
                         "per scegliere le parole giuste."]
    msgs = []
    if halves[1] is None:
        msgs.append("Ho sentito un solo «inizio»: uso i minuti solo per il primo tempo.")
    metas = [m for m in markers if m.kind == "meta"]
    calci = [m for m in markers if m.kind == "calcio"]
    ev_meta = [(i, e) for i, e in events if e.kind == "meta"]
    got = assign(metas, [e for _, e in ev_meta], halves)
    keep = [m for m in markers if m.kind == "inizio" and m.time in halves]
    keep += list(got.values())

    used = set()
    if conv_calcio:                                  # «calcio» subito dopo la meta = trasformazione
        for k, mt in got.items():
            ev = ev_meta[k][1]
            if ev.points != 7 and ev.detail != "trasformata":
                continue
            near = [c for c in calci if id(c) not in used
                    and mt.time - CONV_BEFORE <= c.time <= mt.time + CONV_AFTER]
            if near:
                c = max(near, key=lambda c: c.conf)
                used.add(id(c))
                keep.append(c)
    ev_calcio = [e for _, e in events if e.kind == "calcio"]
    rest = [c for c in calci if id(c) not in used]
    gotc = assign(rest, ev_calcio, halves)
    keep += list(gotc.values())

    for k, (_, e) in enumerate(ev_meta):
        if k not in got:
            msgs.append(f"Meta {e.when.lower() if e.when else ''}{' ' if e.when else ''}"
                        f"({e.scorer or 'senza nome'}): non ho trovato la tua parola nel punto atteso. "
                        "Aggiungila a mano nella revisione.")
    msgs.insert(0, f"Con i minuti del tabellino ho abbinato {len(got)} mete su {len(ev_meta)} "
                   f"e {len(gotc) + len(used)} calci.")
    return sorted(keep, key=lambda m: m.time), msgs
