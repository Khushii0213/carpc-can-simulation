"""
run_demo.py

Zero-setup demo: runs the simulated ECU and the dashboard in the same
process (on two threads), using python-can's in-memory "virtual" bus.
No Linux, no root, no kernel modules needed - works on Windows/Mac/Linux.

This is the fastest way to see the whole pipeline work end to end.
For the "real" version using actual SocketCAN (closer to what you'd use
on real automotive hardware/tooling), see README.md.

Usage:
    python3 run_demo.py
    python3 run_demo.py --seconds 15
"""

import argparse
import threading
import time

import can

from ecu_sim import simulate_ecus
from dashboard import listen_and_render


def main():
    parser = argparse.ArgumentParser(description="Run the CAN demo end-to-end, no setup required")
    parser.add_argument("--seconds", type=float, default=20, help="How long to run the demo")
    args = parser.parse_args()

    channel = "carpc-demo"

    stop_event = threading.Event()

    dashboard_thread = threading.Thread(
        target=listen_and_render,
        kwargs={"channel": channel, "bustype": "virtual", "stop_event": stop_event},
        daemon=True,
    )
    dashboard_thread.start()

    time.sleep(0.3)  # let the dashboard subscribe before we start sending

    ecu_thread = threading.Thread(
        target=simulate_ecus,
        kwargs={"channel": channel, "bustype": "virtual", "stop_event": stop_event},
        daemon=True,
    )
    ecu_thread.start()

    try:
        time.sleep(args.seconds)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[run_demo] Stopping...")
        stop_event.set()
        time.sleep(0.5)


if __name__ == "__main__":
    main()
