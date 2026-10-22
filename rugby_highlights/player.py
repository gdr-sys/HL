"""Player video integrato (Qt Multimedia). Se non e' disponibile mostra un avviso."""

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

import os

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
    positionChanged = Signal(float)   # secondi
    playingChanged = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("video")
        self.setMinimumSize(480, 270)
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

    def load(self, path):
        if self.player is None:
            return
        self.msg.hide()
        self.video.show()
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.pause()

    def seek(self, t):
        if self.player is not None:
            self.player.setPosition(int(max(0.0, t) * 1000))

    def position(self):
        return self.player.position() / 1000.0 if self.player is not None else 0.0

    def is_playing(self):
        return (self.player is not None
                and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)

    def play_range(self, start, end):
        """Riproduce da start e si ferma da solo a end."""
        if self.player is None:
            return
        self._stop_at = end
        self.seek(start)
        self.player.play()

    def pause(self):
        self._stop_at = None
        if self.player is not None:
            self.player.pause()

    def _on_position(self, ms):
        t = ms / 1000.0
        self.positionChanged.emit(t)
        if self._stop_at is not None and self.is_playing() and t >= self._stop_at:
            self.pause()

    def _on_error(self, _err, text):
        self.video.hide()
        self.msg.setText("Non riesco a mostrare questo video nell'anteprima.\n"
                         "Le clip e il montaggio funzionano lo stesso.\n\n" + text)
        self.msg.show()
