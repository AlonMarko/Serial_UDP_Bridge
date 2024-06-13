import argparse
import configparser
import threading
import serial
import socket
import time
import select
import sys
import os
import logging

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# File handler
file_handler = logging.FileHandler('serial_udp_bridge.log')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


def resource_path(relative_path):
    """ Get the absolute path to the resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


class SerialToUDPApp:
    def __init__(self, connections, baud_rate, target_ip, interval):
        self.connections = connections
        self.baud_rate = baud_rate
        self.target_ip = target_ip
        self.interval = interval
        self.threads = []

        self.serial_conn = None

        self.stop_event = threading.Event()

    def read_and_send_serial_data(self, serial_conn, udp_socket, target_port):
        """Read data from serial port and send it via UDP."""
        try:
            while not self.stop_event.is_set():
                if serial_conn.in_waiting > 0:
                    data = serial_conn.read(serial_conn.in_waiting)
                    udp_socket.sendto(data, (self.target_ip, target_port))
                    self.log(f"Sent: {data}")
                time.sleep(self.interval / 1000.0)
        except Exception as e:
            self.log(f"Error in read_and_send_serial_data: {e}")
            # self.send_error_packet(self.target_ip, "Error in read_and_send_serial_data")
        finally:
            udp_socket.close()
            serial_conn.close()

    def listen_and_forward_udp_data(self, serial_conn, listen_socket):
        """Listen for UDP packets and forward the data to the serial port."""
        try:
            while not self.stop_event.is_set():
                ready_to_read, _, _ = select.select([listen_socket], [], [], 1.0)
                if ready_to_read:
                    data, addr = listen_socket.recvfrom(1024)
                    if data:
                        serial_conn.write(data)
                        self.log(f"Received from {addr}: {data}")
        except Exception as e:
            self.log(f"Error in listen_and_forward_udp_data: {e}")
            # self.send_error_packet(self.target_ip, "Error in listen_and_forward_udp_data")
        finally:
            listen_socket.close()

    def start_connection(self, connection):
        """Start the connection for a specific serial port and corresponding UDP ports."""
        try:
            serial_port = connection['serial_ports'][0]
            target_port = connection['target_ports'][0]
            listen_port = connection['listen_ports'][0]

            serial_conn = serial.Serial(serial_port, baudrate=self.baud_rate, timeout=1)
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            listen_socket.bind(('', listen_port))
            listen_socket.setblocking(False)

            read_thread = threading.Thread(target=self.read_and_send_serial_data,
                                           args=(serial_conn, udp_socket, target_port))
            listen_thread = threading.Thread(target=self.listen_and_forward_udp_data, args=(serial_conn, listen_socket))

            self.threads.extend([read_thread, listen_thread])

            read_thread.start()
            listen_thread.start()
        except Exception as e:
            logger.error(f"Error in start_connection for {connection}: {e}")
            # self.send_error_packet(self.target_ip, "Error in start_connection")
            self.stop_bridge()
            exit(1)

    def start_bridge(self):
        try:
            for connection in self.connections:
                logger.info(
                    f"Starting bridge: {connection['serial_ports']} <-> UDP {self.target_ip}:{connection['target_ports']}")
                self.start_connection(connection)

        except Exception as e:
            logger.error(f"Error in start_bridge: {e}")
            # self.send_error_packet(self.target_ip, "Error in start_bridge")
            self.stop_bridge()
            exit(1)

    def stop_bridge(self):
        try:
            self.stop_event.set()
            for thread in self.threads:
                thread.join()
            logger.info("Bridge stopped.")
        except Exception as e:
            logger.info(f"Error in stop_bridge: {e}")

    # def send_error_packet(self, target_ip, message):
    #     """Send an error packet to the specified IP address."""
    #     try:
    #         udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    #         error_packet = f"ERROR: {message}".encode()
    #         udp_socket.sendto(error_packet, (target_ip, 7000)) # Default IP for app communication.
    #         udp_socket.close()
    #     except Exception as e:
    #         logger.error(f"Failed to send error packet to {target_ip}: {e}")


def read_config(config_path):
    config = configparser.ConfigParser()
    config.read(config_path)
    return config


def main():
    parser = argparse.ArgumentParser(description="Serial to UDP Bridge")
    parser.add_argument("--config", type=str, default="config_cli.ini", help="Path to the configuration file")
    parser.add_argument("--serial-ports", type=str, help="Comma-separated list of Serial connections to use")
    parser.add_argument("--baud-rate", type=int, help="Baud rate for serial communication")
    parser.add_argument("--target-ip", type=str, required=True, help="Target IP address for UDP")
    parser.add_argument("--target-ports", type=str, help="Comma-separated list of target ports for UDP")
    parser.add_argument("--listen-ports", type=str, help="Comma-separated list of UDP ports to listen on")
    parser.add_argument("--interval", type=int, help="Sampling interval in milliseconds")
    parser.add_argument("action", choices=['start', 'stop'], help="Action to perform (start or stop the bridge)")

    args = parser.parse_args()
    config = read_config(args.config)

    # Mandatory as launch argument.
    target_ip = args.target_ip

    # From Common.
    baud_rate = args.baud_rate or config.getint('Common', 'baud_rate')
    interval = args.interval or config.getint('Common', 'interval')

    # Nested function to get a list of ports from a config section
    def get_ports(section, key):
        ports = config.get(section, key, fallback="")
        return [int(port) for port in ports.split(',')] if ports else []

    # Nested function to handle serial ports from arguments or config
    def get_serial_ports(section):
        serial_ports = config.get(section, 'serial_port', fallback="")
        return serial_ports.split(',')

    connections = []
    for section in config.sections():
        if section.startswith('Connection'):
            serial_ports = get_serial_ports(section)
            if args.serial_ports:
                serial_ports = args.serial_ports.split(',')
            target_ports = [int(port) for port in args.target_ports.split(',')] if args.target_ports else get_ports(
                section, 'target_port')
            listen_ports = [int(port) for port in args.listen_ports.split(',')] if args.listen_ports else get_ports(
                section, 'listen_port')
            connections.append({
                'serial_ports': serial_ports,
                'target_ports': target_ports,
                'listen_ports': listen_ports
            })

    # serial_ports = args.serial_ports or config.get('Common', 'serial_port')
    #
    # target_ports = [int(port) for port in args.target_ports.split(',')] or config.get('Settings', 'serial_port')
    # listen_ports = [int(port) for port in args.listen_ports.split(',')] if args.listen_ports else []

    app = SerialToUDPApp(
        connections=connections,
        baud_rate=baud_rate,
        target_ip=target_ip,
        interval=interval
    )
    if args.action == 'start':
        app.start_bridge()
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            app.stop_bridge()
        except Exception as e:
            logger.error(f"Exception in main loop: {e}")
            app.stop_bridge()
            sys.exit(1)  # Exit with a code indicating an error
    elif args.action == 'stop':
        app.stop_bridge()
        sys.exit(0)  # Exit with a code indicating success



if __name__ == "__main__":
    main()
