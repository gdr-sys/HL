# Rugby Highlights

Programma per Windows che crea il video degli highlights di una partita di rugby
(2-3 minuti) partendo dalla registrazione intera, con sola audio ambiente.

## Come funziona

1. Durante la registrazione dici a voce **«meta»** o **«calcio»** quando c'è un'azione da punti.
2. Il programma ascolta l'audio (riconoscimento vocale offline, senza internet) e trova quei momenti.
3. Per le mete allarga la clip all'indietro fino al **fischio dell'arbitro precedente**
   (massimo ~40 s) e in avanti con i **festeggiamenti** (12 s). Per i calci taglia rincorsa, calcio e reazione.
4. Confronta quanto trovato con il **tabellino** che inserisci. Se manca qualcosa, aggiunge clip
   «da verificare» ai picchi di rumore del pubblico; se ne trova troppe, disattiva le meno sicure.
5. Tu controlli le clip (inizio/fine regolabili, anteprima) e premi **Crea highlights**.

Il video esce alla **stessa risoluzione dell'originale** (ricodificato H.264 ad alta qualità, CRF 18),
con una breve dissolvenza tra una clip e l'altra.

> I tempi del tabellino (minuti di gioco) **non** vengono usati per tagliare, perché il cronometro
> del rugby si ferma e non coincide col tempo del video. Il tabellino serve solo per contare.

## Installazione

Scarica da GitHub la build più recente:

- **Actions** → ultima esecuzione di «Crea installer Windows» → *Artifacts* → `RugbyHighlights-Windows`
- dentro trovi `RugbyHighlights-Setup.exe` (installer, non richiede amministratore) e
  `RugbyHighlights-portatile.zip` (da scompattare e avviare con doppio clic su `RugbyHighlights.exe`).

Per una release stabile: crea un tag, ad esempio `v0.1.0`; l'installer compare in *Releases*.

## Sviluppo

```
pip install -r requirements.txt pytest
python -m pytest            # richiede ffmpeg nel PATH
python -m rugby_highlights video.mp4 --meta 3 --calci 4 --out highlights.mp4   # senza interfaccia
python main.py              # interfaccia grafica
```

Per il riconoscimento vocale da sorgente scarica il modello italiano
[vosk-model-small-it-0.22](https://alphacephei.com/vosk/models) in `build_res/models/`
(oppure imposta `RUGBY_VOSK_MODEL` con il percorso della cartella).

## Da tarare con partite reali

Le soglie per fischi e rumore del pubblico (`rugby_highlights/audio_analysis.py`) e i tempi prima/dopo
(`rugby_highlights/models.py`, o dalle Opzioni nella finestra) sono valori di partenza: vanno
calibrati su una registrazione vera, controllando in particolare:

- se i fischi vengono riconosciuti col microfono della tua telecamera;
- se «meta» e «calcio» vengono sentiti sopra il rumore (soglia `voice_min_conf`);
- se dici la parola **durante** l'azione o dopo (opzione «ritardo»).

ffmpeg incluso nell'installer è la build GPL di BtbN (https://github.com/BtbN/FFmpeg-Builds).
