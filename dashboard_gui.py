"""
dashboard_gui.py

A real graphical CarPC-style dashboard built with Tkinter (no extra
dependencies beyond python-can). Draws:

  - Speedometer (0-220 kph)
  - RPM gauge (0-8000, redline above 6500)
  - Door indicators (FL / FR / RL / RR)
  - Warning indicators (check engine, low fuel, engine temp, seatbelt, battery)
  - CAN connection status (goes red if no frames arrive for >1.5s)
  - Vehicle-state panel (live text readout of every decoded value)

Run against a real/virtual SocketCAN interface:
    python3 dashboard_gui.py --channel vcan0 --bustype socketcan

Or zero-setup demo mode (spins up a simulated ECU in-process, no CAN
interface needed at all):
    python3 dashboard_gui.py --demo
    python3 dashboard_gui.py --demo --dropout   # also demos connection loss
"""

import argparse
import math
import threading
import time
import tkinter as tk

import can

from signals import (
    VEHICLE_SPEED_ID,
    DOOR_STATUS_ID,
    ENGINE_RPM_ID,
    WARNING_LIGHTS_ID,
    decode_vehicle_speed,
    decode_door_status,
    decode_engine_rpm,
    decode_warning_lights,
)
from ecu_sim import simulate_ecus

# ---------------------------------------------------------------- palette --
BG = "#101317"
PANEL_BG = "#181c22"
FACE = "#1d232b"
FG = "#e8ecf1"
DIM = "#5b6672"
ACCENT = "#37c2ff"
GREEN = "#39d98a"
AMBER = "#ffb545"
RED = "#ff4d4d"
NEEDLE = "#ff4d4d"
TICK = "#3d4652"

CONNECTION_TIMEOUT = 1.5  # seconds with no frames -> "NO SIGNAL"


# ------------------------------------------------------------- shared state -
class VehicleState:
    """Thread-safe holder for the latest decoded values."""

    def __init__(self):
        self.lock = threading.Lock()
        self.speed_kph = 0.0
        self.rpm = 0.0
        self.doors = {"front_left": False, "front_right": False, "rear_left": False, "rear_right": False}
        self.warnings = {"check_engine": False, "low_fuel": False, "engine_temp": False,
                          "seatbelt": False, "battery": False}
        self.last_frame_time = None
        self.frame_count = 0

    def snapshot(self):
        with self.lock:
            return {
                "speed_kph": self.speed_kph,
                "rpm": self.rpm,
                "doors": dict(self.doors),
                "warnings": dict(self.warnings),
                "last_frame_time": self.last_frame_time,
                "frame_count": self.frame_count,
            }


def can_listener(channel, bustype, state: VehicleState, stop_event: threading.Event):
    """Background thread: reads CAN frames and updates shared state."""
    bus = can.interface.Bus(channel=channel, bustype=bustype)
    try:
        while not stop_event.is_set():
            msg = bus.recv(timeout=0.3)
            if msg is None:
                continue
            with state.lock:
                state.last_frame_time = time.time()
                state.frame_count += 1
                if msg.arbitration_id == VEHICLE_SPEED_ID:
                    state.speed_kph = decode_vehicle_speed(msg.data)
                elif msg.arbitration_id == ENGINE_RPM_ID:
                    state.rpm = decode_engine_rpm(msg.data)
                elif msg.arbitration_id == DOOR_STATUS_ID:
                    state.doors = decode_door_status(msg.data)
                elif msg.arbitration_id == WARNING_LIGHTS_ID:
                    state.warnings = decode_warning_lights(msg.data)
    finally:
        bus.shutdown()


# ------------------------------------------------------------- gauge widget -
class Gauge:
    """A circular analog gauge drawn on a Canvas: face, ticks, redline arc,
    a needle that's cheaply updated each frame, and a digital readout."""

    def __init__(self, canvas, cx, cy, radius, min_val, max_val, redline_start=None,
                 major_step=20, unit="", label=""):
        self.canvas = canvas
        self.cx, self.cy, self.radius = cx, cy, radius
        self.min_val, self.max_val = min_val, max_val
        self.start_angle = 210   # degrees, math convention (0 = 3 o'clock, CCW positive)
        self.sweep = 240         # total degrees covered end-to-end

        # Face
        canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                            fill=FACE, outline=TICK, width=2)

        # Redline arc (drawn under the ticks)
        if redline_start is not None:
            a0 = self._angle_for(redline_start)
            extent = a0 - self._angle_for(max_val)
            canvas.create_arc(cx - radius + 10, cy - radius + 10, cx + radius - 10, cy + radius - 10,
                               start=self._angle_for(max_val), extent=extent,
                               style="arc", outline=RED, width=6)

        # Tick marks + numeric labels
        val = min_val
        while val <= max_val + 1e-6:
            ang = math.radians(self._angle_for(val))
            x1 = cx + (radius - 8) * math.cos(ang)
            y1 = cy - (radius - 8) * math.sin(ang)
            x2 = cx + (radius - 20) * math.cos(ang)
            y2 = cy - (radius - 20) * math.sin(ang)
            canvas.create_line(x1, y1, x2, y2, fill=DIM, width=2)
            lx = cx + (radius - 34) * math.cos(ang)
            ly = cy - (radius - 34) * math.sin(ang)
            canvas.create_text(lx, ly, text=str(int(val)), fill=DIM, font=("Consolas", 9))
            val += major_step

        # Unit + name label under center
        canvas.create_text(cx, cy + radius * 0.45, text=unit, fill=DIM, font=("Consolas", 10))
        canvas.create_text(cx, cy + radius + 16, text=label, fill=FG, font=("Consolas", 11, "bold"))

        # Digital readout
        self.readout_id = canvas.create_text(cx, cy + radius * 0.2, text="0",
                                              fill=FG, font=("Consolas", 22, "bold"))

        # Needle + hub (updated every refresh)
        nx, ny = self._needle_end(min_val)
        self.needle_id = canvas.create_line(cx, cy, nx, ny, fill=NEEDLE, width=3)
        canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, fill="#c9ccd1", outline=TICK)

    def _angle_for(self, value):
        value = max(self.min_val, min(self.max_val, value))
        frac = (value - self.min_val) / (self.max_val - self.min_val)
        return self.start_angle - frac * self.sweep

    def _needle_end(self, value):
        ang = math.radians(self._angle_for(value))
        r = self.radius - 16
        return self.cx + r * math.cos(ang), self.cy - r * math.sin(ang)

    def update(self, value, readout_text=None):
        nx, ny = self._needle_end(value)
        self.canvas.coords(self.needle_id, self.cx, self.cy, nx, ny)
        self.canvas.itemconfig(self.readout_id, text=readout_text if readout_text is not None else str(int(value)))


# ------------------------------------------------------------------ app ----
class DashboardApp(tk.Tk):
    def __init__(self, state: VehicleState):
        super().__init__()
        self.state = state
        self.title("CarPC Dashboard")
        self.configure(bg=BG)
        self.geometry("1040x640")
        self.resizable(False, False)

        self._build_top_bar()
        self._build_gauges()
        self._build_doors_panel()
        self._build_warnings_panel()
        self._build_state_panel()

        self.after(100, self.refresh)

    # -- layout ------------------------------------------------------------
    def _build_top_bar(self):
        bar = tk.Frame(self, bg=BG)
        bar.place(x=20, y=14, width=1000, height=30)
        tk.Label(bar, text="CARPC  DASHBOARD", bg=BG, fg=FG,
                 font=("Consolas", 15, "bold")).pack(side="left")

        self.conn_dot = tk.Canvas(bar, width=14, height=14, bg=BG, highlightthickness=0)
        self.conn_dot.pack(side="right", padx=(6, 0))
        self.conn_dot_id = self.conn_dot.create_oval(2, 2, 12, 12, fill=RED, outline="")
        self.conn_label = tk.Label(bar, text="NO SIGNAL", bg=BG, fg=RED, font=("Consolas", 11, "bold"))
        self.conn_label.pack(side="right", padx=8)

    def _build_gauges(self):
        canvas = tk.Canvas(self, width=680, height=330, bg=BG, highlightthickness=0)
        canvas.place(x=20, y=60)
        self.speedo = Gauge(canvas, cx=175, cy=155, radius=140, min_val=0, max_val=220,
                             major_step=20, unit="km/h", label="SPEED")
        self.rpm_gauge = Gauge(canvas, cx=505, cy=155, radius=140, min_val=0, max_val=8000,
                                redline_start=6500, major_step=1000, unit="x1000 rpm", label="ENGINE")
        self.gauge_canvas = canvas

    def _build_doors_panel(self):
        frame = tk.Frame(self, bg=PANEL_BG, highlightbackground=TICK, highlightthickness=1)
        frame.place(x=20, y=410, width=330, height=200)
        tk.Label(frame, text="DOORS", bg=PANEL_BG, fg=DIM, font=("Consolas", 10, "bold")).place(x=12, y=8)

        # Simple top-down car layout: FL/FR up top, RL/RR below
        self.door_labels = {}
        positions = {
            "front_left": (30, 45), "front_right": (200, 45),
            "rear_left": (30, 115), "rear_right": (200, 115),
        }
        names = {"front_left": "FRONT L", "front_right": "FRONT R",
                 "rear_left": "REAR L", "rear_right": "REAR R"}
        for key, (x, y) in positions.items():
            box = tk.Canvas(frame, width=110, height=55, bg=PANEL_BG, highlightthickness=0)
            box.place(x=x, y=y)
            rect_id = box.create_rectangle(2, 2, 108, 53, fill=FACE, outline=TICK, width=1)
            text_id = box.create_text(55, 20, text=names[key], fill=DIM, font=("Consolas", 9, "bold"))
            state_id = box.create_text(55, 38, text="CLOSED", fill=GREEN, font=("Consolas", 10, "bold"))
            self.door_labels[key] = (box, rect_id, text_id, state_id)

    def _build_warnings_panel(self):
        frame = tk.Frame(self, bg=PANEL_BG, highlightbackground=TICK, highlightthickness=1)
        frame.place(x=360, y=410, width=340, height=200)
        tk.Label(frame, text="WARNINGS", bg=PANEL_BG, fg=DIM, font=("Consolas", 10, "bold")).place(x=12, y=8)

        self.warning_items = {}
        labels = [
            ("check_engine", "CHECK ENGINE"),
            ("engine_temp", "ENGINE TEMP"),
            ("low_fuel", "LOW FUEL"),
            ("seatbelt", "SEATBELT"),
            ("battery", "BATTERY"),
        ]
        y = 40
        for key, text in labels:
            row = tk.Canvas(frame, width=310, height=28, bg=PANEL_BG, highlightthickness=0)
            row.place(x=12, y=y)
            dot_id = row.create_oval(2, 6, 18, 22, fill="#2a323c", outline="")
            label_id = row.create_text(30, 14, text=text, fill=DIM, font=("Consolas", 10), anchor="w")
            self.warning_items[key] = (row, dot_id, label_id)
            y += 30

    def _build_state_panel(self):
        frame = tk.Frame(self, bg=PANEL_BG, highlightbackground=TICK, highlightthickness=1)
        frame.place(x=720, y=60, width=300, height=550)
        tk.Label(frame, text="VEHICLE STATE", bg=PANEL_BG, fg=DIM, font=("Consolas", 10, "bold")).place(x=12, y=8)

        self.state_text = tk.Text(frame, width=32, height=30, bg=PANEL_BG, fg=FG,
                                   font=("Consolas", 10), bd=0, highlightthickness=0)
        self.state_text.place(x=12, y=34)
        self.state_text.configure(state="disabled")

    # -- refresh loop --------------------------------------------------------
    def refresh(self):
        snap = self.state.snapshot()

        # Gauges
        self.speedo.update(snap["speed_kph"], f"{snap['speed_kph']:.0f}")
        self.rpm_gauge.update(snap["rpm"], f"{snap['rpm']:.0f}")

        # Doors
        for key, (box, rect_id, text_id, state_id) in self.door_labels.items():
            open_ = snap["doors"].get(key, False)
            box.itemconfig(rect_id, outline=RED if open_ else TICK, width=2 if open_ else 1)
            box.itemconfig(state_id, text="OPEN" if open_ else "CLOSED", fill=RED if open_ else GREEN)

        # Warnings
        for key, (row, dot_id, label_id) in self.warning_items.items():
            active = snap["warnings"].get(key, False)
            color = AMBER if key not in ("check_engine", "engine_temp") else RED
            row.itemconfig(dot_id, fill=color if active else "#2a323c")
            row.itemconfig(label_id, fill=FG if active else DIM)

        # CAN connection status
        last = snap["last_frame_time"]
        connected = last is not None and (time.time() - last) < CONNECTION_TIMEOUT
        self.conn_dot.itemconfig(self.conn_dot_id, fill=GREEN if connected else RED)
        self.conn_label.configure(text="CONNECTED" if connected else "NO SIGNAL",
                                   fg=GREEN if connected else RED)

        # Vehicle-state text panel
        doors_open = [k.replace("_", " ").upper() for k, v in snap["doors"].items() if v]
        warnings_on = [k.replace("_", " ").upper() for k, v in snap["warnings"].items() if v]
        age = f"{time.time() - last:.1f}s ago" if last else "never"
        lines = [
            f"CAN status : {'CONNECTED' if connected else 'NO SIGNAL'}",
            f"Last frame : {age}",
            f"Frames rx  : {snap['frame_count']}",
            "",
            f"Speed      : {snap['speed_kph']:.1f} km/h",
            f"RPM        : {snap['rpm']:.0f}",
            "",
            "Doors open :",
            *(["  - " + d for d in doors_open] if doors_open else ["  (none)"]),
            "",
            "Warnings   :",
            *(["  ! " + w for w in warnings_on] if warnings_on else ["  (none)"]),
        ]
        self.state_text.configure(state="normal")
        self.state_text.delete("1.0", "end")
        self.state_text.insert("1.0", "\n".join(lines))
        self.state_text.configure(state="disabled")

        self.after(100, self.refresh)


def main():
    parser = argparse.ArgumentParser(description="CarPC-style graphical dashboard")
    parser.add_argument("--channel", default="vcan0", help="CAN channel name")
    parser.add_argument("--bustype", default="socketcan", help="e.g. socketcan (Linux vcan/can), virtual")
    parser.add_argument("--demo", action="store_true",
                         help="Zero-setup mode: run a simulated ECU in-process (no CAN interface needed)")
    parser.add_argument("--dropout", action="store_true",
                         help="With --demo, periodically simulate a CAN dropout to test the connection indicator")
    args = parser.parse_args()

    state = VehicleState()
    stop_event = threading.Event()

    channel = args.channel
    bustype = args.bustype
    if args.demo:
        channel, bustype = "carpc-gui-demo", "virtual"
        ecu_thread = threading.Thread(
            target=simulate_ecus,
            kwargs={"channel": channel, "bustype": bustype, "stop_event": stop_event,
                    "simulate_dropout": args.dropout},
            daemon=True,
        )
        ecu_thread.start()
        time.sleep(0.2)

    listener_thread = threading.Thread(
        target=can_listener, args=(channel, bustype, state, stop_event), daemon=True
    )
    listener_thread.start()

    app = DashboardApp(state)
    try:
        app.mainloop()
    finally:
        stop_event.set()


if __name__ == "__main__":
    main()
