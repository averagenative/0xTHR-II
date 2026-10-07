"""Bluetooth LE MIDI transport for THR-II Wireless amps, through BlueZ over D-Bus.

The amp advertises the standard BLE-MIDI service (03b80e5a-...), but its data
characteristic reports the short UUID 0x6BF3 instead of the standard 7772e5db-..., so
PipeWire's BLE-MIDI support skips it. This module talks to the characteristic directly:
AcquireNotify and AcquireWrite hand back sockets, so reading works like the USB rawmidi
transport, with a reader thread and no GLib main loop.

BLE-MIDI framing: every packet starts with a header byte (bit 7 set, high timestamp
bits). A timestamp byte precedes each status byte, including F0 and the closing F7.
SysEx continues across packets, with each continuation packet starting with a header.
"""

from __future__ import annotations

import os
import queue
import select
import threading
import time

from gi.repository import Gio, GLib

from . import log

LOG = log.get("ble")

MIDI_SERVICE = "03b80e5a-ede8-4b33-a751-6ce34ec4c700"
MIDI_CHARACTERISTIC = ("7772e5db-3868-4112-a1a9-f2669d106bf3", "00006bf3-0000-1000-8000-00805f9b34fb")
BLUEZ = "org.bluez"
DEFAULT_MTU = 23


class BluetoothNotFound(RuntimeError):
    pass


def _bus() -> Gio.DBusConnection:
    return Gio.bus_get_sync(Gio.BusType.SYSTEM, None)


def _objects(bus) -> dict:
    reply = bus.call_sync(BLUEZ, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
                          None, None, Gio.DBusCallFlags.NONE, 5000, None)
    return reply.unpack()[0]


def find_thr(name_hint: str = "THR") -> dict | None:
    """Find a paired THR with the BLE-MIDI service. Returns paths, name, address, and state."""
    try:
        bus = _bus()
        objects = _objects(bus)
    except GLib.Error:
        return None
    for path, ifaces in objects.items():
        dev = ifaces.get("org.bluez.Device1")
        if not dev or MIDI_SERVICE not in [u.lower() for u in dev.get("UUIDs", [])]:
            continue
        if name_hint.lower() not in str(dev.get("Name", "")).lower():
            continue
        return {
            "device": path, "name": dev.get("Name"), "address": dev.get("Address"),
            "connected": bool(dev.get("Connected")), "paired": bool(dev.get("Paired")),
            "trusted": bool(dev.get("Trusted")),
        }
    return None


def release(name_hint: str = "THR") -> bool:
    """Disconnect a paired THR and stop BlueZ reconnecting it by itself.

    BlueZ reconnects a trusted LE device whenever it advertises. Disconnecting an untrusted
    one holds it off until something calls Connect, as BleMidi does. Returns True when a
    link was up and got dropped.
    """
    info = find_thr(name_hint)
    if info is None or not (info["connected"] or info["trusted"]):
        return False
    try:
        bus = _bus()
        if info["trusted"]:
            bus.call_sync(BLUEZ, info["device"], "org.freedesktop.DBus.Properties", "Set",
                          GLib.Variant("(ssv)", ("org.bluez.Device1", "Trusted", GLib.Variant("b", False))),
                          None, Gio.DBusCallFlags.NONE, 5000, None)
        if info["connected"]:
            bus.call_sync(BLUEZ, info["device"], "org.bluez.Device1", "Disconnect", None, None,
                          Gio.DBusCallFlags.NONE, 5000, None)
    except GLib.Error as err:
        LOG.warning("Couldn't disconnect %s over Bluetooth: %s", info["name"], err.message)
        return False
    return info["connected"]


def _characteristic(bus, device_path: str) -> str | None:
    objects = _objects(bus)
    services = [p for p, i in objects.items()
                if p.startswith(device_path + "/") and i.get("org.bluez.GattService1", {}).get("UUID") == MIDI_SERVICE]
    for path, ifaces in objects.items():
        char = ifaces.get("org.bluez.GattCharacteristic1")
        if char and any(path.startswith(s + "/") for s in services) and char.get("UUID") in MIDI_CHARACTERISTIC:
            return path
    return None


def packetize(message: bytes, mtu: int) -> list[bytes]:
    """Split one SysEx message (F0 ... F7) into BLE-MIDI packets."""
    stamp = int(time.monotonic() * 1000) & 0x1FFF
    header, ts = 0x80 | ((stamp >> 7) & 0x3F), 0x80 | (stamp & 0x7F)
    room = max(mtu - 3, 5)
    body = message[1:-1]
    packets, current = [], bytearray((header, ts, 0xF0))
    for byte in body:
        if len(current) >= room:
            packets.append(bytes(current))
            current = bytearray((header,))
        current.append(byte)
    if len(current) + 2 > room:
        packets.append(bytes(current))
        current = bytearray((header,))
    current.extend((ts, 0xF7))
    packets.append(bytes(current))
    return packets


class Reassembler:
    """Turn BLE-MIDI packets back into complete SysEx messages."""

    def __init__(self):
        self.buffer: bytearray | None = None

    def feed(self, packet: bytes) -> list[bytes]:
        done = []
        i = 1
        while i < len(packet):
            byte = packet[i]
            if byte & 0x80:
                status = packet[i + 1] if i + 1 < len(packet) and packet[i + 1] & 0x80 else None
                if status == 0xF0:
                    self.buffer = bytearray((0xF0,))
                    i += 2
                elif status == 0xF7:
                    if self.buffer is not None:
                        self.buffer.append(0xF7)
                        done.append(bytes(self.buffer))
                    self.buffer = None
                    i += 2
                elif status is not None:
                    i += 2
                else:
                    i += 1
            else:
                if self.buffer is not None:
                    self.buffer.append(byte)
                i += 1
        return done


class BleMidi:
    """Same interface as device.RawMidi: write(), receive(), close(), alive(), path."""

    kind = "Bluetooth"

    def __init__(self, info: dict | None = None, connect_timeout: float = 15.0):
        info = info or find_thr()
        if info is None:
            raise BluetoothNotFound("No paired THR-II found over Bluetooth.")
        self.bus = _bus()
        self.device = info["device"]
        self.name = info.get("name") or "THR-II"
        self.path = f"bluetooth:{info.get('address')}"
        if not info.get("connected"):
            LOG.info("Asking BlueZ to connect %s", self.path)
            self.bus.call_sync(BLUEZ, self.device, "org.bluez.Device1", "Connect", None, None,
                               Gio.DBusCallFlags.NONE, int(connect_timeout * 1000), None)
        self.char = None
        deadline = time.monotonic() + connect_timeout
        while self.char is None and time.monotonic() < deadline:
            self.char = _characteristic(self.bus, self.device)
            if self.char is None:
                time.sleep(0.3)
        if self.char is None:
            raise BluetoothNotFound("The amp is connected but its MIDI service didn't appear.")
        LOG.debug("MIDI characteristic: %s", self.char)
        self.notify_fd, mtu_in = self._acquire("AcquireNotify")
        try:
            self.write_fd, self.mtu = self._acquire("AcquireWrite")
        except GLib.Error as err:
            LOG.info("AcquireWrite unavailable (%s); using WriteValue", err.message)
            self.write_fd, self.mtu = None, DEFAULT_MTU
        LOG.debug("Notify MTU %d, write MTU %d", mtu_in, self.mtu)
        self.messages: queue.Queue[bytes] = queue.Queue()
        self._read_size = max(mtu_in, 512)
        self._stop = threading.Event()
        self._reader = threading.Thread(target=self._read_loop, name="thr2-ble-in", daemon=True)
        self._reader.start()

    def _acquire(self, method: str) -> tuple[int, int]:
        reply, fds = self.bus.call_with_unix_fd_list_sync(
            BLUEZ, self.char, "org.bluez.GattCharacteristic1", method,
            GLib.Variant("(a{sv})", ({},)), GLib.VariantType.new("(hq)"),
            Gio.DBusCallFlags.NONE, 5000, None, None)
        handle, mtu = reply.unpack()
        return fds.get(handle), mtu

    def write(self, data: bytes) -> None:
        log.frame("TX", data, "ble")
        for packet in packetize(data, self.mtu):
            if self.write_fd is not None:
                os.write(self.write_fd, packet)
            else:
                self.bus.call_sync(BLUEZ, self.char, "org.bluez.GattCharacteristic1", "WriteValue",
                                   GLib.Variant("(aya{sv})", (list(packet), {"type": GLib.Variant("s", "command")})),
                                   None, Gio.DBusCallFlags.NONE, 5000, None)
            time.sleep(0.003)

    def receive(self, timeout: float | None = None) -> bytes | None:
        try:
            return self.messages.get(timeout=timeout)
        except queue.Empty:
            return None

    def _read_loop(self) -> None:
        reassembler = Reassembler()
        while not self._stop.is_set():
            ready, _, _ = select.select([self.notify_fd], [], [], 0.1)
            if not ready:
                continue
            try:
                packet = os.read(self.notify_fd, self._read_size)
            except OSError as err:
                LOG.warning("Bluetooth notifications stopped: %s", err)
                break
            if not packet:
                LOG.warning("Bluetooth notification socket closed; the link probably dropped")
                break
            for message in reassembler.feed(packet):
                log.frame("RX", message, "ble")
                self.messages.put(message)

    def alive(self) -> bool:
        if not self._reader.is_alive():
            return False
        try:
            reply = self.bus.call_sync(BLUEZ, self.device, "org.freedesktop.DBus.Properties", "Get",
                                       GLib.Variant("(ss)", ("org.bluez.Device1", "Connected")),
                                       None, Gio.DBusCallFlags.NONE, 2000, None)
            return bool(reply.unpack()[0])
        except GLib.Error:
            return False

    def close(self) -> None:
        self._stop.set()
        self._reader.join(timeout=1)
        for fd in (self.notify_fd, self.write_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def __enter__(self) -> BleMidi:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
