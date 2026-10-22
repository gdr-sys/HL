"""Player video integrato (Qt Multimedia) sulla linea del tempo di tutta la partita.

Se la partita e' fatta da piu' file, il player passa da un file all'altro da solo.
Se Qt Multimedia non c'e', mostra un avviso e il resto del programma funziona lo stesso.
"""

import os

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

HAVE_MULTIMEDIA = False
# RUGBY_NO_VIDEO_PLAYER=1 spegne il player (rimedio se Qt Multimedia desse problemi sul PC)
if not os.environ.get("RUGBY_NO_VIDEO_PLAYER"):
    try:
        from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
        from PySide6.QtMultimediaWidgets import QVideoWidget
        HAVE_MULTIMEDIA = True
    except ImportError:  # pragma: no cover - dipende dall'installazione
        pass


class VideoPlayer(QFrame):
    positionChanged = Signal(float)   # secondi dall'inizio della partita
    playingChanged = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("video")
        self.setMinimumSize(480, 270)
        self.media = None
        self._idx = -1            # file attualmente caricato
        self._pending = None      # posizione da raggiungere appena il file e' pronto
        self._play_after = False
        self._stop_at = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.msg = QLabel("")
        self.msg.setAlignment(Qt.AlignCenter)
        self.msg.setWordWrap(True)
        self.msg.setObjectName("muted")
        lay.addWidget(self.msg)
        self.player = None
        if HAVE_MULTIMEDIA:
            self.video = QVideoWidget()
            self.video.setAspectRatioMode(Qt.KeepAspectRatio)
            lay.addWidget(self.video)
            self.player = QMediaPlayer(self)
            self.audio = None
            # senza un'uscita audio (nessuna scheda, servizio spento) Qt puo' andare in crash:
            # in quel caso si guarda il video senza suono
            if QMediaDevices.audioOutputs():
                self.audio = QAudioOutput(self)
                self.audio.setVolume(0.8)
                self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(self.video)
            self.player.positionChanged.connect(self._on_position)
            self.player.mediaStatusChanged.connect(self._on_status)
            self.player.playbackStateChanged.connect(
                lambda _s: self.playingChanged.emit(self.is_playing()))
            self.player.errorOccurred.connect(self._on_error)
            self.msg.hide()
        else:
            self.msg.setText("L'anteprima video non è disponibile su questo computer.\n"
                             "Puoi comunque regolare le clip dai tempi.")

    @property
    def available(self):
        return self.player is not None and self.msg.isHidden()

    # ---- caricamento e posizione
    def load(self, media):
        """media: la partita (Media), anche fatta da piu' file."""
        self.media = media
        self._idx, self._pending, self._stop_at = -1, None, None
        if self.player is None or media is None or not media.sources:
            return
        self.msg.hide()
        self.video.show()
        self._open(0, 0.0, play=False)

    def _open(self, idx, local, play):
        self._idx, self._pending, self._play_after = idx, local, play
        self.player.setSource(QUrl.fromLocalFile(self.media.sources[idx].path))
        self.player.pause()

    def seek(self, t, play=False):
        if self.player is None or self.media is None:
            return
        idx, local = self.media.locate(t)
        if idx != self._idx:
            self._open(idx, local, play)
        else:
            self.player.setPosition(int(local * 1000))
            if play:
                self.player.play()

    def position(self):
        if self.player is None or self.media is None or self._idx < 0:
            return 0.0
        return self.media.sources[self._idx].offset + self.player.position() / 1000.0

    def is_playing(self):
        return (self.player is not None
                and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)

    def play_range(self, start, end):
        """Riproduce da start e si ferma da solo a end (anche attraversando i file)."""
        if self.player is None:
            return
        self._stop_at = end
        self.seek(start, play=True)

    def pause(self):
        self._stop_at = None
        self._play_after = False
        if self.player is not None:
            self.player.pause()

    # ---- eventi del player
    def _on_status(self, status):
        S = QMediaPlayer.MediaStatus
        if self._pending is not None and status in (S.LoadedMedia, S.BufferedMedia):
            pos, self._pending = self._pending, None
            self.player.setPosition(int(pos * 1000))
            if self._play_after:
                self._play_after = False
                self.player.play()
        elif status == S.EndOfMedia and self._stop_at is not None:
            if self._idx + 1 < len(self.media.sources):
                nxt = self.media.sources[self._idx + 1]
                if nxt.offset < self._stop_at:        # la clip continua nel file dopo
                    self._open(self._idx + 1, 0.0, play=True)

    def _on_position(self, ms):
        if self.media is None or self._idx < 0 or self._pending is not None:
            return
        t = self.media.sources[self._idx].offset + ms / 1000.0
        self.positionChanged.emit(t)
        if self._stop_at is not None and self.is_playing() and t >= self._stop_at:
            self.pause()

    def _on_error(self, _err, text):
        self.video.hide()
        self.msg.setText("Non riesco a mostrare questo video nell'anteprima.\n"
                         "Le clip e il montaggio funzionano lo stesso.\n\n" + text)
        self.msg.show()
