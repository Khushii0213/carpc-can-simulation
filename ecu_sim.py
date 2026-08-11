"""
ecu_sim.py

Simulates two ECUs broadcasting on the CAN bus:
  - A "speed sensor" ECU sending VehicleSpeed every ~100 ms, oscillating
    like a car accelerating/decelerating.
  - A "body control module" sending DoorStatus every ~500 ms, occasionally
    toggling a door open/closed.

Run standalone against a real (or virtual) CAN interface:
    python3 ecu_sim.py                                   # vcan0 / socketcan (default)
    python3 ecu_sim.py --channel can0 --bustype socketcan # real CAN hardware

Or import simulate_ecus() from another script (see run_demo.py).
"""

import argparse
import math
import random
import threading
import time

import can

from signals import (
    VEHICLE_SPEED_ID,
    DOOR_STATUS_ID,
    ENGINE_RPM_ID,
    WARNING_LIGHTS_ID,
    encode_vehicle_speed,
    encode_door_status,
    encode_engine_rpm,
    encode_warning_lights,
)


def build_bus(channel: str, bustype: str):
    return can.interface.Bus(channel=channel, bustype=bustype)


def simulate_ecus(
    channel: str,
    bustype: str,
    stop_event: threading.Event = None,
    duration: float = None,
    simulate_dropout: bool = False,
):
    """Send simulated VehicleSpeed, EngineRPM, DoorStatus, and WarningLights
    frames until stopped.

    stop_event: threading.Event - if given, stop when it's set (used by run_demo.py)
    duration: float seconds - if given (and no stop_event), stop after this long
    simulate_dropout: if True, periodically stop sending for a few seconds to
        demo the dashboard's CAN-connection-lost indicator
    """
    bus = build_bus(channel, bustype)
    print(f"[ecu_sim] Bus up on channel='{channel}' bustype='{bustype}'")
    print("[ecu_sim] Broadcasting VehicleSpeed (0x100), EngineRPM (0x102), "
          "DoorStatus (0x101), WarningLights (0x103)...")

    door_state = {"front_left": False, "front_right": False, "rear_left": False, "rear_right": False}
    warning_state = {"check_engine": False, "low_fuel": False, "engine_temp": False,
                      "seatbelt": True, "battery": False}
    fuel_percent = 55.0
    last_door_send = 0.0
    last_warning_send = 0.0
    t0 = time.time()

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            now = time.time()
            elapsed = now - t0
            if duration is not None and elapsed > duration:
                break

            # Simulate a periodic CAN dropout so the dashboard's connection
            # indicator has something real to react to.
            if simulate_dropout and int(elapsed) % 20 in (10, 11, 12, 13):
                time.sleep(0.1)
                continue

            # --- Speed: oscillate like real driving (~5-115 kph) ---
            speed = 60 + 55 * math.sin(elapsed / 6.0)
            bus.send(can.Message(
                arbitration_id=VEHICLE_SPEED_ID,
                data=encode_vehicle_speed(speed),
                is_extended_id=False,
            ))

            # --- RPM: roughly tracks speed (like a gear-linked engine),
            #     plus idle noise, so it doesn't look perfectly synthetic ---
            base_rpm = 900 + max(0, speed) * 45
            rpm = base_rpm + random.uniform(-80, 80)
            bus.send(can.Message(
                arbitration_id=ENGINE_RPM_ID,
                data=encode_engine_rpm(rpm),
                is_extended_id=False,
            ))

            # --- Doors: occasionally flip one open/closed ---
            if now - last_door_send > 0.5:
                if random.random() < 0.3:
                    key = random.choice(list(door_state.keys()))
                    door_state[key] = not door_state[key]
                bus.send(can.Message(
                    arbitration_id=DOOR_STATUS_ID,
                    data=encode_door_status(**door_state),
                    is_extended_id=False,
                ))
                last_door_send = now

            # --- Warnings: fuel drains slowly -> low_fuel below 15%;
            #     other lights toggle rarely to demo the indicator states ---
            if now - last_warning_send > 1.0:
                fuel_percent -= 0.4
                if fuel_percent < 0:
                    fuel_percent = 55.0  # refuel, loop the demo
                warning_state["low_fuel"] = fuel_percent < 15.0
                if random.random() < 0.05:
                    warning_state["check_engine"] = not warning_state["check_engine"]
                if random.random() < 0.03:
                    warning_state["engine_temp"] = not warning_state["engine_temp"]
                if random.random() < 0.1:
                    warning_state["seatbelt"] = not warning_state["seatbelt"]
                bus.send(can.Message(
                    arbitration_id=WARNING_LIGHTS_ID,
                    data=encode_warning_lights(**warning_state),
                    is_extended_id=False,
                ))
                last_warning_send = now

            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        bus.shutdown()
        print("[ecu_sim] Stopped.")


def main():
    parser = argparse.ArgumentParser(description="Simulate ECUs sending CAN frames")
    parser.add_argument("--channel", default="vcan0", help="CAN channel name")
    parser.add_argument("--bustype", default="socketcan", help="e.g. socketcan (Linux vcan/can), virtual")
    parser.add_argument("--dropout", action="store_true", help="Periodically simulate a CAN dropout")
    args = parser.parse_args()
    simulate_ecus(args.channel, args.bustype, simulate_dropout=args.dropout)


if __name__ == "__main__":
    main()
