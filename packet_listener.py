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
start_process = None  # Global variable to track the 'app_cli_2_con.py' subprocess

def handle_start(target_ip):
    """Handle start packet by running the start code from a different Python file."""
    global start_process
    try:
        # Start the subprocess and store the Popen object in the global variable
        start_process = subprocess.run(['python3', 'app_cli_2_con.py', '--target-ip', target_ip, 'start'], check=True)
        logging.info(f"Successfully started app_cli_2_con.py with target IP {target_ip}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to run app_cli_2_con.py: {e}")

def handle_stop():
    """Handle stop packet by running the stop code from a different Python file."""
    global start_process
    if start_process and start_process.poll() is None:  # Check if the process is still running
        try:
            os.kill(start_process.pid, signal.SIGINT)  # Send SIGINT to the subprocess
            start_process.wait()  # Wait for the subprocess to handle SIGINT and exit
            logging.info("Successfully stopped app_cli_2_con.py")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to run app_cli_2_con.py: {e}")
    else:
        logging.warning("No running app_cli_2_con.pyprocess found to stop")

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
    listen_socket.bind(('', 7000))

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
