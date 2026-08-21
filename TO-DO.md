# TO-DO — lavoro rimasto

**Tutti i problemi individuati nell'analisi Ubuntu sono chiusi.** Il registro
completo, con sintomo, causa, prova raccolta e fix per ognuno, è in
[AS-IS.md](AS-IS.md).

Suite di test: **46 casi**, tutti verdi (erano 33 prima degli interventi).

---

## Non affrontato: percorsi che il codice stesso dichiara rotti

Questi punti **non facevano parte dell'analisi Ubuntu**: sono difetti
preesistenti che il sorgente segnala da sé, e nessuno di essi si incontra
sul percorso Linux normale (cast audio, video, tray). Sono elencati qui
perché è l'unico backlog che resta.

### Supporto Sonos

[`cast.py`](mkchromecast/cast.py) contiene `_DisabledSonosCasting`, la cui
docstring dice *"This is broken, but should simplify the Chromecast support
code until the Sonos support can be unbroken at some later point."*
`play_cast()` alza deliberatamente:

```python
raise Exception("Internal error: This code path is broken and "
                "needs to be fixed.")
```

La classe non è raggiungibile dall'esterno: `soco` viene importato, ma
`Casting` non la usa mai. Il supporto Sonos è quindi **assente**, non solo
difettoso — il README però lo pubblicizza ancora.

### Riselezione del device dopo un indice non valido

[`cast.py`](mkchromecast/cast.py), in `Casting.input_device()`: sul ramo
`except IndexError` il codice originale chiamava un metodo inesistente, e
oggi c'è al suo posto un `raise Exception("Internal error: Never worked")`.
Si arriva lì digitando un indice fuori intervallo dopo `-s`.

### Riconnessione automatica del backend node

[`node.py:163`](mkchromecast/node.py#L163): quando il server node muore, il
percorso di riconnessione alza `Internal error: Never worked`. Il commento
sopra spiega il perché — la vecchia implementazione poteva generare
processi a catena all'infinito. Su Linux il backend node non è comunque fra
quelli audio supportati.

### `-vf` specificato due volte

[`pipeline_builder.py:244-246`](mkchromecast/pipeline_builder.py#L244-L246):
usando insieme `--subtitles` e `--resolution` su un file non-mkv, ffmpeg
riceve `-vf` due volte e ne ignora uno. Difetto ereditato
dall'implementazione originale e annotato nel codice.

---

## Verifiche

Per qualunque intervento futuro:

```bash
# la suite deve restare verde (baseline attuale: 46/46)
python -m unittest discover -s tests -v
```

Le verifiche funzionali complete sono in
[AS-IS.md](AS-IS.md#verifiche-di-regressione).
