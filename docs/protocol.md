# THR-II protocol notes

These notes record what this project relies on and what it verified on real hardware. The primary source is Martin Zwerschke's `SYSEX_PROTOCOL_THR30II.pdf`, which is itself built from observation and guesswork. Treat anything not marked as verified as a hypothesis.

Test unit: THR30II Wireless, USB ID `0499:7183`, firmware 1.40.0a, Fedora 44, kernel 7.2, verified 2026-10-03.

## USB descriptors

`lsusb -v -d 0499:7183` shows the following:

| Interface | Class | Details |
|---|---|---|
| 0 | Audio control | UAC 1.0 header |
| 1 | MIDI streaming | One embedded MIDI IN and OUT jack, bulk endpoints 0x02 and 0x82 |
| 2 | Audio control | USB streaming input to speaker, microphone to USB streaming output; 2 channels each |
| 3 | Audio streaming (capture) | 16-bit, 2 channels, 48 or 44.1 kHz, isochronous asynchronous, implicit feedback |
| 4 | Audio streaming (playback) | 16-bit, 2 channels, 48 or 44.1 kHz, isochronous asynchronous, feedback endpoint 0x84 |

The device is self-powered (`MaxPower 0mA`) and runs at full speed (12 Mbit/s). ALSA exposes the MIDI port as `hw:<card>,0,0`, which is `/dev/snd/midiC<card>D0`.

## Frame format

Every message is SysEx with this header after `F0`:

| Bytes | Meaning |
|---|---|
| `00 01 0C` | Line 6 manufacturer ID |
| `24 02` | Family and model from the identity reply (`02` is the THR30II Wireless) |
| `4D` | Constant for normal traffic. `7E` marks the firmware-string reply. |
| `ab` | Command group: `00` (A) or `01` (B). Each group has its own counter. |
| `cnt` | 7-bit frame counter for that group |
| `part` | Frame index within a multi-frame payload |
| `hi lo` | Index of the last valid decoded payload byte, as two nibbles |

The payload is bitbucket coded: each group of 7 raw bytes travels as 8 bytes, with the first byte holding the 7 high bits. Decoded payloads are mostly little-endian 32-bit words. Commands start with an opcode word and a body-length word.

## Session start (verified)

1. Send the universal identity request `F0 7E 7F 06 01 F7`. The amp replies with an identity message and a second frame carrying `L6ImageVersion:1.4.0.0.a`.
2. Send A-command `0x01` (firmware version). The answer is `0x01400061` for 1.40.0a.
3. Send A-command `0x04` with the unlock key as a body frame. The amp answers with an acknowledgment (`0`) or a rejection (`0xFFFFFFFF`).

Unlock keys:

| Firmware | Key |
|---|---|
| 1.30.0c | `0x686FBEEB` |
| 1.31.0k | `0x9809EB24` |
| 1.40.0a | `0x7986615C` (verified) |
| 1.42.0g, 1.43.0b, 1.44.0a | `0xDD54CD72` |

The unlock lasts until the amp powers off. Repeating it is harmless.

## Commands this project uses

| Opcode | Group | Body | Purpose | Status |
|---|---|---|---|---|
| `0x01` | A | none | Firmware version | Verified |
| `0x03` | A | none | Download the symbol table (372 names on 1.40.0a) | Verified |
| `0x04` | A | key | Unlock MIDI control | Verified |
| `0x06` | B, in-frame | memory index | User memory name | Verified |
| `0x08` | A | unit, type symbol | Select amp model or effect type | Verified for Amp and FX2 to FX4 |
| `0x09` | A | `0xFFFFFFFF`, param | Read a global parameter | Verified |
| `0x0A` | A | unit, param, type 4, float | Set a parameter. Unit `0xFFFFFFFF` sets a global such as GuitarVolume. | Verified: Amp knobs, GuitarProc FX enables, SpkSimType, GateEnable, Thresh, and GuitarVolume |
| `0x0C` | B, in-frame | memory index or `0xFFFFFFFF` | Download a patch dump | Verified |
| `0x0D` | A | code | Read a system setting | Verified |
| `0x0E` | A | code, type, value | Write a system setting | Verified with codes `0x0D` (DI mode) and `0x06` (Extended Stereo) |
| `0x0E` | B, in-frame | memory index | Load a user memory | Not yet tested |

Answers use opcode `0x01`, followed by a length word and the data. Multi-frame answers continue in frames with `part` 1, 2, and so on. Change reports from the amp use opcode `0x04` (parameter: unit, param, type, value), `0x03` (unit type: unit, symbol), `0x02` (user memory recalled), and `0x06` (ready marker).

## Side effects of model changes (verified)

- Selecting an amp model, even the current one, resets Bass, Mid, Treble, Drive, and Master to 0.5.
- Selecting an effect model loads that model's default settings. Each model has its own parameter set: Chorus (Freq, Depth, Pre, Feedback), Flanger (Freq, Depth), Phaser (Speed, Feedback), Tremolo (Speed, Depth), Tape echo and Digital delay (Time, Feedback, Bass, Treble), Spring (Time, Tone), and Plate, Hall, and Room (Decay, PreDelay, Tone).
- Effect models on 1.40.0a: FX1 `RedComp`; FX2 `StereoSquareChorus`, `L6Flanger`, `Phaser`, `BiasTremolo`; FX3 `TapeEcho`, `L6DigitalDelay`; FX4 `StandardSpring`, `LargePlate1`, `ReallyLargeHall`, `SmallRoom1`.
- The gate threshold (`Thresh`) is a raw dB value, -96 to 0, not a 0 to 1 fraction.
- Every patch dump ends with an opcode `0x02` report whose last word is 1 ("downloaded"). A user memory recall reports 0 in that word.

## Symbol names

Change reports and parameter writes use plain names such as `Master` (`0x4c`), `Drive` (`0x58`), and `SpkSimType` (`0x107`). Patch dumps use `...State` names such as `MasterState` (`0x53`). Units are `Amp` (`0x10c`), `FX1` (`0x109`, compressor), `FX2` (`0x10e`, modulation), `FX3` (`0x111`, echo), `FX4` (`0x114`, reverb), and `GuitarProc` (`0x13c`, gate, cabinet, and effect switches). The numbers are for 1.40.0a.

## System settings

Read with opcode `0x0D` and write with `0x0E`. The answer is a status word, a type word (2 = enum, 4 = float), and a value.

| Code | Name | Reading on the test unit |
|---|---|---|
| `0x00` | Current user memory (0-based) | 0 |
| `0x01` | User memory changed | 1 |
| `0x02` | Front LED | 127 |
| `0x03` | Wireless channel mode | 1 |
| `0x04` | Wireless channel | 13 |
| `0x06` | Extended stereo | 1 |
| `0x07` | Audio streaming EQ | 1 |
| `0x08` | Guitar and audio volume to line out | 0.5 (float) |
| `0x09` | USB output volume | 0.0 (float). USB capture still carries signal, so this likely means 0 dB. |
| `0x0B` | G10T transmitter plugged in | 0 |
| `0x0C` | Battery level | 2 |
| `0x0D` | Guitar DI mode (record dry) | 0. Writing 1 and then 0 was acknowledged and read back correctly. |
| `0x0E` | Speaker tuner mode | 1 |
| `0x0F` | Eco recharge | 1 |

## Open questions

- Does DI mode survive a power cycle?
- What scale do the battery level and front LED values use?
- Does patch upload (B-command `0x0D` with 210-byte body frames) work on 1.40.0a?
- Does Bluetooth MIDI on the Wireless models carry the same protocol? If so, the app could work without a cable.
