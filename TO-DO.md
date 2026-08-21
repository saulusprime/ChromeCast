# TO-DO — problemi riscontrati su Ubuntu

Analisi statica dell'intero sorgente + esecuzione reale su macchina Ubuntu.
Ogni voce riporta **sintomo → causa → prova raccolta → fix proposto**.

## Ambiente di prova

| | |
|---|---|
| SO | Ubuntu 26.04 LTS (Resolute Raccoon) |
| Python | 3.14.4, in `.venv` creato **senza** `--system-site-packages` |
| Locale | `it_IT.UTF-8` ← rilevante, vedi #4 |
| Audio | PipeWire 1.6.2 con shim PulseAudio (`pactl` 17.0), default sample spec `float32le 2ch 48000Hz` |
| Desktop | GNOME su Wayland (Qt gira via XWayland), estensione `ubuntu-appindicators` presente |
| pychromecast | **14.0.10** — il progetto dichiara solo `pychromecast>=4.2` |
| Encoder | `lame`, `oggenc`, `opusenc`, `sox`, `flac` presenti; **`faac` assente** |
| Porta 5000 | **occupata da `shairport-sync.service`** ← rilevante, vedi #1 |

Stato di partenza: suite di test **33/33 OK**, discovery funzionante, pipeline
`parec | lame` funzionante (94 KB di MP3 valido in 6 s). I problemi stanno
altrove.

---

## 🔴 P0 — Bloccanti  ✅ RISOLTI

Corretti sul branch `fix/p0-blockers` (commit `d059f9d9`, `6d97a3de`,
`80ffc734`). Le sezioni sotto restano come documentazione del problema.
Verifica: 33/33 test verdi, cast reale riuscito verso un Chromecast
(`status_text='Trasmissione: Mkchromecast v0.3.9'`), nessun sink residuo.

### #1 — Il fallimento del bind di Flask non viene rilevato  ✅ `d059f9d9`

**Sintomo.** `mkchromecast -n <device>` sembra partire, il Chromecast si
attiva, ma non esce audio.

**Causa.** Su questa macchina `shairport-sync` occupa la porta 5000, che è il
default di mkchromecast. Flask stampa `Address already in use` e muore, ma
gira dentro un `multiprocessing.Process` daemon
([`stream_infra.py:206-224`](mkchromecast/stream_infra.py#L206-L224)) di cui
nessuno controlla l'esito. Il flusso prosegue fino a
[`bin/mkchromecast:106`](bin/mkchromecast#L106) e istruisce il Chromecast a
leggere `http://<ip>:5000/stream` — che è un server **RTSP AirPlay**.

**Prova.**
```console
$ printf 'GET / HTTP/1.0\r\n\r\n' | nc 127.0.0.1 5000
RTSP/1.0 400 Bad Request
Server: AirTunes/105.1

$ systemctl list-units --state=running | grep -i shairport
shairport-sync.service   Shairport Sync - AirPlay Audio Receiver
```
Con `-p 5001` Flask parte correttamente (`* Running on http://192.168.1.192:5001`).

**Fix.** Due interventi in [`stream_infra.py`](mkchromecast/stream_infra.py):
controllo preventivo della porta + attesa di readiness dopo lo start.

```python
import errno
import socket

def port_is_free(host: str, port: int) -> bool:
    """True se possiamo fare bind su host:port."""
    family = socket.AF_INET
    probe_host = host if host not in ("", "0.0.0.0") else "0.0.0.0"
    with socket.socket(family, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((probe_host, port))
            return True
        except OSError as e:
            if e.errno in (errno.EADDRINUSE, errno.EACCES):
                return False
            raise


class PipelineProcess:
    ...
    def start(self) -> None:
        if not port_is_free(self._host, self._port):
            print(colors.error(
                f"La porta {self._port} e' gia' occupata da un altro "
                "programma."))
            print(colors.options("Suggerimento:") +
                  f" riprova con --port {self._port + 1}, oppure libera la "
                  f"porta (su Ubuntu spesso e' shairport-sync: "
                  "`systemctl status shairport-sync`).")
            raise SystemExit(1)
        self._proc.start()

    def wait_until_serving(self, timeout: float = 10.0) -> bool:
        """Attende che il server accetti connessioni; False se non parte."""
        host = "127.0.0.1" if self._host in ("", "0.0.0.0") else self._host
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._proc.is_alive():
                return False
            try:
                with socket.create_connection((host, self._port), timeout=0.5):
                    return True
            except OSError:
                time.sleep(0.2)
        return False
```

`PipelineProcess.__init__` deve memorizzare `self._host` / `self._port`
(oggi li passa solo agli args del processo figlio).

Poi in [`audio.py:main()`](mkchromecast/audio.py#L143-L145) e
[`video.py:main()`](mkchromecast/video.py#L51-L58):

```python
def main():
    pipeline = stream_infra.PipelineProcess(_flask_init, ip, port, platform)
    pipeline.start()
    if not pipeline.wait_until_serving():
        print(colors.error("Il server di streaming non e' partito. Interrompo."))
        utils.terminate()
```

**Workaround immediato senza toccare il codice:** `mkchromecast -p 5001 ...`

---

### #2 — Crash con pychromecast 14: `RequestFailed: Failed to execute play`  ✅ `6d97a3de`

**Sintomo.** Traceback Python non gestito subito dopo l'avvio del cast.

```
File "bin/mkchromecast", line 106, in start_audiocast
    self.cc.play_cast()
File "mkchromecast/cast.py", line 330, in play_cast
    media_controller.play()
pychromecast.error.RequestFailed: Failed to execute play.
```
Preceduto da `PLAY command requested but no session is active.`

**Causa.** In [`cast.py:325-339`](mkchromecast/cast.py#L325-L339):

```python
media_controller.play_media(play_url, media_type, title=..., stream_type="LIVE")

if media_controller.is_active:     # <- stato "stale", puo' essere True a torto
    media_controller.play()        # <- riga 330: qui e' esploso
...
time.sleep(5.0)
media_controller.play()            # <- riga 339: secondo play() incondizionato
```

Tre problemi sommati:
1. `play_media()` è **asincrona** e in pychromecast ≥ 9 non lancia l'app da
   sola; la sessione va attesa con `block_until_active()`, che il codice non
   chiama mai. `time.sleep(5.0)` non è un sostituto.
2. `MediaController.play()` in pychromecast ≥ 9 fa `wait_response()` e alza
   `RequestFailed`; nella 4.x era fire-and-forget. Nessun `try/except`.
3. Non si fa `quit_app()` se il device sta già eseguendo un'altra app. Nel
   test il device era su *Audio Mirroring* (`app_id='8E6C866D'`), ed è per
   questo che `is_active` risultava `True` pur senza sessione media.

**Fix.** Sostituire il blocco in `play_cast()`:

```python
import pychromecast

# Se il device sta facendo altro, liberalo prima.
if self.cast.app_id not in (None, pychromecast.IDLE_APP_ID):
    if self.mkcc.debug:
        print(f"Chiudo l'app attiva sul device: {self.cast.app_id}")
    self.cast.quit_app()
    self.cast.wait(timeout=10)

media_controller.play_media(
    play_url, media_type, title=self.title, stream_type="LIVE",
)

media_controller.block_until_active(timeout=15.0)
if not media_controller.is_active:
    print(colors.error(
        "Il device non ha avviato la sessione media. Verifica che "
        f"{play_url} sia raggiungibile dalla rete del device."))
    raise SystemExit(1)

try:
    media_controller.play()
except pychromecast.error.RequestFailed as e:
    print(colors.error(f"Il device ha rifiutato il comando play: {e}"))
    raise SystemExit(1)
```

Eliminare del tutto `time.sleep(5.0)` e il secondo `media_controller.play()`.

**Fix collegato — `requirements.txt`:** `pychromecast>=4.2` è troppo permissivo
e copre due API incompatibili. Portare a `pychromecast>=14,<15` e allineare il
codice (vedi anche #10).

---

### #3 — `pip install PyGObject` fallisce → `import gi` non funziona  ✅ `80ffc734`

**Sintomo.** L'installazione dei requirements si interrompe. È il motivo per
cui `PyGObject` è stato spostato in fondo a `requirements.txt` (modifica non
committata attualmente presente nel working tree).

**Prova.**
```
Run-time dependency girepository-2.0 found: NO (tried pkg-config and cmake)
../meson.build:35:9: ERROR: Dependency 'girepository-2.0' is required but not found.
error: metadata-generation-failed
```
`gobject-introspection-1.0` 1.86 è presente, ma PyGObject ≥ 3.52 richiede il
modulo pkg-config **`girepository-2.0`**, fornito da `libgirepository-2.0-dev`,
che non è installato. Il pacchetto apt `python3-gi` **è** installato ma il venv
è stato creato senza `--system-site-packages`, quindi non lo vede.

**Fix (scelta A — consigliata).** `PyGObject` serve **solo** per le notifiche
desktop, ed è già avvolto in `try/except ImportError`. Toglierlo dai
requirements obbligatori:

```diff
--- a/requirements.txt
+++ b/requirements.txt
@@
 requests
 psutil
 Flask
 netifaces
 pychromecast>=4.2
 PyQt5
 soco
-PyGObject
+
+# Opzionale: solo per le notifiche desktop su Linux.
+# Richiede i pacchetti di sistema:
+#   sudo apt install libgirepository-2.0-dev libcairo2-dev
+# oppure usa il python3-gi di sistema creando il venv con
+#   python3 -m venv --system-site-packages .venv
+# PyGObject
```

**Fix (scelta B).** Tenerlo obbligatorio e documentare in `README.md` la
dipendenza di sistema `libgirepository-2.0-dev`.

**Bug correlato da correggere comunque.** In
[`systray.py:315`](mkchromecast/systray.py#L315),
[`:468`](mkchromecast/systray.py#L468),
[`:706`](mkchromecast/systray.py#L706) si intercetta solo `ImportError`, ma
`gi.require_version("Notify", "0.7")` alza **`ValueError`** se sul sistema c'è
solo il typelib `Notify-0.8` (già il caso su alcune distro; qui c'è ancora
0.7). Da rendere tollerante:

```python
try:
    import gi
    try:
        gi.require_version("Notify", "0.8")
    except ValueError:
        gi.require_version("Notify", "0.7")
    from gi.repository import Notify
    ...
except (ImportError, ValueError):
    print("Per le notifiche su Linux installa libnotify e python-gobject")
```

Il blocco è ripetuto 3 volte quasi identico: conviene estrarlo in una singola
funzione `_notify(title, message)`.

---

## 🟠 P1 — Gravi  ✅ RISOLTI

Corretti sul branch `fix/p0-blockers` (commit `6fcb4454`, `7dc8ec28`,
`53c8b7ee`). Verifica: 35/35 test verdi, `--reset` pulisce i sink in
locale `it_IT`, `--discover | cat` mostra l'output ed esce 0,
`--sample-rate 48000` serve davvero uno stream a 48000Hz.

### #4 — `--reset` non rimuove i sink se il locale non è inglese  ✅ `7dc8ec28`

**Sintomo.** I sink `Mkchromecast` si accumulano ad ogni crash e `--reset` non
li pulisce.

**Causa.** [`pulseaudio.py:89-94`](mkchromecast/pulseaudio.py#L89-L94) fa
parsing dell'output *tradotto* di `pactl`:

```
Sink #56
	Nome: alsa_output...                 ← non "Name:"
	Modulo di appartenenza: 4294967295   ← non "Owner Module:"
```

**Prova.**
```console
$ python -c "from mkchromecast import pulseaudio as p; p.get_sink_list(); print(p._sink_num)"
[]
$ LC_ALL=C python -c "from mkchromecast import pulseaudio as p; p.get_sink_list(); print(p._sink_num)"
[536870916]
```
Con `LC_ALL=C` il `--reset` rimuove il sink correttamente; in `it_IT` no.

**Fix.** Forzare il locale C su **tutte** le invocazioni di `pactl` e usare
l'output JSON, le cui chiavi non sono tradotte (`pactl` ≥ 16, qui 17.0):

```python
import json
import os
import subprocess

_PACTL_ENV = {**os.environ, "LC_ALL": "C", "LANGUAGE": "C"}


def _pactl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["pactl", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=_PACTL_ENV, timeout=60, check=True,
    )


def get_sink_list() -> None:
    global _sink_num
    result = _pactl("--format=json", "list", "sinks")
    sinks = json.loads(result.stdout.decode("utf-8"))
    _sink_num = [
        int(s["owner_module"])
        for s in sinks
        if s.get("name", "").startswith("Mkchromecast")
    ]
```

Verificato in locale `it_IT`: restituisce `[536870916, 536870917]` con due sink
residui. Applicare `_pactl()` anche a `create_sink`, `remove_sink` e
`check_sink`.

> Se si preferisce restare sul parsing testuale, il minimo indispensabile è
> aggiungere `env=` con `LC_ALL=C` **e** correggere #5.

---

### #5 — `findall(stringa, re.MULTILINE)` — il flag viene passato come `pos`  ✅ `7dc8ec28`

**Causa.** [`pulseaudio.py:94`](mkchromecast/pulseaudio.py#L94):

```python
matches = pattern.findall(result.stdout.decode("utf-8"), re.MULTILINE)
```

Il secondo argomento posizionale di `Pattern.findall` è **`pos`**, non i flag
(che sono già stati fissati in `re.compile`). `re.MULTILINE` vale `8`, quindi
la ricerca parte dal carattere 8, saltando i primi 8 byte dell'output — cioè
l'intestazione `Sink #NN` del **primo** sink.

**Prova.** Con lo stesso input, in locale C:
```
codice attuale  findall(s, re.MULTILINE) : []            ← Mkchromecast e' il 1o sink
corretto        findall(s)               : ['536870916']
```

**Fix.** `pattern.findall(testo)`. Reso irrilevante se si adotta il JSON di #4.

---

### #6 — Sample rate incoerente fra `parec` e l'encoder  ✅ `53c8b7ee`

**Sintomo.** Con `-c opus` l'audio si sente più veloce/acuto (~8.8%). Con
`-c mp3` l'opzione `--sample-rate` non ha alcun effetto.

**Causa.** `parec` viene invocato **senza** `--rate`, quindi negozia sempre
44100 Hz, mentre il samplerate richiesto viene passato solo all'encoder.

[`stream_infra.py:189`](mkchromecast/stream_infra.py#L189):
```python
c_parec = [FlaskServer._backend.path, "--format=s16le", "-d", "Mkchromecast.monitor"]
```

**Prova.**
```console
$ parec -v --format=s16le -d Mkchromecast.monitor
Using sample spec 's16le 2ch 44100Hz'    # sempre, qualunque sia --sample-rate
```

| comando | parec produce | encoder riceve | esito |
|---|---|---|---|
| `-c opus` (forza 48000) | 44100 Hz | `opusenc --raw-rate 48000` | **+8.8% di velocità** |
| `-c flac --sample-rate 48000` | 44100 Hz | `flac --sample-rate 48000` | idem |
| `-c wav --sample-rate 48000` | 44100 Hz | `sox -r 48000` | idem |
| `-c mp3 --sample-rate 48000` | 44100 Hz | `lame -r` (nessun rate) | flag ignorato in silenzio |

`-c opus` è rotto **sempre** con il backend di default, senza bisogno di flag:
[`__init__.py:216-217`](mkchromecast/__init__.py#L216-L217) forza
`samplerate = 48000` per opus.

**Fix, parte A** — dire a `parec` il rate voluto
([`stream_infra.py:189`](mkchromecast/stream_infra.py#L189)):

```python
c_parec = [
    FlaskServer._backend.path,
    "--format=s16le",
    f"--rate={FlaskServer._samplerate}",
    "--channels=2",
    "-d", "Mkchromecast.monitor",
]
```
(`FlaskServer._samplerate` è già disponibile nella classe.)

**Fix, parte B** — passare il rate di input anche agli encoder che oggi non lo
ricevono, in
[`pipeline_builder._build_linux_other_command`](mkchromecast/pipeline_builder.py#L140-L207).
Flag verificati sui binari installati:

```python
if self._settings.codec == "mp3":
    # lame -s vuole i kHz
    return ["lame",
            "-r",
            "-s", str(int(self._settings.samplerate) / 1000),
            "-b", str(self._settings.bitrate),
            "-", "-"]

if self._settings.codec == "ogg":
    return ["oggenc",
            "-b", str(self._settings.bitrate),
            "-Q", "-r",
            "--raw-rate", self._settings.samplerate,   # <-- aggiunto
            "--ignorelength",
            "-"]

if self._settings.codec == "aac":
    return ["faac",
            "-b", str(self._settings.bitrate),
            "-X", "-P",
            "-R", self._settings.samplerate,           # <-- aggiunto
            "-c", "18000",
            "-o", "-", "-"]
```
`opusenc`, `sox` e `flac` già ricevono il rate corretto: una volta sistemato
`parec` (parte A) tornano coerenti.

I test in `tests/test_pipeline_builder.py::testLinuxOther` vanno aggiornati di
conseguenza.

---

### #7 — Tutto l'output si perde quando si redirige; exit code sempre 137  ✅ `6fcb4454`

**Sintomo.**
```console
$ mkchromecast --discover | cat
--- exit 137 ---                        # nessun output

$ PYTHONUNBUFFERED=1 mkchromecast --discover | cat
0  Gcast  Salotto                       # i device c'erano
1  Gcast  Seminterrato
--- exit 137 ---
```

**Causa.** [`utils.py:127-133`](mkchromecast/utils.py#L127-L133):

```python
def terminate() -> None:
    del_tmp()
    parent = psutil.Process(os.getpid())
    for child in parent.children(recursive=True):
        child.kill()
    parent.kill()          # SIGKILL su se stesso
```
Quando stdout è una pipe Python usa buffering a blocchi; `SIGKILL` non permette
alcun flush. In più l'exit code è sempre 137 (128+9), il che rompe qualunque
script o integrazione.

**Fix.**
```python
def terminate(exit_code: int = 0) -> None:
    """Chiude figli e processo corrente. Non ritorna."""
    del_tmp()

    parent = psutil.Process(os.getpid())
    children = parent.children(recursive=True)
    for child in children:
        child.terminate()                       # SIGTERM: consente cleanup
    _, alive = psutil.wait_procs(children, timeout=3)
    for child in alive:
        child.kill()                            # solo i recalcitranti

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)                         # niente SIGKILL su se stessi
```
`os._exit` (non `sys.exit`) perché `terminate()` viene chiamata anche
dall'handler `atexit` registrato in
[`bin/mkchromecast:60`](bin/mkchromecast#L60), dove un `SystemExit` verrebbe
solo stampato. Il flush esplicito prima di `os._exit` è obbligatorio.

Aggiungere `import sys` in `utils.py`.

---

## 🟡 P2 — Bug certi, non raggiunti dal percorso Linux di default

### #8 — `node.py`: `UnboundLocalError` su `bitrate` e `samplerate`

[`node.py:41-51`](mkchromecast/node.py#L41-L51) dichiara i tipi ma non assegna
mai i valori prima dell'uso:

```python
bitrate: int          # sola annotazione, nessun valore
samplerate: int
if mkcc.youtube_url is None:
    if mkcc.backend == "node":
        bitrate = utils.clamp_bitrate(mkcc.codec, bitrate)   # <-- riga 45
```

**Prova (riprodotto).**
```
UnboundLocalError: cannot access local variable 'bitrate' where it is not
associated with a value
```
Stesso problema per `samplerate` se il codec non è in
`QUANTIZED_SAMPLE_RATE_CODECS`.

**Fix.**
```python
bitrate = mkcc.bitrate
samplerate = mkcc.samplerate

if mkcc.youtube_url is None and mkcc.backend == "node":
    bitrate = utils.clamp_bitrate(mkcc.codec, bitrate)
    print(colors.options("Using bitrate: ") + f"{bitrate}k.")
    if mkcc.codec in constants.QUANTIZED_SAMPLE_RATE_CODECS:
        samplerate = utils.quantize_sample_rate(mkcc.codec, samplerate)
    print(colors.options("Using sample rate:") + f" {samplerate}Hz.")
```

**Come ci si arriva su Linux.** `node` non è tra i backend audio Linux
([`constants.py:37`](mkchromecast/constants.py#L37)), ma
[`__init__.py:117`](mkchromecast/__init__.py#L117) prende `backend` dal file di
config della tray **senza validarlo**: basta scrivere `backend = node` in
`~/.config/mkchromecast/mkchromecast_beta.cfg`. Da correggere anche quello:

```python
if tray_config:
    self.backend = tray_config.backend
    if self.backend not in backend_options:
        print(colors.warning(
            f"Backend '{self.backend}' da config non valido su "
            f"{self.platform}; uso '{backend_options[0]}'."))
        self.backend = backend_options[0]
```

### #9 — Node non viene trovato su Ubuntu

[`node.py:56`](mkchromecast/node.py#L56) cerca solo in percorsi hardcoded:

```python
paths = ["/usr/local/bin/node", "./bin/node", "./nodejs/bin/node"]
```
Su Ubuntu il binario è in `/usr/bin/node`, quindi stampa "Node is not
installed..." anche quando è installato.

**Fix.**
```python
import shutil
node_bin = shutil.which("node") or shutil.which("nodejs")
```
Stessa logica già presente e corretta in
[`video.py:86-104`](mkchromecast/video.py#L86-L104), che usa `utils.is_installed`
sul `PATH`: uniformare le due.

### #10 — `Chromecast.device` è stato rimosso in pychromecast 14

[`cast.py`](mkchromecast/cast.py), in
`_DisabledSonosCasting.get_devices`, fa `print(self.cast.device)`.
L'attributo non esiste più; il sostituto è `self.cast.cast_info`
(verificato: è assegnato in `Chromecast.__init__`). Il codice sta in una classe
già marcata come rotta, ma va sistemato quando la si riabilita.

---

## 🔵 P3 — Minori / robustezza  ✅ RISOLTI (una voce solo in parte)

- ✅ `81bd771f` — **`check_sink()` ritornava `None` se `pactl` mancava**, e
  l'unico chiamante testava `is False`: l'assenza di `pactl` veniva quindi
  letta come "il sink esiste già" e non se ne creava mai uno. Ora l'assenza è
  un `PulseAudioNotAvailable` esplicito, con il pacchetto da installare; la
  CLI lo trasforma in una riga di errore ed esce 1, la tray segna il
  tentativo come fallito senza morire.

- ✅ `7dc8ec28` — **`create_sink()` non verificava l'esito.** Ora controlla il
  return code e l'indice del modulo, e `remove_sink()` è idempotente.

- ✅ `68b4a0d8` — **Icone della tray legate alla CWD.** Risolte a partire dalla
  directory del package, poi da `/usr/share`, poi dalla CWD per il bundle
  macOS. Verificato da `/`, `/tmp` e dal repo.

- ⚠️ `68b4a0d8` — **Config riletto 6 volte all'avvio della tray.** Il rumore è
  passato da 18 righe a 1 (avviso sul path beta una sola volta per processo,
  il resto sotto `--debug`). **La causa vera resta**: `audio.py`,
  `preferences.py`, `tray_threading.py` e `systray.py` costruiscono un
  `Mkchromecast()` a livello di modulo. Serve il singleton già previsto dai
  TODO nel codice: è una modifica architetturale, non un fix puntuale.

- ✅ `81bd771f` — **`global cast` ribindato da modulo a oggetto.** Ora è un
  attributo del `Player`, che è anche come la tray lo rilegge.

- ✅ `81bd771f` — **`or None` senza effetto e confronto di versioni fra
  stringhe** (che metteva `0.3.9` sopra `0.3.10`), con il tag estratto via
  `str.strip`. Ora si legge il JSON e si confronta con
  `utils.version_tuple`, coperta da test.

- ✅ `536f7d73` — **`backend_handler` uccideva processi non suoi.** Niente più
  `pkill -f ffmpeg`: si percorre il proprio albero di processi con `psutil`.
  Verificato che un ffmpeg estraneo resti `running` mentre il nostro passa a
  `stopped`.

- ✅ `9004388b` — **`setup.py` non dichiarava le dipendenze.** `requires=` →
  `install_requires=`, elenco corretto (mancavano pychromecast e soco, c'era
  `mutagen` che non è importato da nessuna parte), `python_requires=">=3.9"`.

- ✅ `9004388b` — **`netifaces` sostituito con `ifaddr`**, già presente come
  dipendenza di `zeroconf`. Niente più compilazione durante `pip install`.

- ✅ `536f7d73` — **`audio.py` non risolveva davvero il backend.** Ora
  `shutil.which` in ogni modalità, con errore chiaro se il backend non c'è;
  i percorsi hardcoded restano solo su Darwin per il bundle `.app`.

---

## Dipendenze di sistema per Ubuntu  ✅ documentate nel README

```bash
# runtime
sudo apt install pulseaudio-utils ffmpeg lame vorbis-tools opus-tools flac sox

# opzionale: notifiche desktop (PyGObject)
sudo apt install libgirepository-2.0-dev libcairo2-dev

# opzionale: codec AAC (non nei repo principali Ubuntu)
# faac va compilato a mano oppure si usa --encoder-backend ffmpeg
```

Il `README.md` cita ancora `python3.6` e `python3-pychromecast`
([README.md:286](README.md#L286)); da aggiornare.

---

## Checklist

- [x] #1 Rilevare il fallimento di bind + readiness check (`stream_infra.py`, `audio.py`, `video.py`) — `d059f9d9`
- [x] #2 `block_until_active()` + `quit_app()` + `try/except RequestFailed` (`cast.py`); pinnare `pychromecast>=14,<15` — `6d97a3de`
- [x] #3 Rendere `PyGObject` opzionale; gestire `ValueError` su `require_version` (`systray.py`) — `80ffc734`
- [x] #4 `LC_ALL=C` + parsing JSON in tutte le chiamate a `pactl` (`pulseaudio.py`) — `7dc8ec28`
- [x] #5 `findall(testo)` senza il flag come `pos` (`pulseaudio.py:94`) — `7dc8ec28`
- [x] #6 `--rate` a `parec` + rate di input a `lame`/`oggenc`/`faac`; aggiornare i test — `53c8b7ee`
- [x] #7 `terminate()` con SIGTERM, flush e `os._exit(0)` (`utils.py`) — `6fcb4454`
- [x] #8 Inizializzare `bitrate`/`samplerate` (`node.py`); validare il backend da config — `c0072fa6`
- [x] #9 `shutil.which("node")`, e `--port` non più ignorato — `c0072fa6`
- [x] #10 `cast_info` al posto di `device` (`cast.py`) — `c0072fa6`
- [x] P3 — `81bd771f`, `68b4a0d8`, `536f7d73`, `9004388b`
- [ ] Resta da P3: il singleton `Mkchromecast` (oggi istanziato 6 volte all'import)
- [x] README: dipendenze di sistema Ubuntu aggiornate

## Verifiche di regressione

```bash
# 1. i test devono restare verdi (baseline: 33/33)
python -m unittest discover -s tests -v

# 2. discovery: output visibile anche in pipe, exit code 0
mkchromecast --discover | cat ; echo "exit=$?"

# 3. reset: deve funzionare nel locale dell'utente, non solo in C
pactl load-module module-null-sink sink_name=Mkchromecast
mkchromecast --reset
pactl list sinks short | grep -i mkchrome    # deve essere vuoto

# 4. porta occupata: messaggio chiaro, niente cast a vuoto
mkchromecast -p 5000 -n <device>             # con shairport-sync attivo

# 5. coerenza del sample rate
parec -v --format=s16le --rate=48000 -d Mkchromecast.monitor   # deve dire 48000Hz
```
