#!/usr/bin/env python3


import socket
import threading
import subprocess
import logging
import signal
import os

# Configure logging
logging.basicConfig(filename='/var/log/packet_listener.log', level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s: %(message)s')

stop_event = threading.Event()
start_process = None  # Global variable to track the 'app_cli.py' subprocess
current_target_ip = None  # To track the IP from which the start packet was received


def monitor_subprocess():
    global start_process
    if start_process:
        stdout, stderr = start_process.communicate()  # Capture the standard output and standard error
        exit_code = start_process.returncode  # Get the exit code

        # Log the stdout and stderr
        if stdout:
            logging.info(f"Subprocess output: {stdout.strip()}")
        if stderr:
            logging.error(f"Subprocess error: {stderr.strip()}")

        # Log and send an error packet if the subprocess exited with a non-zero code
        if exit_code != 0:
            error_message = f"app_cli.py exited with code {exit_code}. Error: {stderr.strip() or stdout.strip()}"
            logging.error(error_message)
            send_error_packet(current_target_ip, error_message)

        # Transition back to waiting for start mode
        start_process = None
        logging.info("Transitioning back to waiting for start mode")


def send_error_packet(target_ip, message):
    """Send an error packet to the specified IP address."""
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        error_packet = f"ERROR: {message}".encode()
        udp_socket.sendto(error_packet, (target_ip, 7000))
        udp_socket.close()
        logging.info(f"Sent error packet to {target_ip} with error {error_packet}")
    except Exception as e:
        logging.error(f"Failed to send error packet to {target_ip}: {e}")


def handle_start(target_ip):
    """Handle start packet by running the start code from a different Python file."""
    global start_process, current_target_ip
    current_target_ip = target_ip  # Store the target IP
    try:
        # Start the subprocess and store the Popen object in the global variable
        start_process = subprocess.Popen(
            ['sudo', '-S', 'python3', 'app_cli.py', '--target-ip', target_ip, 'start'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            universal_newlines=True
        )
        psw = "qwe123$"
        stdout, stderr = start_process.communicate(input=f"{psw}\n")

        logging.info(f"Successfully started app_cli.py with target IP {target_ip}")
        monitor_thread = threading.Thread(target=monitor_subprocess)
        monitor_thread.start()
    except Exception as e:
        logging.error(f"Failed to run app_cli.py: {e}")


def handle_stop():
    """Handle stop packet by running the stop code from a different Python file."""
    global start_process
    if start_process and start_process.poll() is None:  # Check if the process is still running
        try:
            os.kill(start_process.pid, signal.SIGINT)  # Send SIGINT to the subprocess
            start_process.wait()  # Wait for the subprocess to handle SIGINT and exit
            logging.info("Successfully stopped app_cli.py")
        except Exception as e:
            logging.error(f"Failed to stop app_cli.py: {e}")
    else:
        logging.warning("No running app_cli.py process found to stop")


def handle_packet(data, addr, current_state):
    """Process the received packet based on the current state."""
    try:
        message = data.decode()
        ip, command = message.split(' ')

        if current_state['waiting_for'] == 'start' and command == "start":
            logging.info(f"Received start packet from {ip}")
            handle_start(ip)
            current_state['waiting_for'] = 'stop'
        elif current_state['waiting_for'] == 'stop' and command == "stop":
            logging.info(f"Received stop packet from {ip}")
            handle_stop()
            current_state['waiting_for'] = 'start'
        else:
            logging.warning(f"Unexpected command received: {command}")
    except Exception as e:
        logging.error(f"Error processing packet: {e}")


def listener():
    """Listen for packets on port 7000 and handle state transitions."""
    listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listen_socket.bind(('', 7000))  # Hard coded default port.

    current_state = {'waiting_for': 'start'}

    try:
        while not stop_event.is_set():
            data, addr = listen_socket.recvfrom(1024)
            if data:
                handle_packet(data, addr, current_state)
    except Exception as e:
        logging.error(f"Error in listener: {e}")
    finally:
        listen_socket.close()
        logging.info("Listener socket closed")


def signal_handler(sig, frame):
    logging.info(f"Received signal {sig}, shutting down.")
    stop_event.set()
    if start_process and start_process.poll() is None:  # If start process is still running, stop it
        handle_stop()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C for testing

    listener_thread = threading.Thread(target=listener)
    listener_thread.start()
    listener_thread.join()
