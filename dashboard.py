"""
dashboard.py

Listens on the CAN bus, decodes incoming frames using signals.py, and
prints a live-updating "dashboard" view - similar in spirit to what a
CarPC cluster application does: turn raw CAN traffic into human-readable
vehicle state.

Run standalone against a real (or virtual) CAN interface:
    python3 dashboard.py                                   # vcan0 / socketcan (default)
    python3 dashboard.py --channel can0 --bustype socketcan # real CAN hardware

Or import listen_and_render() from another script (see run_demo.py).
"""

import argparse
import shutil
import threading
import time

import can

from signals import (
    VEHICLE_SPEED_ID,
    DOOR_STATUS_ID,
    decode_vehicle_speed,
    decode_door_status,
)


def build_bus(channel: str, bustype: str):
    return can.interface.Bus(channel=channel, bustype=bustype)


def render(state):
    width = shutil.get_terminal_size((60, 20)).columns
    line = "-" * min(width, 46)
    speed = state.get("speed_kph")
    doors = state.get("doors", {})

    print("\n" + line)
    print(" CARPC DASHBOARD (simulated)")
    print(line)
    if speed is not None:
        bar_len = int(min(speed, 160) / 160 * 30)
        bar = "#" * bar_len + "." * (30 - bar_len)
        print(f" Speed:  {speed:6.1f} kph  [{bar}]")
    else:
        print(" Speed:  -- kph (waiting for data)")

    def d(name, key):
        state_str = "OPEN" if doors.get(key) else "closed"
        marker = "!" if doors.get(key) else " "
        print(f"   {marker} {name:<12} {state_str}")

    print(" Doors:")
    d("Front Left", "front_left")
    d("Front Right", "front_right")
    d("Rear Left", "rear_left")
    d("Rear Right", "rear_right")
    print(line)


def listen_and_render(channel: str, bustype: str, stop_event: threading.Event = None, max_frames: int = None):
    bus = build_bus(channel, bustype)
    print(f"[dashboard] Listening on channel='{channel}' bustype='{bustype}'")

    state = {"speed_kph": None, "doors": {}}
    last_render = 0.0
    frame_count = 0

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                break

            msg = bus.recv(timeout=1.0)
            if msg is None:
                continue

            frame_count += 1
            if msg.arbitration_id == VEHICLE_SPEED_ID:
                state["speed_kph"] = decode_vehicle_speed(msg.data)
            elif msg.arbitration_id == DOOR_STATUS_ID:
                state["doors"] = decode_door_status(msg.data)

            now = time.time()
            if now - last_render > 0.3:  # throttle redraws
                render(state)
                last_render = now

            if max_frames and frame_count >= max_frames:
                print(f"[dashboard] Reached max-frames={max_frames}, stopping.")
                break
    except KeyboardInterrupt:
        pass
    finally:
        bus.shutdown()
        print("[dashboard] Stopped.")


def main():
    parser = argparse.ArgumentParser(description="Decode and display CAN frames")
    parser.add_argument("--channel", default="vcan0", help="CAN channel name")
    parser.add_argument("--bustype", default="socketcan", help="e.g. socketcan (Linux vcan/can), virtual")
    parser.add_argument("--max-frames", type=int, default=None, help="Stop after N frames")
    args = parser.parse_args()
    listen_and_render(args.channel, args.bustype, max_frames=args.max_frames)


if __name__ == "__main__":
    main()
