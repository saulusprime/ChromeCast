* Mkchromecast (0.4.4), 2026-08-22 — fork saulusprime/ChromeCast

    Packaging, so that the .deb can be handed to somebody else.

    - There is a `debian/` directory, so the package builds with
      `dpkg-buildpackage` and comes with a source package anyone who receives
      it can rebuild. `make dist` builds it, `make lint` checks it; `make deb`
      still builds the quick dpkg-deb package that needs no extra tools.
    - The Maintainer field holds an address that works. It held an upstream
      name with a URL where the address belongs, which came from `setup.py`
      and is fixed there too.
    - The copyright file follows DEP-5 and gives py-getch and the nodejs
      streamer their own paragraphs.
    - The source package leaves out `archive/` and `notifier/`. They are
      macOS-only and neither is installed, but they carry third-party code
      whose licence is stated only by reference, or -- for audiodevice, which
      says "Copyright 2006 Rogue Amoeba Software, LLC. All rights reserved."
      -- not at all.

* Mkchromecast (0.4.3), 2026-08-22 — fork saulusprime/ChromeCast

    - Quit quits again. It raised AttributeError halfway through tearing the
      cast down, on a method the config refactor had deleted while leaving its
      only caller behind, so the application stayed open.  Stopping a cast
      went through the same line.
    - Quitting no longer starts a device search.  Stopping refreshes the list,
      which made sense from the menu and not on the way out.

* Mkchromecast (0.4.2), 2026-08-22 — fork saulusprime/ChromeCast

    - The volume control opens again. It raised `TypeError: setValue(self,
      a0: int): argument 1 has unexpected type 'float'`, because `round(x, 1)`
      returns a float even when the result is whole and Qt sliders take ints.
      The line is old; it only became reachable once casting from the tray
      worked, in 0.4.1.

* Mkchromecast (0.4.1), 2026-08-22 — fork saulusprime/ChromeCast

    Two problems found by using the tray on the desktop, both documented in
    `AS-IS.md` with symptom, cause, evidence collected and fix.

    - Choosing a device no longer closes the application. When the streaming
      port was already taken, the tray died about a second later and the
      reason was left in the journal: the port check raised SystemExit from
      inside a Qt worker slot, and PyQt aborts the process on anything that
      escapes one. The attempt is now reported and the tray stays up.
    - A failed attempt says what went wrong. The notification read "Streaming
      Process Failed. Try Again...", which is bad advice when the answer is
      that another program holds the port; the reason now travels with the
      signal and is shown instead.
    - The streaming port is a preference. The tray has no command line to take
      one from, so a busy port could only be worked around by editing the
      `.desktop` file. **Streaming Port** now sits in Preferences, and an
      explicit `--port` still wins over it for that run.
    - The default port moves from 5000 to 5001. 5000 is held by
      `shairport-sync` on Linux and by AirPlay Receiver on macOS often enough
      that the first cast of the day tended to land on somebody else's server.
    - The node video backend honours `--port`. It served on a hardcoded 5000
      while the device was told to read from the chosen port, the same defect
      `webcast.js` had.
    - "Reset Settings" works. It called a method on an attribute that does not
      exist, so the button had never done anything but raise.

* Mkchromecast (0.4.0), 2026-08-22 — fork saulusprime/ChromeCast

    Fixes found by running the code on Ubuntu 26.04 with Python 3.14,
    PipeWire and pychromecast 14. Every entry is documented in `AS-IS.md`
    with symptom, cause, evidence collected and fix; `TO-DO.md` holds what
    is left.

    The version moves to 0.4.0 rather than 0.3.9 because 0.3.9 was never
    released and because behaviour changed in ways a user notices: exit
    codes mean something, a bad device index asks again instead of raising,
    `--sample-rate` is honoured by the default backend, and Sonos is
    documented as unavailable. The 0.3.9 entries below are upstream work
    that this release carries.

    - Flask failing to bind is detected instead of leaving the device
      reading from a port nothing serves.
    - Casting works with pychromecast 14: the media session is awaited, an
      app already running on the device is closed first, and a refused play
      is reported rather than raised as a traceback.
    - `--reset` removes the sinks in any locale, not only in English, by
      reading `pactl --format=json` with `LC_ALL=C`.
    - `--sample-rate` reaches `parec` as well as the encoder, so it is no
      longer ignored in silence; `-c opus` is no longer 8.8% fast.
    - Output survives being piped and the exit code means something: no more
      SIGKILL on self, no more 137 for everything.
    - The node backend runs at all (it raised `UnboundLocalError`), node is
      found on the PATH, and `--port` is honoured.
    - A device index that is not on the list asks again instead of raising.
    - A dead node server is restarted in place, a bounded number of times,
      rather than by spawning a copy of the process.
    - `--subtitles` and `--resolution` share one `-vf`; subtitles on non-mkv
      files work at all for the first time, and their path is escaped.
    - Sonos is documented as unavailable rather than advertised: the code
      that drove the speakers has been unreachable for some time.
    - `pactl` missing is an error, sinks are created and removed reliably,
      tray icons no longer depend on the working directory, `ffmpeg`
      processes that are not ours are left alone, `setup.py` declares its
      dependencies, and `netifaces` gives way to `ifaddr`.
    - The `Makefile` gained Linux targets: `check`, `wheel`, `deb`,
      `binary` (PyInstaller), `install`, `develop`, `run`, `clean-build`.
      `make` no longer edits the source.
    - `--control` works on installed copies: the getch subpackage was
      never shipped, so any control key raised ModuleNotFoundError.
    - `pactl` that cannot reach the audio server is reported in one line
      rather than as a traceback.
    - The tray icon follows the desktop's light/dark setting instead of
      staying black on a dark panel, where it was very nearly invisible.
      The white artwork already shipped; choosing it was a manual
      preference. `Icon Colors` gains an `auto` value, now the default.
    - The application shows an icon in the desktop's application grid.
      The desktop entry pointed at /usr/share/pixmaps/mkchromecast.xpm,
      which no package installs; it now names the icon "mkchromecast" and
      a square 256x256 icon is installed where icon themes look.
    - Test suite from 33 to 87 cases.

* Mkchromecast (0.3.9) **unreleased**

    - New flag `--loop` to loop video indefinitely while streaming. Closes
      #113.
    - New flag `--mtype` to specify media type. Closes #128.
    - Modified how pyqt is used to accomodate pyqt 5.5, which is what comes in
      Ubuntu 16.04 LTS
    - Removed the -max_muxing_queue_size ffmpeg flag because it's not supported
      in ffmpeg 2.8.11.
    - Screencast with audio.
    - 10bits mkv files are now encoded to 8bits. This fixes #156.
    - node streaming updated to work with `node v9.8.0`.
    - Improved pause/resume when casting videos. Closes #97.
    - Added support for Fedora packages. Thanks to @leamas.
    - setup.py Linux support. Closes #173. Thanks to @leamas.
    - `nodejs` content is dropped. We provide now `package.json` and
      `package-lock.json` files. This will considerably reduce repository size.
      Thanks to @leamas.
    - Using the `--youtube` flag works for audio-only streaming.
    - Fixed inconsistency when node is not installed.
    - Refactored IP assignment. Thanks to Rick Brown.
    - You can attach devices to a running streaming audio session
      (experimental).
    -  Move from SoundFlower to BlackHole for macOS. Closes #289.

* mkchromecast (0.3.8.1) **2017/12/24**

    - A bug when no devices where found has been fixed in this release.

* mkchromecast (0.3.8) **2017/12/23**

    - Improved stability.
    - The macOS bundle is now renamed with capital M, and will not be showing
      in the dock.
    - Chunk size changed from 1024 to 64. Added two more variables that
      decreases the delay considerably.
    - Improved ffmpeg commands for pulseaudio part of the code.
    - node streaming updated to work with `node v9.3.0`.
    - Manpage is now shipped in main branches.
    - TypeError caused by a print statement for Soco devices has been fixed.
      Closes #80.
    - Added Opus codec support.
    - It is now possible to screencast using mkchromecast.
    - Using the `--youtube` flag works with all supported websites by youtube-dl.
    - Correct signal handling using the `signal` module. PR #87 by @Foxboron.
    - Renamed `--reconnect` to `--hijack`. Closes #25.
    - New flag `tries` to to limit the number of tries to connect to
      a chromecast. Closes #54.
    - Allow custom server port with ffmpeg or avconv. Related to #122.
    - Error with "width not divisible by 2 (853x480)". Closes issue #119.
    - The `segment_time` flag has been fixed. Closes issue #71.
    - New flag `command` for setting a custom ffmpeg command. Closes issue
      #109.

* mkchromecast (0.3.7.1) **2017/05/21**

    - macOS bundle built in Yosemite to add more compatibility.
    - Bumped version to match debian official release.

* mkchromecast (0.3.7) **2017/05/20**

    - node streaming updated to work with `node v7.10.0`.
    - Added ALSA device configuration in preferences pane.
    - Improved systray stability, and usability.
    - gstreamer support for capturing audio.
    - Fixed problem related to setting `ogg` and `aac` bitrate. Closes #21.
    - A `--segment-time` option added to modify the segment time when using
      ffmpeg.
    - A `--reconnect` option that monitors if mkchromecast has disconnected
      from google cast, and tries to reconnect.
      Closes [#25](https://github.com/muammar/mkchromecast/issues/25).
    - ALSA device can be set from systray.
    - Add support for newer `pychromecast` versions.
      Closes [#32](https://github.com/muammar/mkchromecast/pull/32).
    - Making ping code python 3 compatible. Closes:
      [#35](https://github.com/muammar/mkchromecast/pull/35).
    - Fixed problem when having various Google cast devices. Closes
      [#50](https://github.com/muammar/mkchromecast/issues/50)
    - Added support to 192000Hz sampling rate support (Closes:
      [#39](https://github.com/muammar/mkchromecast/issues/39)).
    - Fixed a minimal problem with size of preferences pane.
    - Video support.
    - node is a supported backend for streaming video.
    - Added Sonos speakers support.
    - FLAC codec supports bitrate.

* mkchromecast (0.3.6) **released**: 2016/09/19

    - The node streaming has been updated to work with `node v6.6.0`.
    - `Ctrl-C` now raises `KeyboardInterrupt` when using `--volume` option from
      console.
    - Improvements under the hood.
    - Now mkchromecast does not need pulseaudio to cast!.
    - You can play from stream using the `--source-url` flag.
    - `-d` option has been enable to discover available Google cast devices.
    - `--host` flag allows users to manually enter the local ip. Closes
      [#17](https://github.com/muammar/mkchromecast/issues/17).
    - `-n` flag allows users to pass the name of their cast devices.

* mkchromecast (0.3.5) **released**: 2016/08/26

    - Added close button for preferences pane. Closes
      [#13](https://github.com/muammar/mkchromecast/issues/13)
    - Improvements for cases where there are virtual network interfaces
      present.
    - Dropped `-re` flag from ffmpeg and avconv commands.
    - Renamed `ffmpeg.py` to `audio.py`.

* mkchromecast (0.3.4) **released**: 2016/08/19

    - New white icons.
    - Added 96000Hz sampling rate support for `ffmpeg` and `avconv` backends.
      Closes [#11](https://github.com/muammar/mkchromecast/issues/11).
    - Fixed 48000Hz sample rate case.
    - The node streaming has been updated to work with `node v6.4.0`.

* mkchromecast (0.3.3) **released**: 2016/08/16

    - Improved MultiRoom support. Closes
      [#8](https://github.com/muammar/mkchromecast/issues/8).

* mkchromecast (0.3.2) **released**: 2016/06/15

    - Improvements for cases where chromecasts have non-ascii characters in
      their names. Closes
      [#7](https://github.com/muammar/mkchromecast/issues/7).

* mkchromecast (0.3.1) **released**: 2016/08/12

    - Improved Preferences window.
    - The node streaming has been updated to work with `node v6.3.1`.
    - Improvements in pulseaudio.py for preventing subprocess.Popen from
      displaying output.
    - Improvements in `Check For Updates` method.
    - Added new option `--chunk-size` to control chunk's size of flask server
      when streaming using `ffmpeg` or `avconv`.

* mkchromecast (0.3.0) **released**: 2016/07/12

    - Youtube URLs can be played piping the audio using `youtube-dl`.
    - New method for discovering local IP in macOS. This will improve the
      stability of the system tray application. Closes
      [#5](https://github.com/muammar/mkchromecast/issues/5).
    - Now it is possible to select a different color for the system tray icon.
      This is useful when using dark themes.
    - The node streaming has been updated to work with `node v6.3.0`.
    - Improved stability when using system tray icon.
    - New method in preferences window to reset to default configurations.
      Closes [#6](https://github.com/muammar/mkchromecast/issues/6).

* mkchromecast (0.2.9.1) **released**: 2016/06/29

    - Fixing `stop` segfault.

* mkchromecast (0.2.9) **released**: 2016/06/29

    - Improved stability when using system tray icon.
    - New `search at launch` option. When enabled, the system tray search for
      available Google cast devices at launch time.
    - The node streaming server has been updated to work with `node v6.2.2`.

* mkchromecast (0.2.8) **released**: 2016/06/22

    - Preferences and volume windows always on top.
    - The node streaming has been updated to work with v6.2.1. This improves
      stability for macOS users when streaming with node.
    - It is now possible to check for updates using the system tray icon.
    - Scale factor added for retina resolutions.

* mkchromecast (0.2.7) **released**: 2016/06/16

    - Volume now set to max/40 instead of max/10. I have remarked that changing
      volume directly in the chromecast is more stable and faster than doing it
      from the streaming part, e.g. pavucontrol, or soundflower.
    - General improvements in system tray's behavior.
    - An error when setting volume to maximum has been fixed.
    - Now the muted time when launching a cast session is reduced. This is
      possible given that Soundflower changes input/output devices
      automatically. Linux users have to select a sink in pavucontrol.
    - Change from `Mac OS X` to  `macOS`.

* mkchromecast (0.2.6) **released**: 2016/06/08

    - Volume now set to max/20 instead of max/10.
    - This release lets Linux users cast using  `parec` with external libraries
      instead of `ffmpeg` or `avconv`.
    - The program does not import any PyQt5 module when launched without the
      system tray.
    - A deb package is now provided in this release.
    - The system tray will retry stopping the google cast before closing
      abruptly.
    - The Mac OS X application now supports models below the year 2010. See
      [#4](https://github.com/muammar/mkchromecast/issues/4).

* mkchromecast (0.2.5) **released**: 2016/05/25

    - This release fixes a problem with the system tray menu failing to read
      configuration files when changing from lossless to lossy audio coding
      formats.

* mkchromecast (0.2.4) **released**: 2016/05/21

    - This release fixes the system tray menu for Linux.
    - Now avconv is supported.
    - Pass the `--update` option to update the repository.
    - It is now possible to control the Google cast device volume from the
      systray.
    - You can reboot the Google cast devices from the systray.
    - There is a Preferences window to control `backends`, `bitrates`, `sample
      rates`, `audio coding formats` and `notifications`.

* mkchromecast (0.2.3.1) **released**: 2016/05/08

    - This release fixes the Signal 9 passed by error in the Stand-alone
      application.

* mkchromecast (0.2.3) **released**: 2016/05/08

    - The code has been partially refactored to ease maintenance.
    - Printed messages have been improved.
    - Stand-alone application for Mac OS X is released. It only works for the
      `node` backend.

* mkchromecast (0.2.2) **released**: 2016/05/03

    - Fixed error with Python2 when importing threading module.

* mkchromecast (0.2.1) **released**: 2016/05/02

    - Method for monitoring `ffmpeg` backend. This update is useful for those
      who use the system tray menu.

* mkchromecast (0.2.0.2) **released**: 2016/05/01

    - Fixed wav for Linux.

* mkchromecast (0.2.0.1) **released**: 2016/05/01

    - Catching some minimal errors.

* mkchromecast (0.2.0) **released**: 2016/05/01

    - Linux support.
    - Linux only plays with ffmpeg.
    - Now by default log level for `ffmpeg` backend is set to minimum.

* mkchromecast (0.1.9.1) **released**: 2016/04/27

    - Fixed node bug introduced in f635c5d66649767a031ac560d7c32ba6bffe33fe.

* mkchromecast (0.1.9) **released**: 2016/04/25

    - Play headless youtube URL.
    - Now you can control volume up and down from mkchromecast. So, no need
      of using the Android app for this anymore.

* mkchromecast (0.1.8.1) **released**: 2016/04/21

    - Set maximum bitrates and sample rates values for `node`.

* mkchromecast (0.1.8) **released**: 2016/04/21

    - Set maximum bitrates and sample rates values for both backends.
    - New icon when no google cast devices are found.
    - `streaming.py` was renamed to `node.py`.
    - Tested stability: 3hrs streaming at 320k with the `ffmpeg` backend.

* mkchromecast (0.1.7) **released**: 2016/04/18

    - The bitrate and sample rates can be modified in both node and ffmpeg.
      These options are useful when you router is not very powerful.
    - node_modules have been updated.
    - An error preventing launching without options has been fixed.
    - If PyQt5 is not present in the system, mkchromecast does not try to load
      it.

* mkchromecast (0.1.6) **released**: 2016/04/16

    - ffmpeg is now a supported backend. You can check how to use this backend
      by consulting `python mkchromecast.py -h`.
    - The following codecs are supported: 'mp3', 'ogg', 'aac', 'wav', 'flac'.
    - Improved screen messages.
    - Date format in changelog has been changed.

* mkchromecast (0.1.5) **released**: Wed Apr 13 18:08:44 2016 +0200

    This version has the following improvements:

    - If the application fails, the process that ensures streaming with node will
    kill all streaming servers created by mkchromecast.
    - Now there is a systray menu that you can launch as follows:
    `python mkchromecast.py -t`.

    - To use it, you need to install PyQt5. In homebrew you can do it as
    follows: `brew install pyqt5 --with-python`. You can use the package
    manager of your preference.
    - In a future release, a standalone application will be provided.

* mkchromecast (0.1.4) **released**: Mon Mar 28 19:00:28 2016 +0200

    - Now you can pass arguments to mkchromecast. For more information:
    `python mkchromecast -h`.
    - In this version you can choose devices from a list using:
    `python mkchromecast -s`.
    - Some improvements to the messages printed on screen.

* mkchromecast (0.1.3) **released**: Sun Mar 27 16:17:11 2016 +0200

    - Updated requirements.txt.
    - Now some help can be shown.
    - The code is now licensed under MIT. I think this license is simpler.

* mkchromecast (0.1.2) **released**: Sat Mar 26 18:49:18 2016 +0100

    This new revision has the following improvements:

    - mkchromecast has been ported to work with Python3. This is also possible
    because pychromecast works as well. The nodejs binary has been recompiled,
    and node_modules have been updated.  The program seems to be more stable.

* mkchromecast (0.1.1) **released**: Fri Mar 25 23:59:12 2016 +0100

    - In this new version multithreading is dropped in favor of
     multiprocessing. This is to reconnect the streaming server easily. Killing
     processes is easier than killing threading it seems.

    I strongly encourage you to upgrade to this version.

* mkchromecast (0.1.0) **released**: Fri Mar 25 13:21:12 2016 +0100

    - In this beta release, the program casts to the first google cast found in
      the list. If the node streaming server fails, the program reconnects.
