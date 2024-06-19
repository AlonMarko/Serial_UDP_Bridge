import argparse
import configparser
import os
import sys
import threading
import socket
import time
import select
import logging
import signal
import psutil
from queue import Queue, Empty

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# File handler
file_handler = logging.FileHandler('udp_loopback_bridge.log')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

def resource_path(relative_path):
    """ Get the absolute path to the resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath("..")

    return os.path.join(base_path, relative_path)

class UDPLoopbackApp:
    def __init__(self, target_ip, target_port, listen_port, interval):
        self.target_ip = target_ip
        self.target_port = target_port
        self.listen_port = listen_port
        self.interval = interval / 1000.0  # Convert to seconds
        self.stop_event = threading.Event()
        self.queue = Queue()

    def start_bridge(self):
        logger.info(f"Starting UDP loopback bridge: UDP {self.target_ip}:{self.target_port} <-> UDP {self.listen_port}")

        self.stop_event.clear()

        self.listen_thread = threading.Thread(target=self.listen_for_udp_data, daemon=True)
        self.listen_thread.start()
        self.send_thread = threading.Thread(target=self.send_udp_data, daemon=True)
        self.send_thread.start()

    def stop_bridge(self):
        self.stop_event.set()
        if self.listen_thread.is_alive():
            logger.info("Stopping UDP Listen Thread")
            self.listen_thread.join()
            logger.info("Thread joined.")
        if self.send_thread.is_alive():
            logger.info("Stopping UDP Send Thread")
            logger.info("Waiting for the thread to join.")
            self.send_thread.join()
            logger.info("Thread joined.")
        logger.info("Bridge stopped.")

    def listen_for_udp_data(self):
        logger.info("UDP Listen thread started")
        listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listen_socket.bind(('', int(self.listen_port)))
        listen_socket.setblocking(False)  # Set socket to non-blocking mode
        try:
            while not self.stop_event.is_set():
                try:
                    ready_to_read, _, _ = select.select([listen_socket], [], [], 1.0)
                    if ready_to_read:
                        data, addr = listen_socket.recvfrom(1024)  # Buffer size 1024 bytes
                        if data:
                            self.queue.put(data)
                            logger.info(f"Received from {addr}: {data}")
                except socket.error as e:
                    logger.error(f"Error in listen socket: {e}")
                    break
        finally:
            listen_socket.close()
        logger.info("UDP Listen thread stopped")

    def send_udp_data(self):
        logger.info("UDP Send thread started")
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            while not self.stop_event.is_set():
                try:
                    data = self.queue.get(timeout=1.0)
                    udp_socket.sendto(data, (self.target_ip, int(self.target_port)))
                    logger.info(f"Sent to {self.target_ip}:{self.target_port}: {data}")
                except Empty:
                    continue
                except Exception as e:
                    logger.error(f"Error in send socket: {e}")
                    break
        finally:
            udp_socket.close()
        logger.info("UDP Send thread stopped")

def read_config(file_path):
    config = configparser.ConfigParser()
    config.read(file_path)
    return config

def signal_handler(signal, frame):
    logger.info('Signal received, stopping bridge...')
    app.stop_bridge()
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="UDP Loopback Bridge")
    parser.add_argument("--config", type=str, default="config.ini", help="Path to the configuration file")
    parser.add_argument("--target-ip", type=str, required=True, help="Target IP address for UDP")
    parser.add_argument("--target-port", type=int, help="Target port for UDP")
    parser.add_argument("--listen-port", type=int, help="UDP port to listen on")
    parser.add_argument("--interval", type=int, help="Sampling interval in milliseconds")
    parser.add_argument("action", choices=['start', 'stop'], help="Action to perform (start or stop the bridge)")

    args = parser.parse_args()
    config = read_config(args.config)

    target_ip = args.target_ip
    target_port = args.target_port or config.getint('Settings', 'target_port')
    listen_port = args.listen_port or config.getint('Settings', 'listen_port')
    interval = args.interval or config.getint('Settings', 'sampling_interval')

    global app
    app = UDPLoopbackApp(
        target_ip=target_ip,
        target_port=target_port,
        listen_port=listen_port,
        interval=interval
    )

    if args.action == 'start':
        logger.info('Starting the bridge...')
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        app.start_bridge()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            app.stop_bridge()
    elif args.action == 'stop':
        logger.info('Stopping the bridge...')
        for proc in psutil.process_iter():
            if proc.name() == 'python' or proc.name() == 'python3':
                for arg in proc.cmdline():
                    if 'app_cli.py' in arg:
                        proc.send_signal(signal.SIGINT)

if __name__ == "__main__":
    main()
