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
    git clone https://github.com/AlonMarko/Serial_UDP_Bridge.git
    cd Serial_UDP_Bridge
    ```

2. Install the required Python packages:
    ```sh
    pip install pyserial
    ```

## Usage

### GUI Version

1. **Running the GUI Application:**

    ```sh
    python app.py
    ```

2. **Configuring the Bridge:**

    - Edit Settings for the serial port and connections.
    - The Serial port configuration is unified for all ports being opened (might change later).
    - Click "Start Bridge" to start forwarding data.
    - Click "Stop Bridge" to stop forwarding data.
    - Click "Clear Log" to clear the log window.

### Command-Line Version

1. **Starting The Bridge:**

    ```sh
    python app_cli.py --target-ip <target-ip> start
    ```

2. **Overriding Configuration Settings:**

    You can override specific settings from the command line. For example:

    ```sh
    python app_cli.py --serial-port /dev/ttyUSB1 --baud-rate 115200 --target-port 54321 --interval 2000 start
    ```

### Configuration

The configuration file (`config.ini`) contains default settings for the application:

```ini
[Common]
interval = 5
target_ip = 192.168.0.100

[IP_List]
ip1 = 192.168.0.100
ip2 = 192.168.0.101
ip3 = 192.168.0.102
ip4 = 127.0.0.1

[Connection1]
name = Radio 1
serial_port = /dev/ttyUSB1
target_port = 5000
listen_port = 5001
baud_rate = 9600
data_bits = 8
parity = None
stop_bits = 1.0
buffer_size = default
mode = Tx
```

More Connections can be added with the same exact format.
Create or edit the config.ini file to match your setup.

### CLI Version

You can set up the command-line version to run as a service on raspberry pi raspbian os 11
for our usage (can be changed manually). 
there is a build Script that builds it using Docker and creates a debian package.

## Building the Serial-UDP Bridge Package

### Prerequisites

Ensure you have Docker installed and set up on your system. This script uses Docker to build a `.deb` package for the Raspberry Pi.


### Running the Build Script

1. **Ensure `version.txt` is present**:
   - If it's the first time, create it manually with the initial version:
   ```sh
   echo "0.1.0" > version.txt
   ```
   
2. Navigate to the scripts directory:
      ```sh
   cd scripts
   ```

3. Run the build script
    ```sh
   sudo ./build.sh
   ```

**This script will:**

    - Increment the version number stored in version.txt.
    - Create the necessary directory structure for the package.
    - Copy the application files into the package directory.
    - Generate a control file for the package.
    - Generate a postinst script to enable and start the service upon installation.
    - Generate a systemd service file for packet_listener.
    - Build the .deb package using Docker.
    - Place the built package in the ../builds directory.

### Installing the Package on Raspberry Pi

1. Transfer the .deb package to your Raspberry Pi:
 ```sh
   sudo scp ../builds/serial_udp_package_<timestamp>.deb pi@raspberrypi:/home/pi/
   ```

2. Install the package using apt-get install:
 ```sh
   sudo apt-get install /home/pi/serial_udp_package_<timestamp>.deb
   ```
**During the installation, you should see output indicating the steps being performed by the postinst script:**
 ```sh
Reloading systemd manager configuration...
Enabling packet_listener service to start on boot...
Starting packet_listener service...
packet_listener service has been enabled and started.
   ```

## Viewing Logs
1. View The Entire Log File:
    ```sh
    cat /var/log/packet_listener.log
   ```
2. Follow the Log File in Real-Time:
     ```sh
    tail -f /var/log/packet_listener.log
   ```
3. Scroll Through the Log File:
   ```sh
    less /var/log/packet_listener.log
   ```
4. View Logs with journalctl:
    ```sh
   sudo journalctl -u packet_listener
   ```

## Troubleshooting
If you encounter any issues, check the logs for more details. You can also use systemctl status to get the status of the service:
    ```sh
    sudo systemctl status packet_listener.service
    ```
   

## Testing

A test_com.py script is provided to create a virtual serial device and generate mock data for testing purposes.
 ### Running the Test Script

 1. Run The Script:
    ```sh
    python test_com.py
    ```
 2. Explanation:
    - The script creates a virtual serial device and links it to /dev/ttyUSB0.
    - It generates mock data and writes it to the virtual serial device.
    - The data can be used to test the Serial to UDP Bridge application.
    - Press Ctrl+C to stop the script.
    - The virtual serial device will be removed.

Anotehr Test version of the command line script is available for loop backing, it does not interact with serial ports but rather recieves data from UDP and queues it and resends it accordingto parameters to UDP host aswell.
### Running the Loop Back Test Script

 1. Run The Script:
    ```sh
    sudo python3 loop_back_test.py --target-ip <ip here> --listen-port <port> --target-port <port> start
    ```
 2. Explanation:
    - It listens for UDP packets on a specified port and sends received data back to a target IP and port.
    - This verifies network communication functionality without requiring a physical serial device.
   
### License
  This project is licensed under the MIT License.
  












