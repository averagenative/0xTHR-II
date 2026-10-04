# 0xTHR-II

Native Linux control for Yamaha THR-II amps (THR10II, THR10II Wireless, THR30II Wireless) over USB. Yamaha's THR Remote app only runs on Windows, macOS, iOS, and Android. This project talks to the amp's USB MIDI port directly, so you can read and change its settings from Linux, including switching the USB recording output to the dry guitar signal.

**Status:** working prototype with a GTK4 app and a command-line tool. Tested on a THR30II Wireless running firmware 1.40.0a on Fedora 44.

## Requirements

- Linux with ALSA. The amp shows up as a class-compliant USB audio and MIDI device; no driver needed.
- Python 3.10 or later. The command-line tool needs no third-party packages.
- For the app: GTK 4, libadwaita 1.7 or later, PyGObject, and GStreamer with the PipeWire plugin for the level meter. Fedora Workstation includes all of them.
- No group membership. logind gives the logged-in user access to `/dev/snd/midiC*D*`.

## The app

Run `make install` once to add **THR-II Control** to your GNOME app grid, or start it from this directory with `make gui`.

Everything fits on one screen, laid out like the amp's front panel:

- **Top:** the amp (model category plus Modern, Boutique, or Classic character, cabinet, and the five main knobs) and the recording level panel.
- **Middle:** the compressor, effect (chorus, flanger, phaser, or tremolo), echo, and reverb, each with an on/off switch, a model picker, Mix, and that model's settings.
- **Bottom:** the noise gate and the five user memories.
- **Header bar:** **Knob step** and the USB recording output (**Amp** or **Dry**).

The window mirrors the amp: turn a knob on the amp and the matching knob in the app moves. It reconnects by itself when you unplug or power-cycle the amp.

Each knob responds to dragging, the scroll wheel, and the arrow keys. **Knob step** sets how far one scroll notch or arrow-key press moves a knob: 1, 2, 5, or 10 (in dB for the gate threshold). Hold Shift to move by 1 without changing the setting. Page Up and Page Down move ten steps. The app remembers the step in `~/.config/thr2/settings.json`.

The palette button in the header bar picks a theme: the three THR-II finishes (**THR30II Cream**, **THR30II White**, and **THR30II Black**, with knob caps and the Y-pattern speaker grille), **Neon**, **Bare Metal**, or **Adwaita**, which follows your desktop's light or dark style and accent color. The app remembers your choice.

The **Recording level** panel shows what your computer records over USB, with a peak readout and a **Clipped** warning that stays lit until you click it. With headphones plugged into the amp, the **Guitar** knob (the amp's GUITAR knob) only changes what you hear, so you can set the recording level with **Master** and then turn **Guitar** down to a comfortable level. The meter reads the amp's PipeWire capture alongside REAPER, so it doesn't interrupt a recording.

Changing the amp model on a THR-II resets gain, master, and the tone controls to 50, which can be a sudden jump in volume. The app keeps your knob settings across amp changes unless you clear **Keep knobs when changing amps**. Changing an effect's model loads that model's default settings.

Loading a user memory from the app isn't verified yet. It replaces the current settings, so test it on a tone you don't mind losing.

## Presets

Click **Presets** in the header bar to browse two sources:

- **Your presets:** `.thrl6p` files in `~/Music/THR-II Presets`. **Save current tone** writes one there; THR Remote can open these files too.
- **Community presets:** 234 song and artist tones from [f3sty/Yamaha_THRII_presets](https://github.com/f3sty/Yamaha_THRII_presets). The app downloads the collection to `~/.cache/thr2/community` the first time you open the browser. The collection has no license, so this repository doesn't include it.

Click a preset to load it into the amp right away, so you can try several in a row. The knobs and pickers in the window follow along. The tone you had before the first one stays saved, and **Restore original** brings it back. Loading changes only the amp's current tone; to keep a preset, hold one of the amp's USER MEMORY buttons for 2 seconds.

More presets are shared in the [Yamaha Musicians forum's "THR patch DOWNLOAD" thread](https://yamahamusicians.com/forum/viewtopic.php?t=9613) and in [guitarpatches.com's THRII library](https://guitarpatches.com/patches.php?unit=THRII). Both need a free account. Put downloaded `.thrl6p` files in `~/Music/THR-II Presets`, or use **Open file**.

## Command line

Connect the amp over USB, turn it on, and then run any of these. Close the app first; only one program can hold the amp's MIDI port at a time.

```bash
python3 -m thr2 info
python3 -m thr2 dump
python3 -m thr2 monitor
```

`info` shows the firmware, system settings, volumes, and user memory names. `dump` shows the current tone: amp model, cabinet, and every effect parameter. `monitor` prints changes as you turn knobs on the amp.

To change settings:

```bash
python3 -m thr2 set Amp Master 40
python3 -m thr2 amp "Lead / Boutique"
python3 -m thr2 cab "Boutique 2x12"
python3 -m thr2 di on
python3 -m thr2 di off
python3 -m thr2 fx off
python3 -m thr2 fx effect off
```

Values are 0 to 100, like the knobs. `di on` makes the USB recording output carry the dry guitar signal instead of the amp-and-effects sound. Run `python3 -m thr2 --help` for every command.

`fx` shows the compressor, effect (chorus, flanger, phaser, or tremolo), echo, and reverb, and switches them on or off. On the amp itself, turning the EFFECT or ECHO/REV knob fully counterclockwise switches that effect off. Turning the knob again switches it back on, and each user memory stores its own effect settings, so save a memory with the effects off if you want a dry preset.

Presets work from the command line too:

```bash
python3 -m thr2 presets sandman
python3 -m thr2 load "Metallica Enter Sandman"
python3 -m thr2 save "My crunch"
```

`load` accepts a file path or a preset name, and saves your previous tone to `~/.cache/thr2/last-tone-before-load.thrl6p` first. `save` writes to `~/Music/THR-II Presets` unless you give a path.

`set`, `di`, `fx`, `load`, and `save` are verified on hardware. `amp` and `cab` use commands from the protocol notes but haven't been tested yet. Switching the amp model might reset its knobs, so save your tone to a user memory on the amp first.

To install the `thr2` command for your user, run `pip install --user -e .` in this directory.

## Recording through the THR

The THR30II Wireless USB audio interface is UAC1 at full speed: 2 channels in and 2 out, 16-bit, at 44.1 or 48 kHz, with asynchronous clocking. Both the processed and the dry signal travel on the same two channels, so you record one or the other. Use `thr2 di on` to record a dry DI track for reamping with NAM or other plugins, and `thr2 di off` to record the amp's own tone.

The amp's GUITAR knob doesn't affect the USB level, and turning on the tuner mutes the USB output.

## How it works

| Module | Role |
|---|---|
| `thr2/device.py` | Finds the amp's raw MIDI node and splits incoming bytes into SysEx messages on a reader thread |
| `thr2/sysex.py` | Line 6 SysEx framing: headers, frame counters, and 7-bit "bitbucket" coding |
| `thr2/client.py` | Unlock, symbol table, queries, parameter changes, and change events |
| `thr2/patch.py` | Parser for patch dumps (the current tone or a stored user memory) |
| `thr2/thrl6p.py` | Reads, applies, and writes THR Remote `.thrl6p` preset files |
| `thr2/library.py` | Your preset folder and the downloadable community collection |
| `thr2/cli.py` | The `thr2` command |
| `thr2/gui/worker.py` | Background thread that owns the connection, coalesces knob moves, and forwards the amp's change reports |
| `thr2/gui/window.py` | The libadwaita window |
| `thr2/gui/knob.py` | Rotary knob control with drag, scroll, and keyboard input and a shared step setting |
| `thr2/gui/settings.py` | Per-user preferences |
| `thr2/gui/presets.py` | The preset browser |
| `thr2/gui/themes.py` | Themes: libadwaita color variables, extra CSS, knob styles, and the generated grille texture |
| `thr2/gui/meter.py` | USB recording level meter: `pipewiresrc ! level`, pinned to the amp's capture node with fallback disabled |

The amp ignores commands until a client unlocks its MIDI interface with a firmware-specific key. After that, every unit, parameter, and amp model is a number that indexes the amp's own symbol table. Those numbers change between firmware versions, so the client downloads the table on first connect and caches it in `~/.cache/thr2/`. See `docs/protocol.md` for the details.

## Credits

The protocol knowledge comes from Martin Zwerschke's reverse-engineering notes, `SYSEX_PROTOCOL_THR30II.pdf` in [THRII-direct-USB-pedalboard](https://github.com/martinzw/THRII-direct-USB-pedalboard). This project contains no code from that repository.

## License

MIT. See `LICENSE`.
