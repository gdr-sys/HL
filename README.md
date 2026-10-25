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
5. Tu controlli le clip nel player integrato (inizio/fine regolabili trascinando le maniglie, con
   la linea del tempo di tutta la partita) e premi **Crea highlights**. Facoltativa: musica di sottofondo
   con volume regolabile.

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
python main.py              # interfaccia grafica (Qt / PySide6)
```

Per il riconoscimento vocale da sorgente scarica il modello italiano
[vosk-model-small-it-0.22](https://alphacephei.com/vosk/models) in `build_res/models/`
(oppure imposta `RUGBY_VOSK_MODEL` con il percorso della cartella).

Se il player video desse problemi su un PC, si spegne con la variabile d'ambiente
`RUGBY_NO_VIDEO_PLAYER=1` (le clip e il montaggio funzionano lo stesso). Errori imprevisti vengono
mostrati e salvati in `%TEMP%\\rugby_highlights_errore.txt`.

## Da tarare con partite reali

Le soglie per fischi e rumore del pubblico (`rugby_highlights/audio_analysis.py`) e i tempi prima/dopo
(`rugby_highlights/models.py`, o dalle Opzioni nella finestra) sono valori di partenza: vanno
calibrati su una registrazione vera, controllando in particolare:

- se i fischi vengono riconosciuti col microfono della tua telecamera;
- se «meta» e «calcio» vengono sentiti sopra il rumore (soglia `voice_min_conf`);
- se dici la parola **durante** l'azione o dopo (opzione «ritardo»).

ffmpeg incluso nell'installer è la build GPL di BtbN (https://github.com/BtbN/FFmpeg-Builds).

## Più file per partita, solo tagli

- Puoi trascinare **più file** (es. spezzoni da 17 minuti): vengono messi in ordine di nome e trattati come un'unica partita. L'ordine si può cambiare con ↑ / ↓.
- Il montaggio usa **solo tagli netti**: nessuna transizione, nessun effetto, nessuna grafica. Punteggi e titoli si aggiungono dopo (es. in Premiere).

## Copione e riassunto dal comunicato

Nella prima schermata puoi incollare il comunicato stampa. Il programma legge i punteggi progressivi (es. «12-0», «12-7»), capisce chi ha segnato e se è una meta o un calcio, compila il tabellino e, alla creazione del video, scrive anche un file `..._copione.txt` con riassunto, testo da leggere per ogni clip (con orari del video finale), frase del comunicato di contesto e cronologia dei punti. Non usa internet né intelligenza artificiale: se il comunicato non riporta i punteggi progressivi, il testo resta generico.

## Minutaggi per il montaggio completo

Se dici «inizio» al calcio d'inizio (anche all'inizio del secondo tempo), il programma lo segna. Il pulsante **Minutaggi** nella revisione (e il file `..._minutaggi.txt/.csv` creato con il video) elenca ogni «meta», «calcio» e «inizio» con il tempo preciso sulla registrazione, il tempo dall'ultimo «inizio», l'azione che finisce negli highlights e, se i file sono più di uno, il file e il punto dentro al file.

## Marcatori per Premiere

Insieme ai minutaggi il programma crea `..._premiere.xml` (File > Importa in Premiere: una sequenza con i file della partita e i marcatori «Meta 1», «Calcio 2», «Inizio 2° tempo» e «Azione …») e `..._premiere_marcatori.csv` (elenco per il pannello Marcatori). La sequenza è a 25 fps: si può girare a 50p e montare a 25, i tempi in secondi restano uguali.
