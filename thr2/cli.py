"""Command-line front end: ``python -m thr2 <command>``."""

from __future__ import annotations

import argparse
import json
import sys

from .client import AMP_NAMES, CABINETS, SYSTEM_SETTINGS, THR, THRError, TYPE_FLOAT, word_float
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
    print(f"Device    {thr.identity.get('version')} on {thr.midi.path}")
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


def cmd_symbols(thr: THR, args) -> None:
    for i, name in enumerate(thr.symbols):
        if not args.filter or args.filter.lower() in name.lower():
            print(f"0x{i:04x}  {name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="thr2", description="Control a Yamaha THR-II amp over USB.")
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

    p = sub.add_parser("symbols", help="List the amp's symbol table")
    p.add_argument("filter", nargs="?")
    return parser


COMMANDS = {
    "info": cmd_info, "dump": cmd_dump, "monitor": cmd_monitor, "set": cmd_set,
    "amp": cmd_amp, "cab": cmd_cab, "system": cmd_system, "di": cmd_di, "fx": cmd_fx, "symbols": cmd_symbols,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "fx":
        words_ = [a.lower() for a in args.args]
        args.which = next((w for w in words_ if w in FX_UNITS), None)
        args.state = next((w for w in words_ if w in ("on", "off")), None)
        unknown = [w for w in words_ if w not in FX_UNITS and w not in ("on", "off")]
        if unknown:
            parser.error(f"fx: unknown argument {unknown[0]!r}; use comp, effect, echo, reverb, on, off")
    try:
        with THR.open() as thr:
            COMMANDS[args.command](thr, args)
    except (DeviceNotFound, THRError) as err:
        print(f"thr2: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0
