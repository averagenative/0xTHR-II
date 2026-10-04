# Changelog

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
