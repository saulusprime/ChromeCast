# TO-DO — lavoro rimasto

**Tutti i problemi individuati nell'analisi Ubuntu sono chiusi**, e con loro i
percorsi che il codice stesso dichiarava rotti. Il registro completo, con
sintomo, causa, prova raccolta e fix per ognuno, è in [AS-IS.md](AS-IS.md).

Suite di test: **62 casi**, tutti verdi (erano 33 all'inizio, 46 dopo
l'analisi Ubuntu).

---

## Ripristinare il supporto Sonos

È l'unica voce di backlog rimasta. Il codice che pilotava gli speaker Sonos è
irraggiungibile da un refactor in poi:
[`cast.py`](mkchromecast/cast.py) contiene `_DisabledSonosCasting`, che nessuno
istanzia e il cui `play_cast()` alza prima di arrivare allo speaker.

La documentazione ora lo dice apertamente (commit `7b38c65d`) invece di
promettere una funzione assente, quindi **non c'è più niente di ingannevole**:
resta solo il lavoro, se qualcuno lo vuole fare.

Cosa servirebbe:

1. Istanziare la classe quando `soco` trova degli speaker, e unire la sua
   `cclist` a quella dei Chromecast (oggi le due `initialize_cast()` sono
   copie divergenti).
2. Togliere il `raise` da `play_cast()` e verificare `play_uri()` contro
   l'API attuale di `soco`.
3. Collegare i controlli della tray, che per i Sonos hanno percorsi separati
   ([`systray.py:431`](mkchromecast/systray.py#L431),
   [`:452`](mkchromecast/systray.py#L452),
   [`:530`](mkchromecast/systray.py#L530)).
4. Unificare le due `input_device()`: quella di `Casting` è stata sistemata
   (`ee33dc84`), quella dentro `_DisabledSonosCasting` è ancora la copia
   vecchia col `raise`.

**Serve hardware.** Nessuna di queste modifiche è verificabile senza uno
speaker Sonos in rete; senza prova sul campo si otterrebbe solo codice non
testato al posto di codice disabilitato.

---

## Limitazioni note, dichiarate nel codice

Non sono difetti da correggere ma scelte in attesa, già segnalate all'utente
quando le incontra:

- **Sottotitoli con file mkv**: non supportati; il codice stampa
  `Subtitles with mkv are not supported yet.`
  ([`pipeline_builder.py`](mkchromecast/pipeline_builder.py), `_input_file_subtitle`).
  I sottotitoli su file **non**-mkv funzionano da `46bf7d75` — prima non
  funzionavano affatto.

---

## Verifiche

Per qualunque intervento futuro:

```bash
# la suite deve restare verde (baseline attuale: 62/62)
python -m unittest discover -s tests -v
```

Le verifiche funzionali complete sono in
[AS-IS.md](AS-IS.md#verifiche-di-regressione).
