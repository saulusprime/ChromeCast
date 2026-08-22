# AS-IS — lavoro svolto sui problemi Ubuntu

Registro di quanto è stato corretto rispetto all'analisi iniziale del
codice su Ubuntu. Ogni voce conserva **sintomo → causa → prova raccolta →
fix applicato**, con il commit che lo introduce.

Ciò che resta aperto sta in [TO-DO.md](TO-DO.md).

**Stato:** tutti i problemi individuati sono chiusi, e con loro i tre percorsi
che il codice stesso dichiarava rotti (#11, #12, #13), le promesse su Sonos
che il codice non manteneva (#14), i due difetti emersi impacchettando
(#15, #16) e i cinque segnalati usando l'applicazione sul desktop
(#17, #18, #19, #20, #21, #22, #23) e il packaging reso distribuibile
(#24). Suite di test da 33 a **114** casi.

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
| Device di prova | **Seminterrato** — sintoampli Sony TA-AN1000 collegato alle casse (192.168.1.126) — e **Salotto** |

Stato di partenza: suite di test **33/33 OK**, discovery funzionante, pipeline
`parec | lame` funzionante (94 KB di MP3 valido in 6 s). I problemi stanno
altrove.

---

---

## 🔴 P0 — Bloccanti  ✅ RISOLTI

Corretti sul branch `fix/p0-blockers` (commit `d059f9d9`, `6d97a3de`,
`80ffc734`). Le sezioni sotto restano come documentazione del problema.
Verifica: 33/33 test verdi, cast reale riuscito verso un Chromecast
(`status_text='Trasmissione: Mkchromecast v0.3.9'`), nessun sink residuo. La
sessione completa, con l'output riga per riga, è in
[Prova completa: cast audio reale](#prova-completa-cast-audio-reale).

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

---

## 🟡 P2 — Bug certi, non raggiunti dal percorso Linux di default  ✅ RISOLTI

Corretti in `c0072fa6`. Nel farlo è emerso che il comando node aveva la
porta hardcoded a 5000 mentre `cast.py` costruisce l'URL da `--port`:
corretto insieme.

### #8 — `node.py`: `UnboundLocalError` su `bitrate` e `samplerate`  ✅ `c0072fa6`

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

### #9 — Node non viene trovato su Ubuntu  ✅ `c0072fa6`

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

### #10 — `Chromecast.device` è stato rimosso in pychromecast 14  ✅ `c0072fa6`

[`cast.py`](mkchromecast/cast.py), in
`_DisabledSonosCasting.get_devices`, fa `print(self.cast.device)`.
L'attributo non esiste più; il sostituto è `self.cast.cast_info`
(verificato: è assegnato in `Chromecast.__init__`). Il codice sta in una classe
già marcata come rotta, ma va sistemato quando la si riabilita.

---

---

## 🔵 P3 — Minori / robustezza  ✅ RISOLTI

- ✅ `a9936424` — **`Mkchromecast` istanziato sei volte all'import.** `audio.py`,
  `preferences.py`, `tray_threading.py` e `systray.py` ne costruivano uno
  ciascuno, quindi ogni avvio faceva sei volte il parsing della riga di
  comando e il caricamento del file di configurazione. Ora la costruzione
  senza argomenti restituisce un'istanza condivisa; passando `args`
  espliciti si ottiene comunque un oggetto separato, come richiesto dai
  test.

  Anche `audio.py` faceva il lavoro vero all'import (risoluzione del
  backend, clamp del bitrate, quantizzazione del sample rate, costruzione
  del comando, e relative stampe). Da Python 3.14 `multiprocessing` usa
  **`forkserver`**: il processo di streaming re-importa il modulo invece di
  ereditarlo, quindi tutte quelle righe venivano stampate una seconda
  volta. Ora le impostazioni si costruiscono al primo uso e le stampa le fa
  solo il processo che avvia il server.

  Lo stesso passaggio a `forkserver` aveva rotto in silenzio la pulizia di
  emergenza del processo di streaming: chiamava `remove_sink()`, ma lo
  stato che identifica il sink vive nel padre e non viene ereditato, quindi
  non faceva nulla. Ora il sink viene prima cercato. Verificato uccidendo
  il padre con SIGKILL: prima il sink sopravviveva.

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

---

## 🟣 Percorsi che il codice dichiarava rotti  ✅ RISOLTI

Non facevano parte dell'analisi Ubuntu: erano difetti preesistenti che il
sorgente segnalava da sé, con un `raise` messo lì apposta al posto della
logica mancante.

### #11 — Un indice di device sbagliato faceva morire l'applicazione  ✅ `ee33dc84`

**Sintomo.** Con `-s`, digitando un indice fuori dall'elenco, l'applicazione
alzava `Exception: Internal error: Never worked; needs to be fixed.`

**Causa.** [`cast.py`](mkchromecast/cast.py), `Casting.input_device()`: il ramo
`except IndexError` chiamava in origine `self.select_device()`, un metodo mai
esistito (`select_device` è un flag booleano), e il refactor ci ha lasciato il
`raise` al suo posto. In più l'indice veniva scritto nel file pickle **prima**
di essere validato, quindi la scelta sbagliata sopravviveva alla sessione.

**Prova.** Contro la discovery reale, digitando `99`:

```console
$ printf '99\n1\n' | ... input_device()
Exception: Internal error: Never worked; needs to be fixed.
```

**Fix.** L'indice si risolve prima di essere registrato, e solo uno valido
arriva al pickle. Tutto ciò che non è un numero dentro l'intervallo dei device
elencati costa uno dei `SELECTION_ATTEMPTS` tentativi e un nuovo prompt;
esaurirli chiude l'applicazione con un messaggio invece che con un traceback.
Gli indici negativi vengono rifiutati anziché contare dalla fine.

L'EOF sul prompt si gestisce in `select_a_device()`, cioè dove si legge
davvero: il primo prompt lo fa [`bin/mkchromecast:153`](bin/mkchromecast#L153),
fuori da `input_device()`, quindi gestirlo solo nel ciclo di riprova lasciava
comunque il traceback con stdin chiuso. **Trovato dalla prova dal vivo, non
dai test unitari.**

**Verifica.**
```console
$ printf '99\n1\n' | ...          # indice sbagliato, poi buono
'99' is not one of the indexes listed above.
Casting to: Seminterrato            # pickle = 1

$ printf '99\nxx\n-1\n' | ...    # tre sbagliati
No device was selected.             # exit 1, nessun /tmp/mkchromecast.tmp

$ ... < /dev/null                   # stdin chiuso
No index was given: standard input is closed.   # exit 1
```

### #12 — La riconnessione del backend node poteva generare processi a catena  ✅ `36b71830`

**Sintomo.** Quando il server node moriva, il percorso di riconnessione alzava
`Internal error: Never worked; needs to be fixed.`

**Causa.** [`node.py`](mkchromecast/node.py) riavviava node chiamando
`stream_audio()`, che lancia una copia nuova di *questo stesso processo*: ogni
riavvio annidava un processo dentro il precedente, e un node che falliva
all'avvio trasformava la cosa in una catena senza fine. Il commento sopra il
`raise` diceva esattamente questo.

**Fix.** Il riavvio avviene sul posto — è lo stesso processo a rilanciare node
— quindi la ricorsione temuta dal commento sparisce, ed è limitato da
`NODE_RECONNECT_ATTEMPTS`. Un server che ha retto per
`NODE_HEALTHY_UPTIME_SECONDS` si riprende il tentativo speso: senza, una lunga
sessione con la tray consumerebbe il budget nell'arco di giorni e poi
smetterebbe di riconnettersi per sempre.

Al device si dice di leggere il nuovo server solo dopo che node è
sopravvissuto al periodo di grazia: puntarlo a un server morto all'avvio
produrrebbe solo silenzio. Il watchdog sul processo principale e il notifier
macOS sono usciti dal ciclo in `watch_until_exit()` e `notify_reconnecting()`;
`kill()` e `relaunch()`, che esistevano solo per il vecchio riavvio, sono
stati rimossi.

**Non verificato contro un server reale:** `webcast-osx-audio` è solo per
macOS e node non è fra i backend audio Linux. Il limite, la politica di
recasting e il recupero del budget sono coperti da test.

### #13 — `-vf` specificato due volte, e sottotitoli mai funzionanti su file non-mkv  ✅ `46bf7d75`

**Sintomo dichiarato.** Usando insieme `--subtitles` e `--resolution` su un
file non-mkv, ffmpeg riceveva `-vf` due volte e ne ignorava uno.

**Prova.** Con ffmpeg 7 sulla macchina di prova:

```console
$ ffmpeg -i sample.mp4 -vcodec libx264 -vf "subtitles=sub.srt" -vf "scale=1920x1080" out.mp4
$ ffprobe -show_entries stream=width,height out.mp4
1920,1080                        # scalato, sottotitoli spariti senza un avviso
```

**Fix.** I due filtri finiscono in un solo `-vf`, con la scala per prima così i
sottotitoli vengono disegnati alla risoluzione di uscita invece di essere
scalati insieme all'immagine.

**Due difetti emersi dalla stessa riga di comando.**

*I sottotitoli su file non-mkv non hanno mai funzionato.* La politica di
codifica sceglieva `-vcodec copy`, e ffmpeg rifiuta un filtergraph accanto a
uno stream copy:

```console
$ ffmpeg -i sample.mp4 -vcodec copy -vf "subtitles=sub.srt" out.mp4
Filtergraph 'subtitles=sub.srt' was specified, but codec copy was selected.
Filtering and streamcopy cannot be used together.
```
Ora la politica guarda se c'è qualcosa da filtrare, non solo la risoluzione.

*Il percorso del file sottotitoli finiva nel filtro senza escaping*, cosa che
conta di più ora che i filtri sono uniti da virgole: una virgola nel nome
chiudeva il filtro e ne apriva uno inesistente (`No such filter: 'ird
sub.srt'`). Il percorso attraversa tre parser prima di arrivare a libass, per
cui ogni carattere speciale vuole tre backslash; i livelli sono stati
determinati provando ffmpeg con nomi contenenti virgole, due punti, parentesi
quadre, apici e backslash.

**Verifica.** I comandi generati sono stati eseguiti davvero da ffmpeg —
sottotitoli da soli, risoluzione da sola, e insieme con un file chiamato
`we,ird: [it's] a sub.srt`: tutti e tre completano senza errori.

### #15 — `--control` rotto in ogni copia installata  ✅ `f160fb52`

**Sintomo.** Con `--control`, il primo tasto premuto alza
`ModuleNotFoundError: No module named 'mkchromecast.getch'`. Solo sulle copie
**installate**: dall'albero di lavoro funziona.

**Causa.** [`setup.py`](setup.py) dichiarava `packages=["mkchromecast"]`, che
**non** include i sottopacchetti: né il wheel né il `.deb` contenevano
`mkchromecast/getch/`, importato da
[`bin/mkchromecast`](bin/mkchromecast) in `block_until_exit()`.

Il `.deb` lo escludeva per di più di proposito, sulla base di una ricerca
sbagliata: `grep -r "getch" --include="*.py"` non può trovare
`bin/mkchromecast`, che non ha estensione.

**Prova.**
```console
$ cd /tmp && python3 -c "from mkchromecast.getch import getch"
ModuleNotFoundError: No module named 'mkchromecast.getch'
```

**Fix.** `packages=["mkchromecast", "mkchromecast.getch"]` e niente più
esclusione in [`packaging/build-deb.sh`](packaging/build-deb.sh). Verificato
importando `getch` dal `.deb` estratto, col python3 di sistema.

**Insieme, tre derive di `bin/mkchromecast`** rispetto ai moduli:
`--reset` e `--version` giravano fuori dal `try`, quindi un `pactl` assente
usciva come traceback mentre lo stesso errore altrove era una riga; il tasto
`a` stampava la lista device grezza, che da quando è fatta di dataclass
significa una fila di `AvailableDevice(...)`; e l'import di `typing` era
avanzato da dichiarazioni spostate nel corpo della classe.

### #16 — `pactl` presente ma irraggiungibile: traceback  ✅ `e124d828`

**Sintomo.** `mkchromecast --reset` da un contesto senza sessione audio (login
ssh, unità systemd) esce con
`subprocess.CalledProcessError: Command '['pactl', 'list', 'sinks']' returned
non-zero exit status 1`.

**Causa.** [`pulseaudio.py`](mkchromecast/pulseaudio.py), `_pactl()`:
`FileNotFoundError` diventava `PulseAudioNotAvailable`, ma un `pactl` che c'è e
non riesce a parlare col server no — pur essendo il caso che la docstring
dell'eccezione dichiarava già ("*not installed or cannot be reached*").

**Prova.**
```console
$ env -i PATH=/usr/bin:/bin pactl list sinks
Connection failure: Connection refused
```

**Fix.** `_pactl()` riconosce il fallimento di connessione — il messaggio è in
inglese qualunque sia il locale, perché `_PACTL_ENV` lo fissa — e lo riporta
come `PulseAudioNotAvailable`; idem per un `pactl` che non risponde entro il
timeout. Gli altri errori di comando restano `CalledProcessError`, per non
travestire da server irraggiungibile un fallimento che non lo è. Quattro test
nuovi in `tests/test_pulseaudio.py`.

**Trovato verificando l'installazione del `.deb`, non da un test.**

### #17 — L'icona della tray non seguiva il tema scuro  ✅ `59a5b788`

**Sintomo.** Con il desktop Ubuntu in tema scuro, l'icona nella barra
superiore è quasi invisibile: è nera su fondo trasparente.

**Causa.** [`systray.py`](mkchromecast/systray.py) sceglieva la variante
dell'icona da `config.colors`, una preferenza **manuale** con default
`black`. Le varianti bianche esistevano già da sempre
(`google_w.png`, `google_working_w.png`, `google_nodev_w.png`), ma nessuno le
selezionava se non aprendo le preferenze.

**Prova.** Media pesata sull'alfa del tratto, misurata con Qt:

| file | RGB del tratto |
|---|---|
| `google.png` | (0, 0, 0) — nero |
| `google_b.png` | (10, 158, 230) — azzurro |
| `google_w.png` | (254, 254, 254) — bianco |

e il desktop:
```console
$ gsettings get org.gnome.desktop.interface color-scheme
'prefer-dark'
```

**Fix.** Nuovo modulo [`theme.py`](mkchromecast/theme.py) che chiede al
desktop se è scuro: `color-scheme` di GNOME, poi il nome del tema GTK per le
sessioni che l'hanno lasciato a `default`, poi `GTK_THEME`; su macOS
`AppleInterfaceStyle`. Se nessuno risponde si resta sul nero, che è ciò che
l'icona era prima.

`colors` accetta ora il valore `auto`, che è il nuovo default ed è offerto
nelle preferenze; una scelta esplicita continua a vincere. Un timer da 10 s
ridisegna l'icona se il tema cambia mentre l'applicazione gira — il costo
della domanda è di 4 ms, misurati.

**Nota per chi aggiorna:** un file di configurazione già esistente contiene
`colors = black` e resta nero, perché non è distinguibile da una scelta
deliberata. Va messo a `auto` a mano o dalle preferenze.

La verifica GUI completa non è automatizzabile: la piattaforma Qt
`offscreen` non crea una tray di sistema (`QObject::connect: No such signal
QPlatformNativeInterface::systemTrayWindowChanged`). Sono coperti da test la
rilevazione del tema, la risoluzione della variante e il ridisegno al cambio
di tema.

### #18 — Nessuna icona nella griglia delle applicazioni  ✅ `4b8c388a`

**Sintomo.** In "Mostra applicazioni" di Ubuntu compare il nome
*Mkchromecast* senza icona.

**Causa.** [`mkchromecast.desktop`](mkchromecast.desktop) diceva
`Icon=/usr/share/pixmaps/mkchromecast.xpm`, un file che **nessun pacchetto
installa** — né quello Debian né il nostro:

```console
$ find /usr/share/pixmaps /usr/share/icons -iname "*mkchrome*"
$   # nulla
```

Inoltre un percorso assoluto è il modo sbagliato di nominare un'icona: vale
solo per quel file e quella dimensione.

**Fix.** L'entry ora dice `Icon=mkchromecast`, un nome di tema, e
`images/mkchromecast.png` (256×256, quadrata, tratto azzurro su fondo
trasparente, generata dalla variante `google_b`) viene installata in
`/usr/share/icons/hicolor/256x256/apps/` sia da `setup.py` sia da
[`packaging/build-deb.sh`](packaging/build-deb.sh). L'azzurro si legge sia su
fondo chiaro sia su scuro, a differenza del nero della tray.

**Prova.** Risoluzione via `Gtk.IconTheme` con `XDG_DATA_DIRS` puntato
sull'albero del pacchetto estratto:

```
richiesta  48px -> .../hicolor/256x256/apps/mkchromecast.png
richiesta 256px -> .../hicolor/256x256/apps/mkchromecast.png
```

`desktop-file-validate` passa. Quattro test in `tests/test_packaging.py`
verificano che l'icona nominata dall'entry esista, sia quadrata e sia
installata dove il tema la cerca.

### #19 — Scegliere un dispositivo chiudeva l'applicazione  ✅ `00fcb4c5`

**Sintomo.** Dalla tray: si avvia la scansione, compaiono i due dispositivi,
se ne sceglie uno e dopo circa un secondo l'applicazione sparisce. Nessuna
finestra di errore; la spiegazione resta nel journal.

**Causa.** Il controllo della porta introdotto con #1 alzava `SystemExit(1)`
([`stream_infra.py`](mkchromecast/stream_infra.py), `PipelineProcess.start`).
Per la CLI è corretto. Ma la tray ci arriva da uno slot Qt eseguito in un
thread worker, e **PyQt aborta il processo su qualunque eccezione che sfugge
da uno slot**: `SystemExit` è una `BaseException`, quindi non veniva
intercettata da nessuno dei gestori lungo il percorso.

**Prova.** Dal syslog dell'utente, con `shairport-sync` sulla 5000:

```
mkchromecast.desktop[6810]: Port 5000 is already in use by another program.
mkchromecast.desktop[6810]: Hint: retry with --port 5001, ...
mkchromecast.desktop[6810]: QObject::~QObject: Timers cannot be stopped from another thread
systemd[3232]: app-gnome-mkchromecast-6810.scope: Consumed 1.455s CPU time over 19.952s
```

Il meccanismo, isolato: uno slot che alza `SystemExit` in un `QThread` uccide
l'applicazione e produce la stessa riga `QObject::~QObject`, senza mai
arrivare al timer che avrebbe stampato "ancora viva".

**Fix.** Nuova `StreamServerError(RuntimeError)`, sullo stesso modello di
`PulseAudioNotAvailable` (#16): la CLI la aggiunge al gestore che già aveva e
esce 1 come prima; la tray la intercetta in `_play_cast_` e segna il
tentativo come fallito restando in piedi. I tre percorsi di errore della
tray, che ripetevano le stesse tre righe, passano da un unico `_fail()`.

Verificato sul percorso vero — `QThread` reale, `Player` reale, porta 5000
davvero occupata:

```console
SEGNALE RICEVUTO: _play_cast_ failed: Port 5000 is already in use by another
                  program. Retry with --port 5001, ...
APPLICAZIONE ANCORA VIVA
```

CLI invariata: stesso messaggio, `exit=1`, nessun sink residuo.

### #20 — Il motivo del fallimento non arrivava all'utente  ✅ `494f1c7e`

**Sintomo.** La notifica diceva `Streaming Process Failed. Try Again...`.
Riprovare non poteva funzionare: la porta sarebbe rimasta occupata.

**Causa.** [`systray.py`](mkchromecast/systray.py) distingueva solo successo
da fallimento; il motivo veniva stampato su stdout, che sotto un lanciatore
`.desktop` finisce nel journal.

**Fix.** Il motivo viaggia col segnale `pcastready` e finisce nella notifica.
Quando non se ne conosce uno resta il messaggio generico di prima.

### #21 — La porta non era raggiungibile dalla tray  ✅ `1332d261`

**Sintomo.** Corretto #19, la tray sopravvive ma su questa macchina non casta
comunque: la 5000 è occupata e dalla griglia delle applicazioni non c'è modo
di cambiarla.

**Causa.** La porta esisteva solo come argomento della riga di comando
(`args.port`), e la tray non ne ha una:
[`mkchromecast.desktop`](mkchromecast.desktop) lancia `mkchromecast -t` e
basta. Fra le preferenze non c'era una voce per la porta.

**Fix.** `port` diventa una chiave di configurazione come le altre
([`config.py`](mkchromecast/config.py)), con una voce **Streaming Port** nel
pannello delle preferenze, validata mentre si digita. Le tre sorgenti si
riconciliano in un punto solo, [`__init__.py`](mkchromecast/__init__.py),
perché da lì legge tutto il resto dell'applicazione:

| situazione | porta usata |
|---|---|
| `mkchromecast -n X` | 5001 (default) |
| `mkchromecast -n X -p 5100` | 5100 |
| `mkchromecast -t`, preferenze a 5055 | 5055 |
| `mkchromecast -t -p 5099`, preferenze a 5055 | 5099 |
| `-p 99999` | 5001, con avviso |

Un `--port` esplicito vince anche in modalità tray, altrimenti `-t -p 5001`
avrebbe smesso di funzionare proprio per chi lo stava usando come rimedio.

**Il default passa da 5000 a 5001.** La 5000 è occupata da `shairport-sync`
su Linux e da AirPlay Receiver su macOS abbastanza spesso da essere un
inciampo prevedibile, ed è anche il default del server di sviluppo di Flask.

Due difetti emersi mentre si lavorava qui, corretti insieme:

- **`html5-video-streamer.js` ignorava `--port`**: ascoltava su 5000 fisso
  mentre `cast.py` costruiva l'URL da `mkcc.port`, quindi il dispositivo
  chiedeva una porta su cui non c'era nessuno. È lo stesso difetto che
  `webcast.js` aveva e che era già stato corretto in `c0072fa6`. Verificato:
  `node html5-video-streamer.js film.mp4 5123` risponde `200` sulla 5123.
- **Il tasto "Reset Settings" non aveva mai funzionato**:
  [`preferences.py`](mkchromecast/preferences.py) chiamava
  `self.configurations.write_defaults()`, dove `self.configurations` non
  esiste (l'attributo è `self.config`) e `write_defaults` non esisteva su
  `Config`; la riga successiva usava `self.qcnotifations`, con un refuso.
  Il metodo alzava `AttributeError` alla prima riga. Ora `Config` ha un
  `write_defaults()` e il pulsante riporta tutto ai default, porta compresa.

### #22 — Il cursore del volume alzava `TypeError`  ✅ `b99716c8`

**Sintomo.** Dalla tray, la voce *Volume* non apre niente e nel journal
compare:

```
File "/usr/lib/python3/dist-packages/mkchromecast/systray.py", line 551, in volume_cast
    self.sl.setValue(round((self.cast.status.volume_level * self.maxvolset), 1))
TypeError: setValue(self, a0: int): argument 1 has unexpected type 'float'
```

**Causa.** `round(x, 1)` restituisce un `float` anche quando il risultato è
intero (`0.65 * 100` → `65.0`), e `QSlider.setValue` accetta solo `int`. La
riga è upstream e non è mai stata corretta; il `try` attorno intercetta solo
`AttributeError`, quindi il `TypeError` passava.

**Prova.** Contro un `QSlider` vero:

```console
round(x, 1)  -> 65.0     RIFIUTATO: setValue(self, a0: int): argument 1 has unexpected type 'float'
round(x)     -> 65       accettato, slider a 65
```

**Perché salta fuori solo adesso.** Il ramo si raggiunge solo quando
`self.cast` è davvero un `Chromecast`. Prima di `81bd771f` era il modulo
`cast` ribindato, e prima di #19 e #21 dalla tray non si arrivava a castare
su questa macchina: `self.cast.status` alzava `AttributeError`, che il `try`
intercettava, e il cursore partiva dal valore di ripiego. Il difetto è
vecchio, l'esposizione è nuova.

**Fix.** La conversione diventa `slider_value()`, una funzione di modulo che
restituisce un `int`, coperta da test — la si può verificare senza display,
mentre il resto del pannello no. Verificato anche sul percorso vero, con un
`QSlider` reale e un dispositivo al 65%: `cursore aperto, valore: 65 su 100`.

Il resto del percorso volume è stato controllato ed è sano: `set_volume` non
compare su `pychromecast.Chromecast` ma viene legato sull'istanza in
`__init__` (`self.set_volume = receiver_controller.set_volume`), quindi sia
`value_changed()` sia `Casting.volume_up()`/`volume_down()` funzionano.

### #23 — Uscire non usciva, e faceva partire una ricerca  ✅ `c667a206`

**Sintomo.** Cliccando *Quit* l'applicazione non si chiude e si mette a
cercare i dispositivi. Nel journal:

```
File "/usr/lib/python3/dist-packages/mkchromecast/systray.py", line 738, in exit_all
    self.stop_cast()
File "/usr/lib/python3/dist-packages/mkchromecast/systray.py", line 523, in stop_cast
    self.read_config()
AttributeError: 'menubar' object has no attribute 'read_config'
```

**Causa.** Un residuo del refactor della configurazione. `read_config()`
rileggeva il file per aggiornare `self.notifications`, `self.searchatlaunch` e
`self.colors`; il commit `377815b7` ha sostituito quegli attributi con
`self.config.*` e **ha cancellato il metodo lasciando in piedi la sua unica
chiamata**, dentro `stop_cast()`.

I due sintomi vengono entrambi da lì. `stop_cast()` chiama `search_cast()`
poche righe prima — ecco la ricerca — e poi muore sull'`AttributeError`,
quindi non torna mai al chiamante: `exit_all()` non arriva a
`self.app.quit()` e l'applicazione resta aperta.

**Perché salta fuori solo adesso.** Come #22, il corpo di `stop_cast()` gira
solo se `self.cast` non è `None`, oppure dopo uno stop o un fallimento. Prima
di #19 e #21, da questa macchina non si arrivava a castare e il tentativo
fallito uccideva l'applicazione prima.

**Fix.** La rilettura torna, nella forma attuale: `self.config.load_and_validate()`.
La `Config` della tray è in sola lettura, quindi rilegge senza riscrivere.

Uscendo non si cerca più: `exit_all()` alza `self.exiting`, e `stop_cast()`
salta il `search_cast()`. Fermare dal menù continua a rinfrescare l'elenco.
Il flag è un attributo e non un parametro di `stop_cast()` di proposito: il
metodo è collegato a `StopCastAction.triggered`, che passa il proprio
`checked` a qualunque slot accetti un argomento, e avrebbe disattivato in
silenzio la ricerca anche quando serve.

**Verifica.** Quattro test in `tests/test_systray.py` sul metodo vero:
rilegge la configurazione, cerca fermando dal menù, non cerca uscendo, e
`exit_all()` arriva a `app.quit()`.

Cercati anche gli altri residui dello stesso tipo, percorrendo l'AST di
`systray.py`, `preferences.py`, `tray_threading.py` e `cast.py` per ogni
`self.x()` che non sia né un metodo né un attributo assegnato. L'unico
rimasto è `_get_chromecast()` dentro `_DisabledSonosCasting`
([`cast.py:692`](mkchromecast/cast.py#L692)), cioè nel codice Sonos già
disabilitato e in backlog.

### #24 — Il pacchetto non era in condizione di essere distribuito  ✅ `b46bb5da`

**Sintomo.** `make deb` produceva un `.deb` valido e installabile, ma non
consegnabile a nessun altro: nessun pacchetto sorgente da ricostruire, e un
manutentore a cui non si può scrivere.

**Causa.** Tre cose distinte.

1. `Maintainer: Muammar El Khatib <http://muammar.me/>` — un URL dove va un
   indirizzo, quindi non un campo `Maintainer` valido. Veniva da
   [`setup.py`](setup.py), che aveva lo stesso errore in `author_email`. E
   comunque il manutentore è chi costruisce e distribuisce il pacchetto, non
   l'autore upstream.
2. Nessuna directory `debian/`: il pacchetto si poteva costruire solo con
   `packaging/build-deb.sh`, su questa macchina. Chi lo riceve non può
   ricostruirlo, ispezionarlo né correggerlo.
3. **`archive/` contiene codice di terzi senza licenza.** Il `LICENSE` del
   progetto dice che i file in `archive` e `notifier` hanno licenze proprie,
   ma dentro `archive/audiodevice-src.zip` c'è:

   ```
   //  Copyright 2006 Rogue Amoeba Software, LLC. All rights reserved.
   ```

   Nessuna concessione. E `notifier/LICENSE` non contiene un testo di
   licenza: rimanda a un URL. Entrambe le directory sono solo-macOS e non
   vengono installate, ma sarebbero finite in qualunque tarball sorgente.

**Fix.** Una `debian/` canonica: `control`, `rules` (`dh` con `pybuild` e
`dh-python`), `changelog`, `copyright` in formato DEP-5, `source/format`
`3.0 (native)`, `source/options`, `docs`, `clean`. `setup.py` era già adatto
a pybuild — pacchetti, script e `data_files` finiscono dove il pacchetto
Debian li vuole — quindi `rules` è di quattro righe più due override.

Il manutentore è `saulusprime <pierno.paolo@gmail.com>`, corretto anche in
`setup.py`. Il `copyright` DEP-5 dà un paragrafo a `mkchromecast/getch`
(py-getch, Joe Esposito) e uno a `nodejs/`. `archive/` e `notifier/` restano
nel repo ma fuori dal pacchetto sorgente, con il motivo scritto in
[`debian/source/options`](debian/source/options).

Due dettagli che non erano scontati:

- **Le esclusioni di `tar-ignore` sostituiscono quelle predefinite**, non si
  aggiungono. Senza nominare `.git` esplicitamente, il tarball sorgente lo
  includeva: **352 MB** invece di 11.
- **pybuild esegue la suite da una copia del solo pacchetto**, dove la
  `.desktop` e le icone non ci sono, e quattro test di `test_packaging.py`
  le cercano relativamente al repo. `override_dh_auto_test` li fa girare
  nell'albero sorgente, come fa `make check`, invece di indebolirli.

**Verifica.**

```console
$ make lint          # lintian -i --pedantic
(nessuna segnalazione)

$ dpkg-source -x ../mkchromecast_0.4.4.dsc /tmp/src
$ cd /tmp/src && dpkg-buildpackage -us -uc -b
Ran 114 tests ... OK
dpkg-deb: generazione del pacchetto "mkchromecast" in "../mkchromecast_0.4.4_all.deb"

$ md5sum <i due .deb> | awk '{print $1}' | uniq -c
      2 8f177b149233dd7b01a88898e386d4e9
```

Il pacchetto ricostruito dal sorgente è **identico byte per byte** a quello
costruito dall'albero di lavoro.

### #14 — Il supporto Sonos era pubblicizzato ma assente  ✅ `7b38c65d`

**Sintomo.** README, man page, voce `.desktop` e descrizione del bundle macOS
offrivano il cast verso gli speaker Sonos; il README spiegava anche come
abilitarlo installando `soco`.

**Causa.** Il codice che pilotava i Sonos è irraggiungibile da un refactor in
poi: nessuno istanzia `_DisabledSonosCasting`, e il suo `play_cast()` alza
prima di arrivare allo speaker.

**Fix (scelta: allineare la documentazione).** Ora dicono ciò che è vero. La
sezione Sonos del README spiega dov'è finito il codice e che il ripristino sta
nel backlog, il known issue sui codec Sonos punta lì, e la docstring della
classe dice apertamente che nessuno la istanzia. `soco` resta una dipendenza,
tenuta per chi ripristinerà la classe.

---


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

---

## Riepilogo dei commit

| | Problema | Commit |
|---|---|---|
| #1 | Fallimento del bind di Flask non rilevato | `d059f9d9` |
| #2 | Crash `RequestFailed` con pychromecast 14 | `6d97a3de` |
| #3 | `PyGObject` non installabile su Ubuntu 26.04 | `80ffc734` |
| #4 | `--reset` inefficace in locale non inglese | `7dc8ec28` |
| #5 | `findall` con il flag passato come `pos` | `7dc8ec28` |
| #6 | Sample rate incoerente fra `parec` e l'encoder | `53c8b7ee` |
| #7 | Output perso in pipe, exit code sempre 137 | `6fcb4454` |
| #8 | `UnboundLocalError` in `node.py`; backend da config non validato | `c0072fa6` |
| #9 | Node non trovato su Ubuntu; `--port` ignorato | `c0072fa6` |
| #10 | `Chromecast.device` rimosso in pychromecast 14 | `c0072fa6` |
| P3 | `pactl` mancante, `global cast`, updater | `81bd771f` |
| P3 | Icone legate alla CWD, rumore di config | `68b4a0d8` |
| P3 | `pkill` fuori dal nostro albero, `backend.path` | `536f7d73` |
| P3 | `setup.py`, `netifaces` → `ifaddr` | `9004388b` |
| P3 | Singleton `Mkchromecast`, effetti all'import di `audio.py` | `a9936424` |
| — | Dipendenze di sistema nel README | `54a9598b` |
| #11 | Indice di device sbagliato: niente riselezione | `ee33dc84` |
| #12 | Riconnessione node a catena di processi | `36b71830` |
| #13 | `-vf` doppio; sottotitoli mai funzionanti su non-mkv | `46bf7d75` |
| #14 | Sonos pubblicizzato ma assente | `7b38c65d` |
| #15 | `getch` non impacchettato: `--control` rotto una volta installato | `f160fb52` |
| #16 | `pactl` irraggiungibile: traceback invece di un messaggio | `e124d828` |
| #17 | Icona della tray nera su tema scuro | `59a5b788` |
| #18 | Nessuna icona nella griglia delle applicazioni | `4b8c388a` |
| #19 | La tray moriva quando la porta era occupata | `00fcb4c5` |
| #20 | La notifica non diceva perché il cast era fallito | `494f1c7e` |
| #21 | Porta non configurabile dalla tray; default a 5001 | `1332d261` |
| #22 | `TypeError` aprendo il cursore del volume | `b99716c8` |
| #23 | Quit non usciva e faceva partire una ricerca | `c667a206` |
| #24 | Pacchetto non distribuibile: manutentore, sorgente, licenze | `b46bb5da` |

---

## Verifiche di regressione

> **Attenzione a quale eseguibile si lancia.** `mkchromecast` sul PATH è
> `/usr/bin/mkchromecast`, che appartiene a un pacchetto e **non** all'albero
> di lavoro. Su questa macchina era il pacchetto apt `0.3.9~git20200902+db2964a`
> del 2020, che non conteneva niente di quanto è documentato qui; dal 21 agosto
> 2026 è sostituito dai pacchetti costruiti con `make deb`, che portano una
> revisione `Nlocal1`. Quale sia quello installato in un dato momento va
> controllato, non dato per scontato:
>
> ```bash
> dpkg -l mkchromecast                                   # quale versione
> cd /tmp && python3 -c "import mkchromecast.cast as c; print(c.__file__)"
> ```
>
> In ogni caso le verifiche di una modifica non ancora impacchettata vanno
> fatte sull'albero di lavoro, col python del venv (quello di sistema segue le
> versioni della distribuzione, non `requirements.txt`):
>
> ```bash
> MKC=".venv/bin/python bin/mkchromecast"
> ```
>
> `bin/mkchromecast` si mette da solo la radice del repo in `sys.path`, quindi
> la forma con percorsi assoluti funziona da qualunque directory.

```bash
# 1. i test devono restare verdi (33 prima dei fix, 114 dopo)
python -m unittest discover -s tests -v

# 2. discovery: output visibile anche in pipe, exit code 0
$MKC --discover | cat ; echo "exit=$?"

# 3. reset: deve funzionare nel locale dell'utente, non solo in C
pactl load-module module-null-sink sink_name=Mkchromecast
$MKC --reset
pactl list sinks short | grep -i mkchrome    # deve essere vuoto

# 4. porta occupata: messaggio chiaro, niente cast a vuoto
$MKC -p 5000 -n <device>                     # con shairport-sync attivo

# 5. coerenza del sample rate
parec -v --format=s16le --rate=48000 -d Mkchromecast.monitor   # deve dire 48000Hz

# 6. selezione del device: un indice sbagliato richiede, non uccide
$MKC -s --discover                           # digita 99, poi un indice valido

# 7. sottotitoli su file non-mkv, con e senza --resolution
$MKC --video -i film.mp4 --subtitles sub.srt --resolution 720p

# 8. la porta: default, argomento esplicito, preferenza della tray
$MKC -n <device>                             # deve dire 5001
$MKC -t                                      # Preferences -> Streaming Port
$MKC -t -p 5099                              # l'esplicito vince sulla preferenza
```

### Prova completa: cast audio reale

Il percorso intero, dal sink al ricevitore, provato il 21 agosto 2026 verso il
Sony TA-AN1000:

```console
$ .venv/bin/python bin/mkchromecast -n Seminterrato -p 5001
Creating Pulseaudio Sink...
Starting Local Streaming Server
Selected backend: BackendInfo(name='parec', path='/usr/bin/parec')
Selected audio codec: mp3
Using bitrate: 192
Using sample rate: 44100Hz
 * Running on http://192.168.1.192:5001
[Done]

Status of device  Seminterrato
CastStatus(..., app_id=None, session_id=None, status_text='', ...)

The IP of Seminterrato is: 192.168.1.126
Using media type: audio/mpeg
192.168.1.126 - - [21/Aug/2026 21:06:11] "GET /stream HTTP/1.1" 200 -

Cast media controller status
CastStatus(..., app_id='CC1AD845', display_name='Default Media Receiver',
           session_id='54d1e1c1-...', status_text='Trasmissione: Mkchromecast v0.3.9', ...)
```

Cosa conferma, riga per riga:

| Riga | Conferma |
|---|---|
| `Running on ...:5001` seguito da `[Done]` | #1: il controllo della porta e l'attesa di readiness passano; con la 5000 occupata si sarebbe fermato con un errore invece di castare a vuoto |
| `app_id=None` → `app_id='CC1AD845'` con `session_id` | #2: `block_until_active()` fa il suo lavoro. Con il codice originale qui usciva `RequestFailed: Failed to execute play` |
| `GET /stream HTTP/1.1" 200` dal device | Il ricevitore apre davvero lo stream, non si limita ad accettare il comando |
| `BackendInfo(name='parec', path='/usr/bin/parec')` | `536f7d73`: il backend è risolto sul PATH, non da percorsi fissi |
| Ogni riga di impostazioni stampata **una volta sola** | `a9936424`: prima del passaggio a `forkserver` comparivano doppie, perché il processo di streaming re-importava `audio.py` |

Il ritardo di mp3 su questo percorso resta quello noto (fino a ~8 s). Ora che
il sample rate arriva davvero anche a `parec` (#6), `-c flac --sample-rate
48000` è un'alternativa che prima veniva ignorata in silenzio.
