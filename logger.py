"""
logger.py

Logs every decoded CAN frame to a CSV file - similar to what tools like
candump/asammdf do in real vehicle development, just simplified.

Usage:
    python3 logger.py --seconds 15 --out can_log.csv
"""

import argparse
import csv
import threading
import time

import can

from signals import (
    VEHICLE_SPEED_ID,
    DOOR_STATUS_ID,
    decode_vehicle_speed,
    decode_door_status,
    MESSAGE_NAMES,
)
from ecu_sim import simulate_ecus


def log_frames(channel: str, bustype: str, out_path: str, stop_event: threading.Event):
    bus = can.interface.Bus(channel=channel, bustype=bustype)
    print(f"[logger] Logging to {out_path} ...")

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "arbitration_id_hex", "message_name", "decoded"])

        try:
            while not stop_event.is_set():
                msg = bus.recv(timeout=1.0)
                if msg is None:
                    continue

                name = MESSAGE_NAMES.get(msg.arbitration_id, "Unknown")
                if msg.arbitration_id == VEHICLE_SPEED_ID:
                    decoded = f"speed_kph={decode_vehicle_speed(msg.data):.1f}"
                elif msg.arbitration_id == DOOR_STATUS_ID:
                    decoded = str(decode_door_status(msg.data))
                else:
                    decoded = msg.data.hex()

                writer.writerow([f"{msg.timestamp:.3f}", hex(msg.arbitration_id), name, decoded])
                f.flush()
        finally:
            bus.shutdown()
            print("[logger] Stopped.")


def main():
    parser = argparse.ArgumentParser(description="Log simulated CAN traffic to CSV")
    parser.add_argument("--seconds", type=float, default=15, help="How long to log for")
    parser.add_argument("--out", default="can_log.csv", help="Output CSV path")
    parser.add_argument("--channel", default="carpc-demo", help="CAN channel (virtual demo channel)")
    args = parser.parse_args()

    stop_event = threading.Event()

    ecu_thread = threading.Thread(
        target=simulate_ecus,
        kwargs={"channel": args.channel, "bustype": "virtual", "stop_event": stop_event},
        daemon=True,
    )
    ecu_thread.start()
    time.sleep(0.2)

    def stop_after(seconds):
        time.sleep(seconds)
        stop_event.set()

    timer_thread = threading.Thread(target=stop_after, args=(args.seconds,), daemon=True)
    timer_thread.start()

    try:
        log_frames(args.channel, "virtual", args.out, stop_event)
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        print(f"[logger] Done. Wrote {args.out}")


if __name__ == "__main__":
    main()
