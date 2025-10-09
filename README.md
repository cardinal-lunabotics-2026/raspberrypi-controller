# Raspberry Pi Controller

This repository contains the Python software running on the Raspberry Pi for the Cardinal Lunabotics 2026 robot.
The Pi acts as the bridge between the mission control system (laptop) and the Arduino controller.

## Overview
- Communicates with the Arduino via USB serial to send motor and actuator commands.
- Connects to the mission control laptop over Wi-Fi/Ethernet to receive control commands.
- Executes control logic, relays sensor feedback, and manages basic automation tasks(Optional).
