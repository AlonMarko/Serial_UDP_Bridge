# Serial to UDP Bridge

This project provides a Serial to UDP bridge that forwards data between a serial port and a UDP socket. It comes in two versions: a GUI-based version using Tkinter and a command-line version suitable for running on a Raspberry Pi or other Linux systems.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [GUI Version](#gui-version)
  - [Command-Line Version](#command-line-version)
- [Configuration](#configuration)
- [Systemd Service](#systemd-service)
- [License](#license)

## Features

- Forwards data from a serial port to a UDP socket and vice versa.
- Configurable serial port settings (baud rate, etc.).
- Configurable UDP settings (target IP, target port, etc.).
- GUI version for easy configuration and monitoring.
- Command-line version for use in headless environments like Raspberry Pi.

## Requirements

- Python 3.x
- `pyserial` library
- `tkinter` library (for the GUI version)

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/serial-to-udp-bridge.git
    cd serial-to-udp-bridge
    ```

2. Install the required Python packages:
    ```sh
    pip install pyserial
    ```

## Usage

### GUI Version

1. **Running the GUI Application:**

    ```sh
    python app_gui.py
    ```

2. **Configuring the Bridge:**

    - Enter the serial port, baud rate, target IP, target port, sampling interval, and listening UDP port.
    - Click "Start Bridge" to start forwarding data.
    - Click "Stop Bridge" to stop forwarding data.
    - Click "Clear Log" to clear the log window.

### Command-Line Version

1. **Running the Command-Line Application:**

    ```sh
    python app_cli.py --config path/to/config.ini
    ```

2. **Overriding Configuration Settings:**

    You can override specific settings from the command line. For example:

    ```sh
    python app_cli.py --config path/to/config.ini --serial-port /dev/ttyUSB1 --baud-rate 115200 --target-ip 192.168.1.101 --target-port 54321 --listen-port 54321 --interval 2000
    ```

### Configuration

The configuration file (`config.ini`) contains default settings for the application:

```ini
[Settings]
serial_port = /dev/ttyUSB0
baud_rate = 9600
target_ip = 192.168.1.100
target_port = 12345
listen_port = 12345
interval = 1000
```

Create or edit the config.ini file to match your setup.

### Systemd Service

You can set up the command-line version to run as a systemd service on Linux:

1. Create a Systemd Service File:
    ```sh
    sudo nano /etc/systemd/system/serial_to_udp.service```
2. Add the Following Configuration:
   ```ini
    [Unit]
    Description=Serial to UDP Bridge
    After=network.target

    [Service]
    ExecStart=/usr/bin/python3 /path/to/your/app_cli.py --config /path/to/your/config.ini
    ExecReload=/bin/kill -HUP $MAINPID
    Restart=always
    User=pi
    Group=pi
    
    [Install]
    WantedBy=multi-user.target
    ```










