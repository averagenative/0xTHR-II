# Changelog

## 1.0.3 (2026-10-07)

- Fixes the amp going silent over USB, with "Timed out waiting for the amp to answer" on every change. A THR30II Wireless stops answering over USB soon after its Bluetooth link comes up, and stays silent until it's turned off and on, even after the link drops. BlueZ reconnects a paired amp by itself, so whenever the app or the command-line tool uses USB, it now disconnects the amp over Bluetooth and marks it untrusted, which stops BlueZ reconnecting it. **Connect over Bluetooth**, or starting the app without the USB cable, still connects it over Bluetooth.
- If the amp stops answering anyway, the app disconnects after two missed answers in a row and asks you to turn the amp off and on, instead of timing out on every change.
- If the amp stopped answering while the app read its settings right after connecting, the app stopped trying to reconnect until it was restarted. It now keeps trying.

## 1.0.2 (2026-10-04)

- The level meter works in the standalone AppImage. The PipeWire plugin bundled from Debian 13 lacks the `on-disconnect` setting the meter asked for, so the meter never started; it now sets that only when the plugin has it.

## 1.0.1 (2026-10-04)

- Standalone AppImage: `0xTHR-II-1.0.1-x86_64.AppImage` bundles Python 3.13, GTK 4, libadwaita, and GStreamer, so it runs without installing anything on any x86_64 desktop with glibc 2.41 or later (Fedora 42, Ubuntu 25.04, Debian 13, or later). `--install` adds it to the app grid with its icon; `--uninstall` removes that; `cli` runs the command-line tool.
- If GStreamer or its PipeWire plugin is missing (wheel or source installs), the app starts without the level meter instead of failing.
- `thr2 paths` shows where settings, presets, and caches are stored, and the app's Console lists them at startup.
- Your presets folder follows the desktop's Music folder, including localized names.
- With the amp off, the app retries Bluetooth every 5 to 30 seconds instead of every 2 seconds. USB is still checked every 2 seconds.
- `make release` builds the wheel, source archive, and AppImage, and publishes a GitHub release with checksums. `packaging/test-standalone.sh` checks the AppImage in a bare container.

## 1.0.0 (2026-10-04)

First release. Tested on a THR30II Wireless with firmware 1.40.0a on Fedora 44.

### Amp control

- USB MIDI and Bluetooth LE transports. The app prefers USB and otherwise connects a paired THR-II Wireless over Bluetooth.
- Unlocks MIDI control with the firmware-specific key and downloads the amp's symbol table, cached per firmware.
- Reads and changes the amp model, cabinet, gain and tone, the four effect slots with their models and settings, the noise gate, guitar and playback volumes, Extended Stereo, and the USB recording output (processed or dry).
- Follows knob changes made on the amp.

### Presets and memories

- Loads and saves THR Remote `.thrl6p` presets, and downloads the 234-preset community collection on request.
- Loads only the changes a preset needs, in batches, with an optional Keep my Master volume and Keep my Gain, and a Restore original button.
- Saves the current tone, or a preset straight from the list, to any of the five user memories under a name you choose. Works around a firmware hang when the same memory is saved twice in a row.

### App

- One-screen GTK4 and libadwaita window with rotary knobs and an adjustable knob step.
- USB recording level meter with peak hold and a clip warning.
- Themes: THR30II Cream, White, and Black, Neon, Bare Metal, and Adwaita.
- Bluetooth and USB link lights, a console with a debug switch for raw frames, and a progress bar while presets apply.

### Command line

- `thr2` with `info`, `dump`, `monitor`, `set`, `amp`, `cab`, `system`, `di`, `fx`, `presets`, `load`, `save`, `store`, and `symbols`, plus `--via` and `--debug`.

### Known limitations

- Loading a user memory from the app (the memory buttons) hasn't been verified on hardware.
- Over Bluetooth, with the USB cable unplugged, the amp reported its knob values and volumes as 0. Changes still work.
- Saves made with the amp's own USER MEMORY buttons aren't tracked by the app, so saving the same memory again from the app right after one can still hang the amp until it's turned off and on.
