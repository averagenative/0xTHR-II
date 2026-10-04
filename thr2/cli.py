"""Command-line front end: ``python -m thr2 <command>``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import AMP_NAMES, CABINETS, SYSTEM_SETTINGS, THR, THRError, TYPE_FLOAT, word_float
from . import library, thrl6p
from .device import DeviceNotFound
from .patch import Patch

AMP_UNIT = "Amp"
PROC_UNIT = "GuitarProc"


RAW_PARAMS = {"Reference", "Period", "Thresh", "SpkSimType", "Tempo"}


def pct(value: object, name: str = "") -> str:
    if isinstance(value, bool) or not isinstance(value, float):
        return str(value)
    if name.removesuffix("State") in RAW_PARAMS or not 0.0 <= value <= 1.0:
        return f"{value:g}"
    return f"{value * 100:5.1f}"


def cmd_info(thr: THR, args) -> None:
    print(f"Device    {thr.identity.get('version')} over {thr.midi.kind} ({thr.midi.path})")
    print(f"Firmware  {thr.firmware_text}  ({len(thr.symbols)} symbols)")
    print("System settings:")
    for name in SYSTEM_SETTINGS:
        try:
            vtype, value = thr.system(name)
        except THRError:
            continue
        shown = f"{word_float(value):.3f}" if vtype == TYPE_FLOAT else str(value)
        print(f"  {name:22s} {shown}")
    print("Global parameters:")
    for name in ("GuitarVolume", "AudioVolume", "GuitInputGain", "TunerEnable"):
        try:
            print(f"  {name:22s} {pct(thr.get_global(name))}")
        except THRError:
            pass
    print("User memories:")
    for i in range(5):
        print(f"  {i + 1}  {thr.patch_name(i)}")


def print_patch(patch: Patch) -> None:
    print(f"Patch  {patch.name!r}")
    proc = patch.find(PROC_UNIT)
    amp = patch.find(AMP_UNIT)
    if amp:
        print(f"Amp    {AMP_NAMES.get(amp.type, amp.type)}  ({amp.type})")
    if proc:
        cab = proc.params.get("SpkSimTypeState")
        if isinstance(cab, (int, float)) and not isinstance(cab, bool) and 0 <= int(cab) < len(CABINETS):
            print(f"Cab    {CABINETS[int(cab)]}")
    for unit, parent in patch.walk():
        if not unit.params:
            continue
        indent = "  " if parent else ""
        print(f"{indent}[{unit.name}] {unit.type}")
        for key, value in unit.params.items():
            print(f"{indent}  {key.removesuffix('State'):16s} {pct(value, key)}")


def cmd_dump(thr: THR, args) -> None:
    index = 0xFFFFFFFF if args.memory is None else args.memory - 1
    patch = thr.dump(index)
    if args.json:
        def unit_dict(u):
            return {"type": u.type, "params": u.params, "units": {k: unit_dict(v) for k, v in u.units.items()}}
        print(json.dumps({"meta": patch.meta, "units": {k: unit_dict(v) for k, v in patch.units.items()}}, indent=2))
    else:
        print_patch(patch)


def cmd_monitor(thr: THR, args) -> None:
    sys.stdout.reconfigure(line_buffering=True)
    print("Listening for changes on the amp. Press Ctrl+C to stop.")
    for event in thr.listen():
        if event.opcode == 0x04:
            print(f"{event.unit:12s} {event.param:16s} {pct(event.value, event.param)}")
        elif event.opcode == 0x03:
            friendly = AMP_NAMES.get(str(event.value), "")
            print(f"{event.unit:12s} {'type':16s} {event.value} {friendly}")
        elif event.opcode == 0x02:
            print(f"{'memory':12s} {'recalled':16s} {event.value}")
        elif args.verbose:
            print(f"opcode 0x{event.opcode:02x} {[hex(w) for w in event.words]}")


def cmd_set(thr: THR, args) -> None:
    value = args.value / 100.0 if not args.raw else args.value
    ok = thr.set_param(args.unit, args.param, value)
    print("OK" if ok else "Amp rejected the change (not acknowledged).")


def cmd_amp(thr: THR, args) -> None:
    wanted = args.model
    by_friendly = {v.lower().replace(" ", ""): k for k, v in AMP_NAMES.items()}
    symbol = by_friendly.get(wanted.lower().replace(" ", ""), wanted)
    ok = thr.set_unit_type(AMP_UNIT, symbol)
    print(f"Amp set to {symbol}" if ok else "Amp rejected the model.")


def cmd_cab(thr: THR, args) -> None:
    try:
        index = int(args.cab)
    except ValueError:
        matches = [i for i, c in enumerate(CABINETS) if args.cab.lower() in c.lower()]
        if not matches:
            sys.exit(f"Unknown cabinet {args.cab!r}. Choices: {', '.join(CABINETS)}")
        index = matches[0]
    ok = thr.set_param(PROC_UNIT, "SpkSimType", float(index))
    print(f"Cab set to {CABINETS[index]}" if ok else "Amp rejected the cabinet.")


def cmd_system(thr: THR, args) -> None:
    if args.value is None:
        vtype, value = thr.system(args.name)
        print(f"{args.name} type={vtype} value={value}")
        return
    ok = thr.set_system(args.name, args.value)
    vtype, value = thr.system(args.name)
    print(f"{'OK' if ok else 'Not acknowledged'}; {args.name} now reads {value}")


def cmd_di(thr: THR, args) -> None:
    if args.state is not None:
        thr.set_system("guitar_di_mode", 1 if args.state == "on" else 0)
    _, value = thr.system("guitar_di_mode")
    print("USB output: dry guitar (DI)" if value else "USB output: processed (amp and effects)")


FX_UNITS = {
    "comp": ("FX1", "Compressor"),
    "effect": ("FX2", "Effect (chorus, flanger, phaser, tremolo)"),
    "echo": ("FX3", "Echo"),
    "reverb": ("FX4", "Reverb"),
}


def cmd_fx(thr: THR, args) -> None:
    targets = [args.which] if args.which else list(FX_UNITS)
    if args.state:
        for name in targets:
            unit = FX_UNITS[name][0]
            if not thr.set_param(PROC_UNIT, f"{unit}Enable", 1.0 if args.state == "on" else 0.0):
                print(f"Amp rejected switching {name} {args.state}.")
    patch = thr.dump()
    proc = patch.find(PROC_UNIT)
    for name, (unit, label) in FX_UNITS.items():
        enabled = proc.params.get(f"{unit}EnableState") if proc else None
        model = patch.find(unit)
        state = "on " if enabled else "off"
        print(f"{name:7s} {state}  {model.type if model else '?':20s} {label}")


def resolve_preset(target: str) -> tuple[dict, str]:
    """Accept a file path or a preset name from your folder or the community collection."""
    path = Path(target).expanduser()
    if path.exists():
        preset = thrl6p.read(path)
        return preset, thrl6p.name_of(preset, path.stem)
    if not library.community_ready():
        print("Downloading the community preset collection...", file=sys.stderr)
        library.download_community()
    matches = library.find(target)
    if not matches:
        sys.exit(f"No preset file or name matches {target!r}. Try: thr2 presets {target.split()[0]}")
    if len(matches) > 1:
        names = "\n  ".join(e.name for e in matches[:15])
        sys.exit(f"{len(matches)} presets match {target!r}. Be more specific:\n  {names}")
    return thrl6p.read(matches[0].path), matches[0].name


def cmd_load(thr: THR, args) -> None:
    preset, name = resolve_preset(args.preset)
    before = thr.dump()
    backup = thrl6p.from_patch(before, f"Before {name}", firmware=thr.firmware)
    backup_path = thrl6p.write(backup, library.CACHE.parent / "last-tone-before-load.thrl6p")
    hold = {}
    amp = before.find("Amp")
    if args.keep_master and amp:
        hold[("Amp", "Master")] = amp.params.get("MasterState", 0.5)
    if args.keep_gain and amp:
        hold[("Amp", "Drive")] = amp.params.get("DriveState", 0.5)
    skipped = thrl6p.apply(thr, preset, hold)
    print(f"Loaded {name!r} into the amp's current tone.")
    print(f"To keep it, hold a USER MEMORY button on the amp for 2 seconds.")
    print(f"Your previous tone is saved as {backup_path}; load that file to undo.")
    if skipped and args.verbose:
        print("Skipped settings the current models don't use:")
        for note in skipped:
            print(f"  {note}")


def cmd_save(thr: THR, args) -> None:
    patch = thr.dump()
    name = args.name or Path(args.file).stem
    target = Path(args.file).expanduser()
    if not target.is_absolute() and target.parent == Path("."):
        target = library.USER_DIR / target
    path = thrl6p.write(thrl6p.from_patch(patch, name, firmware=thr.firmware), target)
    print(f"Saved the current tone as {path}")


def cmd_presets(args) -> None:
    if args.update or not library.community_ready():
        print(f"Downloaded {library.download_community()} community presets.", file=sys.stderr)
    entries = library.user() + library.community()
    if args.filter:
        entries = [e for e in entries if args.filter.lower() in e.name.lower()]
    for e in entries:
        amp = AMP_NAMES.get(e.amp, e.amp)
        print(f"{e.source:9s} {e.name:42s} {amp}")


def cmd_store(thr: THR, args) -> None:
    from .patch import rename_dump
    index = args.memory - 1
    old_name = thr.patch_name(index)
    dump = thr.dump_raw()
    if args.name:
        dump = rename_dump(dump, args.name)
    if not args.yes:
        answer = input(f"Replace user memory {args.memory} ({old_name!r}) with the current tone? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Nothing saved.")
            return
    ok = thr.store_memory(index, dump)
    print(f"Saved to user memory {args.memory} as {thr.patch_name(index)!r}" if ok else "The amp didn't accept the save.")


def cmd_symbols(thr: THR, args) -> None:
    for i, name in enumerate(thr.symbols):
        if not args.filter or args.filter.lower() in name.lower():
            print(f"0x{i:04x}  {name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="thr2", description="Control a Yamaha THR-II amp over USB or Bluetooth.")
    parser.add_argument("--debug", action="store_true", help="Print the connection log and every raw frame")
    parser.add_argument("--via", choices=("auto", "usb", "bluetooth"), default="auto",
                        help="Connection to use. auto prefers USB, then a connected Bluetooth amp.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="Show firmware, system settings, volumes, and preset names")

    p = sub.add_parser("dump", help="Show the current tone or a stored user memory")
    p.add_argument("--memory", type=int, choices=range(1, 6), help="User memory 1 to 5")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("monitor", help="Print knob and switch changes as they happen")
    p.add_argument("-v", "--verbose", action="store_true")

    p = sub.add_parser("set", help="Set a parameter, for example: set Amp Master 40")
    p.add_argument("unit", help="Amp, FX1 to FX4, GuitarProc, or global")
    p.add_argument("param", help="Symbol name, for example Drive, Master, Bass, Thresh")
    p.add_argument("value", type=float, help="0 to 100 (or the raw value with --raw)")
    p.add_argument("--raw", action="store_true")

    p = sub.add_parser("amp", help="Select an amp model by name, for example 'Lead / Boutique'")
    p.add_argument("model")

    p = sub.add_parser("cab", help="Select a cabinet by number (0 to 16) or name")
    p.add_argument("cab")

    p = sub.add_parser("system", help="Read or write a system setting (writes are experimental)")
    p.add_argument("name", choices=sorted(SYSTEM_SETTINGS))
    p.add_argument("value", nargs="?", type=int)

    p = sub.add_parser("di", help="Show or switch the USB output between processed and dry")
    p.add_argument("state", nargs="?", choices=("on", "off"))

    p = sub.add_parser("fx", help="Show effects, or switch them: fx off, fx effect off, fx reverb on")
    p.add_argument("args", nargs="*", metavar="[comp|effect|echo|reverb] [on|off]")

    p = sub.add_parser("load", help="Load a .thrl6p preset into the amp's current tone")
    p.add_argument("preset", help="A .thrl6p file, or a preset name from your folder or the community collection")
    p.add_argument("-v", "--verbose", action="store_true", help="List settings the preset's models don't use")
    p.add_argument("--keep-master", action="store_true", help="Keep the current Master volume")
    p.add_argument("--keep-gain", action="store_true", help="Keep the current Gain")

    p = sub.add_parser("save", help="Save the amp's current tone as a .thrl6p preset")
    p.add_argument("file", help="File name; a bare name goes in ~/Music/THR-II Presets")
    p.add_argument("--name", help="Preset name shown in THR Remote and this app")

    p = sub.add_parser("presets", help="List presets in your folder and the community collection")
    p.add_argument("filter", nargs="?")
    p.add_argument("--update", action="store_true", help="Download the community collection again")

    p = sub.add_parser("store", help="Save the current tone into one of the amp's user memories")
    p.add_argument("memory", type=int, choices=range(1, 6), help="User memory 1 to 5 (overwritten)")
    p.add_argument("--name", help="Name to store with it")
    p.add_argument("-y", "--yes", action="store_true", help="Don't ask for confirmation")

    p = sub.add_parser("symbols", help="List the amp's symbol table")
    p.add_argument("filter", nargs="?")
    return parser


COMMANDS = {
    "info": cmd_info, "dump": cmd_dump, "monitor": cmd_monitor, "set": cmd_set,
    "amp": cmd_amp, "cab": cmd_cab, "system": cmd_system, "di": cmd_di, "fx": cmd_fx, "load": cmd_load, "save": cmd_save, "store": cmd_store, "symbols": cmd_symbols,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.debug:
        from . import log
        log.to_stderr()
        log.enable_debug(True)
    if args.command == "fx":
        words_ = [a.lower() for a in args.args]
        args.which = next((w for w in words_ if w in FX_UNITS), None)
        args.state = next((w for w in words_ if w in ("on", "off")), None)
        unknown = [w for w in words_ if w not in FX_UNITS and w not in ("on", "off")]
        if unknown:
            parser.error(f"fx: unknown argument {unknown[0]!r}; use comp, effect, echo, reverb, on, off")
    if args.command == "presets":
        cmd_presets(args)
        return 0
    try:
        with THR.open(via=args.via) as thr:
            COMMANDS[args.command](thr, args)
    except (DeviceNotFound, THRError) as err:
        print(f"thr2: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0
