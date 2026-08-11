"""
signals.py

Defines the CAN messages used in this simulation, and how to pack/unpack
their signals into raw bytes. This is a tiny hand-rolled version of what a
real automotive DBC file does: map an arbitration ID -> named signals with
scaling, offset, and bit layout.

Two messages are defined:

  0x100  VehicleSpeed     -> 1 signal: speed_kph   (0-255, 1 byte, scale 1.0)
  0x101  DoorStatus       -> 4 signals: door FL/FR/RL/RR (1 bit each)

Real vehicle CAN buses look exactly like this in spirit: fixed arbitration
IDs, fixed-width signals packed into an 8-byte payload, with a scale/offset
per signal so raw integers map to physical units.
"""

import struct

VEHICLE_SPEED_ID = 0x100
DOOR_STATUS_ID = 0x101
ENGINE_RPM_ID = 0x102
WARNING_LIGHTS_ID = 0x103


def encode_vehicle_speed(speed_kph: float) -> bytes:
    """Pack speed (0-255 kph) into a 1-byte payload (byte 0), padded to 8 bytes."""
    raw = max(0, min(255, int(round(speed_kph))))
    payload = struct.pack("B", raw)
    return payload.ljust(8, b"\x00")


def decode_vehicle_speed(data: bytes) -> float:
    (raw,) = struct.unpack("B", data[0:1])
    return float(raw)


def encode_door_status(front_left: bool, front_right: bool, rear_left: bool, rear_right: bool) -> bytes:
    """Pack 4 door-open flags into the low 4 bits of byte 0."""
    byte0 = (bool(front_left) << 0) | (bool(front_right) << 1) | (bool(rear_left) << 2) | (bool(rear_right) << 3)
    payload = struct.pack("B", byte0)
    return payload.ljust(8, b"\x00")


def decode_door_status(data: bytes) -> dict:
    byte0 = data[0]
    return {
        "front_left": bool(byte0 & 0b0001),
        "front_right": bool(byte0 & 0b0010),
        "rear_left": bool(byte0 & 0b0100),
        "rear_right": bool(byte0 & 0b1000),
    }


def encode_engine_rpm(rpm: float) -> bytes:
    """Pack RPM (0-8000) into 2 bytes, little-endian, bytes 0-1."""
    raw = max(0, min(65535, int(round(rpm))))
    payload = struct.pack("<H", raw)
    return payload.ljust(8, b"\x00")


def decode_engine_rpm(data: bytes) -> float:
    (raw,) = struct.unpack("<H", data[0:2])
    return float(raw)


# Warning light bit positions within byte 0 of WARNING_LIGHTS_ID
_WARNING_BITS = {
    "check_engine": 0,
    "low_fuel": 1,
    "engine_temp": 2,
    "seatbelt": 3,
    "battery": 4,
}


def encode_warning_lights(**flags: bool) -> bytes:
    """Pack named warning flags into the low bits of byte 0.

    Accepts any of: check_engine, low_fuel, engine_temp, seatbelt, battery
    """
    byte0 = 0
    for name, bit in _WARNING_BITS.items():
        if flags.get(name):
            byte0 |= 1 << bit
    payload = struct.pack("B", byte0)
    return payload.ljust(8, b"\x00")


def decode_warning_lights(data: bytes) -> dict:
    byte0 = data[0]
    return {name: bool(byte0 & (1 << bit)) for name, bit in _WARNING_BITS.items()}


MESSAGE_NAMES = {
    VEHICLE_SPEED_ID: "VehicleSpeed",
    DOOR_STATUS_ID: "DoorStatus",
    ENGINE_RPM_ID: "EngineRPM",
    WARNING_LIGHTS_ID: "WarningLights",
}
