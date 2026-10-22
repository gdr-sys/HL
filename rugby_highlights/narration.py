"""Copione e riassunto della partita, a partire dal comunicato stampa.

Niente intelligenza artificiale e niente internet: dal comunicato si leggono i punteggi
progressivi (es. "12-7", "19-14"). Da ogni salto di punteggio si capisce quale squadra ha
segnato e quanti punti (7 o 5 = meta, 3 = calcio), e la frase del comunicato che lo racconta
diventa il contesto da leggere. Poi gli eventi si abbinano alle clip nell'ordine della partita.
"""

import re
from dataclasses import dataclass, field

SCORE_RE = re.compile(r"(?<!\d)(\d{1,3})\s*[-–—]\s*(\d{1,3})(?!\d)")
MINUTE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*(?:°|º|ª|’|'|′|esimo|\s*minuto)")
SECOND_HALF_RE = re.compile(r"\b(ripresa|secondo tempo|seconda frazione|secondo tempo)\b", re.I)
END_FIRST_RE = re.compile(r"scadere (?:della|del) (?:prima|primo) (?:frazione|tempo)", re.I)
FINAL_RE = re.compile(r"fischio finale|ultimo assalto|filo di lana|ultimi minuti|ultima azione", re.I)
LEAD_WORDS = re.compile(r"^(?:e|ed|ma|però|mentre|poi|quindi|ma poi)\s+", re.I)

ORD_F = ["prima", "seconda", "terza", "quarta", "quinta", "sesta", "settima", "ottava",
         "nona", "decima"]
ORD_M = ["primo", "secondo", "terzo", "quarto", "quinto", "sesto", "settimo", "ottavo",
         "nono", "decimo"]
WORDS_PER_SECOND = 2.5          # ritmo di lettura per un telecronista tranquillo


class ReportError(Exception):
    pass


@dataclass
class Event:
    side: str                  # "home" | "away" (come nel punteggio del comunicato: prima = casa)
    kind: str                  # "meta" | "calcio"
    points: int
    score: tuple = None        # punteggio dopo questo evento, se noto con certezza
    fragment: str = ""         # la frase del comunicato che lo racconta
    when: str = ""             # "Al 27°", "Nella ripresa", ...
    minute: int = None
    exact: bool = True         # False se piu' punti stanno nello stesso salto (ordine incerto)


@dataclass
class Report:
    events: list = field(default_factory=list)
    final: tuple = (0, 0)
    paragraphs: list = field(default_factory=list)
    text: str = ""

    def count(self, kind, side=None):
        return sum(1 for e in self.events
                   if e.kind == kind and (side is None or e.side == side))


@dataclass
class Names:
    home: str = ""
    away: str = ""

    @property
    def h(self):
        return self.home.strip() or "i padroni di casa"

    @property
    def a(self):
        return self.away.strip() or "gli ospiti"

    def of(self, side):
        return self.h if side == "home" else self.a


# ------------------------------------------------------------------ lettura del comunicato
def _longest_chain(scores):
    """Sottosequenza piu' lunga di punteggi che non scendono mai (scarta citazioni a caso,
    come il risultato finale scritto gia' nell'introduzione)."""
    n = len(scores)
    best, prev = [1] * n, [-1] * n
    for i in range(n):
        for j in range(i):
            if (scores[j][0] <= scores[i][0] and scores[j][1] <= scores[i][1]
                    and scores[j] != scores[i] and best[j] + 1 >= best[i]):
                best[i], prev[i] = best[j] + 1, j
    if not n:
        return []
    k = max(range(n), key=lambda i: (best[i], i))
    chain = []
    while k != -1:
        chain.append(k)
        k = prev[k]
    return chain[::-1]


def _split_points(diff):
    """Salto di punti -> elenco dei punteggi singoli (7, 5, 3, 2).

    Si cerca il minor numero di azioni e, a parita', quello con piu' mete (12 = 7+5, 10 = 5+5).
    """
    options = (7, 5, 3, 2)
    best = {0: (0, 0, [])}
    for total in range(1, diff + 1):
        cands = []
        for p in options:
            if total - p in best:
                cnt, neg_meta, parts = best[total - p]
                cands.append((cnt + 1, neg_meta - (1 if p >= 5 else 0), parts + [p]))
        if cands:
            best[total] = min(cands, key=lambda c: (c[0], c[1]))
    return best[diff][2] if diff in best else []


def _clean_fragment(frag):
    frag = frag.strip(" ,;:)\n\t")
    frag = LEAD_WORDS.sub("", frag)
    if frag.count("(") > frag.count(")"):
        frag += ")"
    if frag:
        frag = frag[0].upper() + frag[1:]
    return frag


def parse_report(text) -> Report:
    text = (text or "").strip()
    if not text:
        raise ReportError("Il comunicato è vuoto.")
    matches = [m for m in SCORE_RE.finditer(text) if int(m.group(1)) < 150 and int(m.group(2)) < 150]
    scores = [(int(m.group(1)), int(m.group(2))) for m in matches]
    chain = _longest_chain(scores)
    if not chain:
        raise ReportError("Nel comunicato non trovo i punteggi (per esempio «12-7»).")

    # limiti delle frasi
    bounds, start = [], 0
    for m in re.finditer(r"[.!?]+(?:\s+|$)|\n+", text):
        bounds.append((start, m.end()))
        start = m.end()
    if start < len(text):
        bounds.append((start, len(text)))

    def sentence_of(pos):
        for a, b in bounds:
            if a <= pos < b:
                return a, b
        return 0, len(text)

    events, prev, prev_end, prev_sent = [], (0, 0), 0, None
    for idx in chain:
        m, cur = matches[idx], scores[idx]
        s_start, s_end = sentence_of(m.start())
        a = max(s_start, prev_end) if prev_sent == (s_start, s_end) else s_start
        last_in_sentence = not any(
            matches[j].start() < s_end and matches[j].start() > m.start() for j in chain
            if j > idx)
        b = s_end if last_in_sentence else m.end() + (1 if text[m.end():m.end() + 1] == ")" else 0)
        fragment = _clean_fragment(text[a:b])
        prev_end, prev_sent = m.end(), (s_start, s_end)

        before = text[:m.start()]
        second_half = bool(SECOND_HALF_RE.search(before)) or bool(SECOND_HALF_RE.search(fragment))
        mm = MINUTE_RE.search(fragment) or MINUTE_RE.search(text[s_start:s_end])
        minute = int(mm.group(1)) if mm else None
        if minute:
            when = f"Al {minute}°"
        elif END_FIRST_RE.search(fragment):
            when = "Allo scadere del primo tempo"
        elif FINAL_RE.search(fragment):
            when = "Sul fischio finale"
        elif second_half:
            when = "Nella ripresa"
        else:
            when = ""

        dh, da = cur[0] - prev[0], cur[1] - prev[1]
        groups = [("home", p) for p in _split_points(dh)] + [("away", p) for p in _split_points(da)]
        if not groups:
            prev = cur
            continue
        # la meta (anche piu' di una) prima, poi i calci
        groups.sort(key=lambda g: (g[0] != "home", g[1] < 5, -g[1]))
        for k, (side, pts) in enumerate(groups):
            known = k == len(groups) - 1
            events.append(Event(side, "meta" if pts >= 5 else "calcio", pts,
                                cur if known else None, fragment, when, minute,
                                exact=len(groups) == 1))
        prev = cur

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    return Report(events, scores[chain[-1]], paragraphs, text)


# ------------------------------------------------------------------ abbinamento alle clip
def align(clip_kinds, events):
    """Abbina clip ed eventi nell'ordine. Ritorna un elenco, per ogni clip, dell'indice
    dell'evento (o None). Le clip dubbie o manuali si abbinano a qualsiasi evento."""
    n, m = len(clip_kinds), len(events)

    def ok(i, j):
        k = clip_kinds[i]
        base = k.split("+")[0]
        if k in ("dubbio", "manuale") or "+" in k:
            return True
        return base == events[j].kind

    table = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best = max(table[i + 1][j], table[i][j + 1])
            if ok(i, j):
                best = max(best, table[i + 1][j + 1] + 1)
            table[i][j] = best
    result, i, j = [None] * n, 0, 0
    while i < n and j < m:
        if ok(i, j) and table[i][j] == table[i + 1][j + 1] + 1:
            result[i] = j
            i, j = i + 1, j + 1
        elif table[i + 1][j] >= table[i][j + 1]:
            i += 1
        else:
            j += 1
    return result


# ------------------------------------------------------------------ testo
def _ordinal(n, feminine):
    words = ORD_F if feminine else ORD_M
    return words[n - 1] if 1 <= n <= len(words) else f"{n}ª" if feminine else f"{n}°"


def _clock(sec):
    sec = int(round(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _score_line(score, names):
    return f"{names.h} {score[0]}, {names.a} {score[1]}"


def event_line(ev, number, names):
    """La frase da leggere per un'azione, breve e sempre adatta alla durata della clip."""
    team = names.of(ev.side)
    if ev.kind == "meta":
        what = f"{_ordinal(number, True)} meta" + (" trasformata" if ev.points == 7 and ev.exact else "")
    else:
        what = f"{_ordinal(number, False)} calcio a punti"
    head = f"{ev.when}, " if ev.when else ""
    line = f"{head}{what} per {team}."
    line = line[0].upper() + line[1:]
    if ev.score:
        line += f" {_score_line(ev.score, names)}."
    return line


def reading_seconds(text):
    return len(text.split()) / WORDS_PER_SECOND


def build_script(report, clips, names=None, title="Highlights della partita"):
    """clips: elenco di oggetti con start, end, kind (le clip attive, in ordine).

    Ritorna il testo completo: riassunto, copione clip per clip, cronologia dei punti.
    """
    names = names or Names()
    events = report.events if report else []
    link = align([c.kind for c in clips], events) if events else [None] * len(clips)
    used = {j for j in link if j is not None}

    out = [title.upper(), "=" * len(title)]
    if report:
        out += [f"Risultato finale: {_score_line(report.final, names)}", ""]
        out += ["RIASSUNTO DELLA PARTITA", "-----------------------"]
        out += [report.paragraphs[0] if report.paragraphs else "", ""]
        if len(report.paragraphs) > 1:
            out += ["Il racconto completo (dal comunicato):", ""]
            out += [p for p in report.paragraphs[1:]]
            out += [""]
    out += ["COPIONE CLIP PER CLIP", "---------------------",
            "Gli orari sono quelli del video finale (mm:ss). Il testo breve sta sempre nella clip;",
            "la frase «Dal comunicato» è il contesto, da leggere per intero solo se c'è tempo.", ""]

    counters, t, warnings = {}, 0.0, []
    for i, c in enumerate(clips):
        dur = c.end - c.start
        j = link[i]
        if j is not None:
            ev = events[j]
            key = (ev.side, ev.kind)
            counters[key] = counters.get(key, 0) + 1
            line = event_line(ev, counters[key], names)
            context = ev.fragment
        else:
            kind = c.kind.split("+")[0]
            line = ("Meta." if kind == "meta" else "Calcio a punti." if kind == "calcio"
                    else "Un'altra azione della partita.")
            context = ""
            if events:
                warnings.append(f"Clip {i + 1} ({_clock(t)}): non l'ho collegata a nessun punto "
                                "del comunicato; il testo è generico.")
        out.append(f"CLIP {i + 1}  [{_clock(t)} – {_clock(t + dur)}]  ({dur:.0f} s)")
        out.append(f"  Da leggere: {line}")
        if context:
            need = reading_seconds(line + " " + context)
            out.append(f"  Dal comunicato: «{context}»")
            if need > dur:
                out.append(f"  (per leggere tutto servono circa {need:.0f} s, la clip ne dura {dur:.0f}: "
                           "meglio la frase breve)")
        out.append("")
        t += dur

    missing = [events[j] for j in range(len(events)) if j not in used]
    if missing:
        warnings.append(f"{len(missing)} punti del comunicato non hanno una clip "
                        "(non registrati o scartati): "
                        + "; ".join(f"{(e.when + ' ') if e.when else ''}{e.kind} per {names.of(e.side)}"
                                    for e in missing) + ".")
    if events:
        out += ["CRONOLOGIA DEI PUNTI", "--------------------"]
        for n, e in enumerate(events, start=1):
            out.append(f"{n:>2}. {e.when + ' - ' if e.when else ''}{e.kind} per {names.of(e.side)}"
                       f" (+{e.points})" + (f"  →  {_score_line(e.score, names)}" if e.score else ""))
        out.append("")
    if warnings:
        out += ["DA CONTROLLARE", "--------------"] + [f"- {w}" for w in warnings] + [""]
    return "\n".join(out)
