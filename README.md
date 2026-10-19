# P-SAGRO

P-SAGRO (Precision Smart Agriculture ROS-Oriented platform) is a lab-scale smart agriculture testbed developed at the ITU Smart Agriculture & IoT Lab (SAILAB) as part of an M.Sc. thesis. This repository is the ROS 2 workspace for the testbed: an Arduino firmware that drives four pumps and reads two flow sensors and a temperature/humidity sensor, a ROS 2 serial bridge to that firmware, operator interfaces (RViz interactive markers and a Tkinter monitor), and a URDF model of the platform.

**Status:** under active development; not yet ported to ROS 2 Jazzy.

Author: Erdem Bahadır

## Hardware

As used by the firmware and nodes in this repository:

| Component | Quantity | Connection (firmware) |
|---|---|---|
| Arduino-compatible microcontroller | 1 | USB serial, 115200 baud (default port `/dev/ttyUSB0`) |
| Pump outputs | 4 | Digital pins 14, 15, 16, 17 (HIGH = on) |
| ZJ-S401 flow sensors | 2 | Interrupt pins 2 and 3 (rising edge, internal pull-up) |
| DHT11 temperature/humidity sensor | 1 | Pin 4 |

The mechanical model is a single static link (`base_link`) exported from SolidWorks as `meshes/base_link.STL`.

## Packages

| Package | Build type | Description |
|---|---|---|
| `psagro_control` | ament_python | Serial bridge to the pump controller, RViz interactive markers for the pumps, and a Tkinter flow/climate monitor. |
| `psagro_description` | ament_cmake | URDF model, mesh, RViz config, and launch files for RViz, Gazebo Classic, and Ignition Gazebo Fortress. |

### Nodes (`psagro_control`)

| Node | Subscribes | Publishes | Parameters |
|---|---|---|---|
| `arduino_bridge` | `/pump_command` | `/pump_status`, `/flow`, `/climate` | `port` (default `/dev/ttyUSB0`), `baud` (default `115200`) |
| `pump_interactive` | `/pump_status` | `/pump_command` | `pump_positions`, `marker_scale`, `frame_id` (default `base_link`) |
| `flow_monitor` | `/flow`, `/climate`, `/pump_status` | `/pump_command` | none |

All topics use `std_msgs/String` and carry the raw serial protocol lines described below.

- `arduino_bridge` forwards each `/pump_command` message to the serial port and routes incoming lines by prefix: `FLOW,` lines to `/flow`, `CLIMATE,` lines to `/climate`, all other lines to `/pump_status`. If the port is unavailable it retries every 2 s. On shutdown it sends `ALL_OFF`.
- `pump_interactive` shows one interactive marker per pump in RViz (server name `pump_markers`). The right-click menu turns a pump on, turns it off, or runs it for 5 s. Marker color follows the reported pump state. The node publishes `STATUS` every 2 s to poll the controller.
- `flow_monitor` is a Tkinter window that shows flow rate, accumulated volume and pulse count per sensor, plus temperature and humidity, and has buttons for pump commands. It recomputes flow using 5880 pulses per liter for each sensor.

Code comments, log messages and GUI labels are in Turkish.

## Firmware

`firmware/pump_controller/pump_controller.ino` is an Arduino sketch. It requires a library that provides `DHT.h`.

Serial: 115200 baud, newline-terminated ASCII. Commands are case-insensitive.

| Command | Effect | Response |
|---|---|---|
| `P<n>_ON` | Turn pump `n` (1–4) on for up to the maximum on-time | `ACK:P<n>_ON` |
| `P<n>_OFF` | Turn pump `n` off | `ACK:P<n>_OFF` |
| `P<n>_RUN_<ms>` | Run pump `n` for `<ms>` milliseconds | `ACK:P<n>_RUN_<ms>` |
| `ALL_ON` | Turn all pumps on for up to the maximum on-time | `ACK:ALL_ON` |
| `ALL_OFF` | Turn all pumps off | `ACK:ALL_OFF` |
| `STATUS` | Report pump states | `STATUS,<p1>,<p2>,<p3>,<p4>` (1 = on) |

Messages sent by the firmware without a command:

| Message | When |
|---|---|
| `READY` | After setup |
| `OFF:P<n>` | A pump's run time has expired |
| `FLOW,<sensor>,<pulses>,<L/min>` | Every 1 s for each flow sensor (pulse count since the last report) |
| `CLIMATE,<temp_C>,<humidity_%>` or `CLIMATE,ERR` | Every 2 s |
| `ERR:BAD_CMD`, `ERR:BAD_PUMP`, `ERR:UNKNOWN` | Invalid command |

Every pump activation is limited to 300 s (`MAX_ON_MS`); a run time of 0 or above the limit is set to the limit. The flow calibration constant `PULSES_PER_LITER` is 5880 and is marked for calibration in the source.

## Requirements

Built and tested with:

- Ubuntu 22.04
- ROS 2 Humble

Additional dependencies used by the code:

- `python3-serial` (pyserial) for `arduino_bridge`
- `python3-tk` for `flow_monitor`
- `gazebo_ros` (Gazebo Classic) for `gazebo.launch.py`
- `ros_gz_sim` and `ros_gz_bridge` (Ignition Gazebo Fortress) for `gz_sim.launch.py`

`python3-serial`, `python3-tk`, `ros_gz_sim` and `ros_gz_bridge` are not yet declared in `package.xml`, so `rosdep` will not install them.

## Build

```bash
source /opt/ros/humble/setup.bash
cd ~/psagro_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

## Run

Hardware bringup (serial bridge, pump interactive markers, robot_state_publisher and RViz):

```bash
ros2 launch psagro_control psagro_bringup.launch.py port:=/dev/ttyUSB0 baud:=115200
```

Flow and climate monitor (no launch file):

```bash
ros2 run psagro_control flow_monitor
```

Model visualization in RViz:

```bash
ros2 launch psagro_description display.launch.py
```

Simulation, Gazebo Classic (the model is spawned after 10 s):

```bash
ros2 launch psagro_description gazebo.launch.py
```

Simulation, Ignition Gazebo Fortress (empty world; the model is spawned after 6 s and `/clock` is bridged):

```bash
ros2 launch psagro_description gz_sim.launch.py
```

## Repository structure

```
psagro_ws/
├── firmware/
│   └── pump_controller/
│       └── pump_controller.ino
└── src/
    ├── psagro_control/
    │   ├── launch/psagro_bringup.launch.py
    │   ├── psagro_control/
    │   │   ├── arduino_bridge.py
    │   │   ├── flow_monitor.py
    │   │   └── pump_interactive.py
    │   ├── test/
    │   ├── package.xml
    │   ├── setup.cfg
    │   └── setup.py
    └── psagro_description/
        ├── launch/
        │   ├── display.launch.py
        │   ├── gazebo.launch.py
        │   └── gz_sim.launch.py
        ├── meshes/base_link.STL
        ├── rviz/psagro.rviz
        ├── urdf/psagro.urdf
        ├── CMakeLists.txt
        ├── LICENSE
        └── package.xml
```
