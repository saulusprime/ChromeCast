# TO-DO — lavoro rimasto

Quanto già corretto è documentato in [AS-IS.md](AS-IS.md), che conserva per
ogni problema il sintomo, la causa, la prova raccolta e il fix applicato.

---

## 🔵 P3 — `Mkchromecast` istanziato più volte all'import

**Stato: parziale** (`68b4a0d8`). Il rumore a video è passato da 18 righe a
1 — l'avviso sul path beta viene stampato una sola volta per processo e il
resto è finito sotto `--debug`. **La causa vera resta**: `audio.py`,
`preferences.py`, `tray_threading.py` e `systray.py` costruiscono ciascuno
un `Mkchromecast()` a livello di modulo.

### Come si manifesta

```console
$ mkchromecast -t
:::config::: WARNING: USING BETA CONFIG PATH: ~/.config/mkchromecast/mkchromecast_beta.cfg
```

Prima erano 18 righe di questo tipo, una terna per ciascuna delle sei
istanze. Ora ne resta una sola, ma le sei istanze ci sono ancora: ogni
`Mkchromecast()` rilegge e rivalida il file di configurazione, e ogni
import di `mkchromecast.audio` riesegue la costruzione del comando
dell'encoder.

### Dove

| File | Cosa fa all'import |
|---|---|
| [`audio.py`](mkchromecast/audio.py) | `_mkcc = mkchromecast.Mkchromecast()` + costruisce il comando |
| [`preferences.py`](mkchromecast/preferences.py) | `_mkcc = mkchromecast.Mkchromecast()` |
| [`tray_threading.py`](mkchromecast/tray_threading.py) | `_mkcc = mkchromecast.Mkchromecast()` |
| [`systray.py`](mkchromecast/systray.py) | `_mkcc = mkchromecast.Mkchromecast()` |

Ognuno di questi porta il commento `TODO(xsdg): Encapsulate this so that we
don't do this work on import.`

### Perché non è stato fatto

È una modifica architetturale, non un fix puntuale: va introdotto il
singleton già previsto dai TODO nel codice e vanno spostati fuori
dall'import gli effetti collaterali di `audio.py`. Tocca il percorso della
tray, quello della CLI e quello del processo di streaming, che oggi si
affidano proprio a quel lavoro fatto all'import.

### Da tenere presente

`Mkchromecast` ha già una cache degli argomenti a livello di classe
([`__init__.py:20-29`](mkchromecast/__init__.py#L20-L29)): le varie istanze
condividono il parsing, ma non il resto dello stato. Inoltre
[`video.py:20`](mkchromecast/video.py#L20) costruisce un `Mkchromecast`
**dentro** il processo di streaming, dopo il `fork`. Qualunque
riorganizzazione va verificata contro quel percorso, oltre che contro
tray e CLI.

---

## Verifiche

Prima di considerare chiuso il punto:

```bash
# la suite deve restare verde (baseline attuale: 42/42)
python -m unittest discover -s tests -v

# la tray deve continuare a partire e a trovare i device
mkchromecast -t

# il cast da CLI deve continuare a funzionare
mkchromecast -n <device> -p 5001
```

Le verifiche complete di tutti i fix già applicati sono in
[AS-IS.md](AS-IS.md#verifiche-di-regressione).
