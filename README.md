# CarPC CAN Bus Simulation

A small end-to-end simulation of how vehicle software reads sensor/body data
off a CAN bus. Two "ECUs" broadcast messages (speed, RPM, doors, warning
lights), and either a terminal or a graphical dashboard decodes them and
displays live vehicle state — the same basic pattern used in real
instrument clusters and infotainment (CarPC) software.

```
ecu_sim.py  --(CAN frames: speed, RPM, doors, warnings)-->  dashboard_gui.py  (graphical - gauges, indicators)
                                                              dashboard.py      (terminal version)
                                                              logger.py         (optional CSV log)
signals.py  <- shared encode/decode logic (like a tiny DBC file)
```

## Graphical dashboard (`dashboard_gui.py`)

A real Tkinter GUI — analog speedometer and RPM gauge with needles and a
redline zone, door indicators, warning lights, a CAN connection-status
indicator, and a live vehicle-state text panel.

```bash
pip install -r requirements.txt
python3 dashboard_gui.py --demo              # zero-setup, in-process simulated ECU
python3 dashboard_gui.py --demo --dropout    # also demos the "NO SIGNAL" state
```

Against a real SocketCAN interface (see the SocketCAN section below):

```bash
python3 dashboard_gui.py --channel vcan0 --bustype socketcan
```

It shows, live:
- **Speedometer** — 0-220 km/h analog gauge
- **RPM gauge** — 0-8000 rpm with a redline arc above 6500
- **Door indicators** — FL/FR/RL/RR, turn red with an outline when open
- **Warning indicators** — check engine, engine temp, low fuel, seatbelt, battery
- **CAN connection status** — green "CONNECTED" / red "NO SIGNAL", based on
  whether a frame has arrived in the last 1.5 seconds (a real thing vehicle
  software has to handle — sensors/ECUs do drop off the bus)
- **Vehicle-state panel** — plain-text live readout of every decoded value,
  useful for debugging and for showing "here's the raw state" in an interview

`Gauge` in `dashboard_gui.py` is a small reusable class — pass it a
center point, radius, min/max, and optional redline, and it draws the face,
ticks, and a needle you can update every frame. Built with plain Tkinter
Canvas drawing, no image assets or extra dependencies.

## Terminal dashboard (`dashboard.py`)

A lighter, no-GUI-toolkit version that prints the same state to the
terminal. Useful for headless machines (e.g. a real Raspberry Pi CarPC over
SSH) or if you don't want a graphical dependency.

## Why this project

Real automotive software reads and writes signals over CAN: things like
vehicle speed, RPM, door/seatbelt status, and climate settings are all just
CAN frames with a defined arbitration ID and a byte layout. This project
simulates that pipeline so you can talk through, in an interview, exactly
how a message goes from "ECU sends bytes" to "dashboard shows a number" —
without needing real vehicle hardware.

## Quick start (no setup, works on any OS)

```bash
pip install -r requirements.txt
python3 run_demo.py --seconds 20
```

This runs a simulated ECU and the dashboard together in one process using
python-can's in-memory "virtual" bus. You'll see a live dashboard update
in your terminal with speed and door status.

To also log the traffic to CSV:

```bash
python3 logger.py --seconds 15 --out can_log.csv
```

## The "real" version (Linux, SocketCAN)

The quick-start demo uses an in-memory virtual bus so it works anywhere,
but it only works within a single Python process. To get a genuine
two-process setup — closer to real vehicle tooling, and a stronger talking
point in an interview — use Linux's built-in **SocketCAN** with a virtual
CAN interface (`vcan0`). This needs a real Linux machine (native Ubuntu,
WSL2 with a recent kernel, or a Raspberry Pi) since it uses a kernel module.

1. **Create the virtual CAN interface** (one-time per boot):
   ```bash
   sudo modprobe vcan
   sudo ip link add dev vcan0 type vcan
   sudo ip link set up vcan0
   ```

2. **Install can-utils** (the standard Linux CAN diagnostic tools):
   ```bash
   sudo apt install can-utils
   ```

3. **Run the ECU simulator in one terminal:**
   ```bash
   python3 ecu_sim.py --channel vcan0 --bustype socketcan
   # add --dropout to periodically simulate a CAN dropout
   ```

4. **Run the dashboard in another terminal** (graphical or terminal version):
   ```bash
   python3 dashboard_gui.py --channel vcan0 --bustype socketcan
   # or: python3 dashboard.py --channel vcan0 --bustype socketcan
   ```

5. **(Optional) Watch the raw traffic with can-utils**, exactly as you
   would on a real vehicle bus:
   ```bash
   candump vcan0
   ```
   You'll see raw frames like `vcan0  100   [8]  3C 00 00 00 00 00 00 00`
   — that's `ID=0x100` (VehicleSpeed), and byte 0 (`0x3C` = 60 decimal) is
   the speed in kph, matching what `signals.py` encodes/decodes.

6. **(Optional) Inject a frame manually** to see the dashboard react in
   real time:
   ```bash
   cansend vcan0 101#08.00.00.00.00.00.00.00   # sets front_right door open
   ```

This SocketCAN path is what makes the project genuinely resume-worthy —
`candump`/`cansend` are real tools used in automotive software development,
and `vcan0` behaves identically to a real `can0` hardware interface from
the application's point of view.

## How the signals are defined (`signals.py`)

Real automotive CAN buses are described by **DBC files**: a mapping from
arbitration ID → named signals, each with a bit position, length, scale,
and offset, so raw bytes turn into physical units. `signals.py` is a tiny,
hand-written version of exactly that idea for two messages:

| Arbitration ID | Name          | Signal(s)                                          |
|-----------------|---------------|----------------------------------------------------|
| `0x100`         | VehicleSpeed  | `speed_kph` — 1 byte, 0–255                         |
| `0x101`         | DoorStatus    | 4 bits — front-left/right, rear-left/right          |
| `0x102`         | EngineRPM     | `rpm` — 2 bytes little-endian, 0–8000               |
| `0x103`         | WarningLights | 5 bits — check engine, low fuel, engine temp, seatbelt, battery |

If you want to go further, look at the `cantools` library, which reads
real `.dbc` files and gives you the same encode/decode API — a natural
next step after this project.

## Files

- `signals.py` — message/signal definitions and encode/decode functions
- `ecu_sim.py` — simulates ECUs sending CAN frames (standalone or imported)
- `dashboard_gui.py` — graphical dashboard: gauges, indicators, connection status
- `dashboard.py` — terminal dashboard (no GUI toolkit needed)
- `logger.py` — logs decoded frames to CSV
- `run_demo.py` — zero-setup terminal demo running everything in one process
- `requirements.txt` — Python dependencies (`dashboard_gui.py` also needs
  Tkinter, which ships with most Python installs — on Debian/Ubuntu:
  `sudo apt install python3-tk`)

## Possible extensions

- Add more signals (RPM, fuel level, seatbelt status)
- Read real `.dbc` files with `cantools` instead of hand-written encoding
- Replace the terminal dashboard with a simple Tkinter/PyQt GUI
- Log to SQLite instead of CSV and add a query/replay tool
- Add basic CAN error-frame or bus-load simulation
