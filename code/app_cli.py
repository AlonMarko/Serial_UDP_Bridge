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
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Adjust the base path to point to the parent directory (project root)
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    path = os.path.join(base_path, 'configs/', relative_path)

    return path


class SerialToUDPApp:
    def __init__(self, connections, target_ip, interval):
        self.connections = connections
        self.target_ip = target_ip
        self.interval = interval / 1000.0
        self.threads = []

        self.serial_conn = None

        self.stop_event = threading.Event()

    def read_and_send_serial_data(self, serial_conn, udp_socket, target_port, buffer_size):
        """Read data from serial port and send it via UDP."""
        try:
            while not self.stop_event.is_set():
                if serial_conn.in_waiting > 0:
                    data = serial_conn.read(
                        min(buffer_size, serial_conn.in_waiting) if buffer_size else serial_conn.in_waiting)
                    udp_socket.sendto(data, (self.target_ip, target_port))
                    logger.info(f"Sent: {data}")
                time.sleep(self.interval)
        except Exception as e:
            logger.info(f"Error in read_and_send_serial_data: {e}")
            # self.send_error_packet(self.target_ip, "Error in read_and_send_serial_data")
        finally:
            udp_socket.close()
            serial_conn.close()

    def listen_and_forward_udp_data(self, serial_conn, listen_socket):
        """Listen for UDP packets and forward the data to the serial port."""
        try:
            while not self.stop_event.is_set():
                ready_to_read, _, _ = select.select([listen_socket], [], [], 0.01)
                if ready_to_read:
                    data, addr = listen_socket.recvfrom(1024)
                    if data:
                        serial_conn.write(data)
                        logger.info(f"Received from {addr}: {data}")
        except Exception as e:
            logger.error(f"Error in listen_and_forward_udp_data: {e}")
        finally:
            listen_socket.close()

    def start_connection(self, connection):
        """Start the connection for a specific serial port and corresponding UDP ports."""
        try:
            serial_port = connection['serial_ports'][0]
            target_port = connection['target_ports'][0]
            listen_port = connection['listen_ports'][0]
            baud_rate = connection['baud_rate']
            data_bits = connection['data_bits']
            parity = connection['parity'][0].upper()  # Get the first letter (N, E, O, M, S)
            stop_bits = connection['stop_bits']
            buffer_size_str = connection['buffer_size']
            conn_direction = connection['mode']

            # Convert buffer size to integer or set to None for default
            if buffer_size_str == 'default':
                buffer_size = None
            else:
                buffer_size = int(buffer_size_str)

            parity_mapping = {
                'N': serial.PARITY_NONE,
                'E': serial.PARITY_EVEN,
                'O': serial.PARITY_ODD,
                'M': serial.PARITY_MARK,
                'S': serial.PARITY_SPACE
            }

            serial_conn = serial.Serial(
                port=serial_port,
                baudrate=baud_rate,
                bytesize={5: serial.FIVEBITS, 6: serial.SIXBITS, 7: serial.SEVENBITS, 8: serial.EIGHTBITS}[data_bits],
                parity=parity_mapping.get(parity, serial.PARITY_NONE),
                stopbits={1: serial.STOPBITS_ONE, 1.5: serial.STOPBITS_ONE_POINT_FIVE, 2: serial.STOPBITS_TWO}[
                    stop_bits],
                timeout=0
            )

            # Set custom buffer sizes if specified
            if buffer_size is not None:
                serial_conn.set_buffer_size(rx_size=buffer_size, tx_size=buffer_size)

            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            listen_socket.bind(('', listen_port))
            listen_socket.setblocking(False)

            if conn_direction == "Tx":
                logger.info(f"Starting Tx Conn type")

                read_thread = threading.Thread(target=self.read_and_send_serial_data,
                                               args=(serial_conn, udp_socket, target_port, buffer_size))
                self.threads.extend([read_thread])
                read_thread.start()
            elif conn_direction == "Rx":
                logger.info(f"Starting Rx Conn type")

                listen_thread = threading.Thread(target=self.listen_and_forward_udp_data,
                                                 args=(serial_conn, listen_socket))
                self.threads.extend([listen_thread])
                listen_thread.start()
            elif conn_direction == "Tx/Rx":
                logger.info(f"Starting Tx/Rx Conn type")

                read_thread = threading.Thread(target=self.read_and_send_serial_data,
                                               args=(serial_conn, udp_socket, target_port, buffer_size))
                listen_thread = threading.Thread(target=self.listen_and_forward_udp_data,
                                                 args=(serial_conn, listen_socket))
                self.threads.extend([read_thread, listen_thread])
                read_thread.start()
                listen_thread.start()

        except Exception as e:
            logger.error(f"Error in start_connection for {connection}: {e}")
            self.stop_bridge()
            exit(1)

    def start_bridge(self):
        try:
            for connection in self.connections:
                logger.info(
                    f"Starting bridge for {connection['name']}: {connection['serial_ports']} <-> UDP {self.target_ip}:{connection['target_ports']}")
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
            baud_rate = config.getint(section, 'baud_rate')
            data_bits = config.getint(section, 'data_bits')
            parity = config.get(section, 'parity')
            stop_bits = config.getfloat(section, 'stop_bits')
            buffer_size = config.get(section, 'buffer_size')
            c_mode = config.get(section, 'Mode')
            connections.append({
                'serial_ports': serial_ports,
                'target_ports': target_ports,
                'listen_ports': listen_ports,
                'baud_rate': baud_rate,
                'data_bits': data_bits,
                'parity': parity,
                'stop_bits': stop_bits,
                'name': config.get(section, 'name', fallback=section),  # Optional, for logging
                'buffer_size': buffer_size,
                'mode': c_mode
            })

    app = SerialToUDPApp(
        connections=connections,
        target_ip=target_ip,
        interval=interval
    )
    if args.action == 'start':
        app.start_bridge()
        try:
            while True:
                pass
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
