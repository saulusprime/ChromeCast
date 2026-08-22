# TO-DO — lavoro rimasto

**Tutti i problemi individuati nell'analisi Ubuntu sono chiusi**, e con loro i
percorsi che il codice stesso dichiarava rotti. Il registro completo, con
sintomo, causa, prova raccolta e fix per ognuno, è in [AS-IS.md](AS-IS.md).

Suite di test: **114 casi**, tutti verdi (erano 33 all'inizio, 46 dopo
l'analisi Ubuntu, 87 dopo i difetti trovati usando l'applicazione).

Quel che resta è un backlog vero: una funzione da riportare in vita e qualche
riga di testo rimasta indietro rispetto al codice. Il packaging Debian
canonico, che era la seconda voce, è stato fatto (`#24`).

---

## Ripristinare il supporto Sonos

È la voce di backlog principale. Il codice che pilotava gli speaker Sonos è
irraggiungibile da un refactor in poi:
[`cast.py:522`](mkchromecast/cast.py#L522) contiene `_DisabledSonosCasting`,
che nessuno istanzia e il cui `play_cast()` alza prima di arrivare allo
speaker.

La documentazione ora lo dice apertamente (commit `677a4329`) invece di
promettere una funzione assente, quindi **non c'è più niente di ingannevole**:
resta solo il lavoro, se qualcuno lo vuole fare.

Cosa servirebbe:

1. Istanziare la classe quando `soco` trova degli speaker, e unire la sua
   `cclist` a quella dei Chromecast (oggi le due `initialize_cast()` sono
   copie divergenti).
2. Togliere il `raise` da [`play_cast()`](mkchromecast/cast.py#L757) e
   verificare `play_uri()` contro l'API attuale di `soco`.
3. Collegare i controlli della tray, che per i Sonos hanno percorsi separati
   ([`systray.py:431`](mkchromecast/systray.py#L431),
   [`:452`](mkchromecast/systray.py#L452),
   [`:530`](mkchromecast/systray.py#L530)).
4. Unificare le due `input_device()`: quella di `Casting` è stata sistemata
   (`c2e51683`), quella dentro `_DisabledSonosCasting` è ancora la copia
   vecchia col [`raise`](mkchromecast/cast.py#L679).
5. Decidere che fare di `soco`, che oggi è una dipendenza dichiarata in
   [`requirements.txt`](requirements.txt) e in
   [`setup.py:60`](setup.py#L60) ma è importata solo da codice
   irraggiungibile: o torna in servizio con i punti sopra, o va resa
   opzionale come `PyGObject`.

**Serve hardware.** Nessuna di queste modifiche è verificabile senza uno
speaker Sonos in rete; senza prova sul campo si otterrebbe solo codice non
testato al posto di codice disabilitato.

---

## Testi rimasti indietro rispetto al codice

Piccoli, ma sono affermazioni false che qualcuno leggerà.

- **[`AS-IS.md`](AS-IS.md#L965), in fondo alla sezione sulle dipendenze di
  sistema**, dice che il README «cita ancora `python3.6` e
  `python3-pychromecast`». Metà è già risolta e metà non è più un difetto:
  `python3.6` non compare più da nessuna parte, e
  [`README.md:291`](README.md#L291) può tranquillamente raccomandare
  `python3-pychromecast`, perché su Ubuntu 26.04 l'apt ne ha la **14.0.9**,
  dentro il `pychromecast>=14,<15` di `requirements.txt`. La nota va tolta, e
  con lei il link che punta ancora alla riga 286.
- **[`_arg_parsing.py:566`](mkchromecast/_arg_parsing.py#L566)** manda l'utente
  di `--help` su `http://rg3.github.io/yt-dlp/supportedsites.html`, che è
  l'indirizzo del vecchio youtube-dl e non esiste. Il passaggio a `yt-dlp` è
  fatto ovunque tranne che in questa riga; l'indirizzo buono è quello che il
  README già usa,
  `https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md`.

---

## Limitazioni note, dichiarate nel codice

Non sono difetti da correggere ma scelte in attesa, già segnalate all'utente
quando le incontra:

- **Sottotitoli con file mkv**: non supportati; il codice stampa
  `Subtitles with mkv are not supported yet.`
  ([`pipeline_builder.py:356`](mkchromecast/pipeline_builder.py#L356),
  `_input_file_subtitle`). I sottotitoli su file **non**-mkv funzionano da
  `9fbf7685` — prima non funzionavano affatto.

---

## Verifiche

Per qualunque intervento futuro:

```bash
# la suite deve restare verde (baseline attuale: 114/114)
python -m unittest discover -s tests -v
```

Per le prove sul campo, attenzione a quale eseguibile si lancia: `mkchromecast`
sul PATH può essere il pacchetto della distribuzione, non l'albero di lavoro.
Si usa `.venv/bin/python bin/mkchromecast`, come spiegato nelle
[verifiche di regressione](AS-IS.md#verifiche-di-regressione), dove c'è anche
la [prova completa del cast audio](AS-IS.md#prova-completa-cast-audio-reale).
