import argparse
import configparser
import os
import sys
import threading
import serial
import socket
import time
import select
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
    def __init__(self, serial_port, baud_rate, target_ip, target_port, listen_port, interval):
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.target_ip = target_ip
        self.target_port = target_port
        self.listen_port = listen_port
        self.interval = interval / 1000.0  # Convert to seconds
        self.stop_event = threading.Event()
        self.serial_conn = None

    def start_bridge(self):
        try:
            self.serial_conn = serial.Serial(self.serial_port, baudrate=int(self.baud_rate), timeout=1)
        except Exception as e:
            logger.error(f"Error setting up connections: {e}")
            return

        logger.info(f"Starting bridge: {self.serial_port} <-> UDP {self.target_ip}:{self.target_port}")

        self.stop_event.clear()

        self.read_thread = threading.Thread(target=self.read_and_send_serial_data, daemon=True)
        self.read_thread.start()
        self.listen_thread = threading.Thread(target=self.listen_and_forward_udp_data, daemon=True)
        self.listen_thread.start()

    def stop_bridge(self):
        self.stop_event.set()
        if self.read_thread.is_alive():
            logger.info("Stopping Reading Serial Thread")
            self.read_thread.join()
            logger.info("Thread joined.")
        if self.listen_thread.is_alive():
            logger.info("Stopping Listening UDP Thread")
            self.listen_thread.join()
            logger.info("Thread joined.")
        if self.serial_conn:
            logger.info("Closing Serial Connection.")
            self.serial_conn.close()
            logger.info("Serial Connection Closed.")
        logger.info("Bridge stopped.")

    def read_and_send_serial_data(self):
        logger.info("Serial->UDP thread started")
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while not self.stop_event.is_set():
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    udp_socket.sendto(data, (self.target_ip, int(self.target_port)))
                    logger.info(f"Sent: {data}")
            except Exception as e:
                logger.error(f"Error in read socket: {e}")
        udp_socket.close()

    def listen_and_forward_udp_data(self):
        logger.info("UDP->Serial thread started")
        listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listen_socket.bind(('', int(self.listen_port)))
        listen_socket.setblocking(False)  # Set socket to non-blocking mode
        while not self.stop_event.is_set():
            try:
                ready_to_read, _, _ = select.select([listen_socket], [], [], 1.0)
                if ready_to_read:
                    data, addr = listen_socket.recvfrom(1024)  # Buffer size 1024 bytes
                    if data:
                        self.serial_conn.write(data)
                        logger.info(f"Received from {addr}: {data}")
                    else:
                        time.sleep(0.1)
            except socket.error as e:
                logger.error(f"Error in listen socket: {e}")
                break
            time.sleep(self.interval)
        listen_socket.close()


def read_config(file_path):
    config = configparser.ConfigParser()
    config.read(file_path)
    return config

def main():
    parser = argparse.ArgumentParser(description="Serial to UDP Bridge")
    parser.add_argument("--config", type=str, default="config.ini", help="Path to the configuration file")
    parser.add_argument("--serial-port", type=str, help="Serial port to use")
    parser.add_argument("--baud-rate", type=int, help="Baud rate for serial communication")
    parser.add_argument("--target-ip", type=str, required=True, help="Target IP address for UDP")
    parser.add_argument("--target-port", type=int, help="Target port for UDP")
    parser.add_argument("--listen-port", type=int, help="UDP port to listen on")
    parser.add_argument("--interval", type=int, help="Sampling interval in milliseconds")
    parser.add_argument("action", choices=['start', 'stop'], help="Action to perform (start or stop the bridge)")

    args = parser.parse_args()
    config = read_config(args.config)

    serial_port = args.serial_port or config.get('Settings', 'serial_port')
    baud_rate = args.baud_rate or config.getint('Settings', 'baud_rate')
    target_ip = args.target_ip
    target_port = args.target_port or config.getint('Settings', 'target_port')
    listen_port = args.listen_port or config.getint('Settings', 'listen_port')
    interval = args.interval or config.getint('Settings', 'sampling_interval')

    app = SerialToUDPApp(
        serial_port=serial_port,
        baud_rate=baud_rate,
        target_ip=target_ip,
        target_port=target_port,
        listen_port=listen_port,
        interval=interval
    )
    if args.action == 'start':
        app.start_bridge()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            app.stop_bridge()
    elif args.action == 'stop':
        app.stop_bridge()

if __name__ == "__main__":
    main()
