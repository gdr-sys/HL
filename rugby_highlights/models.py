"""Strutture dati e impostazioni condivise."""

from dataclasses import dataclass, field


class Cancelled(Exception):
    """Sollevata quando l'utente annulla un'operazione lunga."""


# Parole dette a voce -> tipo di azione
KEYWORDS = {
    "meta": ["meta", "metà"],
    "calcio": ["calcio"],
    "inizio": ["inizio"],      # segna il calcio d'inizio: serve solo ai minutaggi
}


@dataclass
class Settings:
    # Meta: l'azione parte (di solito) dal fischio precedente
    meta_lookback_max: float = 40.0      # quanto indietro cercare il fischio (s)
    meta_lookback_min: float = 8.0       # ignora fischi troppo vicini alla parola
    meta_lookback_default: float = 25.0  # se non si trova nessun fischio
    meta_post: float = 12.0              # festeggiamenti dopo la meta (s)
    whistle_margin: float = 1.5          # secondi prima del fischio
    # Calcio a punti
    calcio_pre: float = 14.0
    calcio_post: float = 7.0
    # Voce
    voice_min_conf: float = 0.6
    use_grammar: bool = True             # riconoscimento limitato alle parole chiave
    delay_correction: float = 0.0        # ritardo tra azione e parola detta (s)
    dedupe_seconds: float = 8.0
    # Montaggio
    merge_gap: float = 2.0
    min_clip_seconds: float = 8.0
    fade: float = 0.0        # 0 = solo tagli netti, nessun effetto
    crf: int = 18
    target_seconds: float = 180.0


@dataclass
class Expected:
    """Quanto dice il tabellino (somma di entrambe le squadre)."""
    meta: int = 0
    calcio: int = 0

    @property
    def any(self) -> bool:
        return self.meta > 0 or self.calcio > 0


@dataclass
class Marker:
    time: float
    kind: str          # "meta" | "calcio"
    word: str = ""
    conf: float = 1.0


@dataclass
class Whistle:
    start: float
    end: float
    strength: float = 0.0


@dataclass
class Clip:
    start: float
    end: float
    kind: str                  # "meta", "calcio", "meta+calcio", "dubbio", "manuale"
    label: str = ""
    source: str = "voce"       # "voce" | "audio" | "manuale"
    note: str = ""
    enabled: bool = True
    conf: float = 1.0

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class AnalysisResult:
    duration: float
    clips: list = field(default_factory=list)
    markers: list = field(default_factory=list)
    whistles: list = field(default_factory=list)
    peaks: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    energy: list = field(default_factory=list)   # livello del rumore, un valore al secondo
