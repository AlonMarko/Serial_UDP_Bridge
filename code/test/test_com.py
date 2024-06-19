import os
import pty
import time
import serial
import threading


def create_virtual_serial_device():
    # Create a master-slave pair of pseudo-terminals
    master, slave = pty.openpty()
    slave_name = os.ttyname(slave)

    # Link the slave PTY to /dev/ttyUSB0
    link_name = '/dev/ttyUSB0'
    try:
        os.symlink(slave_name, link_name)
    except FileExistsError:
        os.remove(link_name)
        os.symlink(slave_name, link_name)

    return master, slave_name


def generate_mock_data(master_fd):
    while True:
        os.write(master_fd, b'Test data from mock device\n')
        time.sleep(0.1)  # Send data every second


def main():
    master_fd, slave_name = create_virtual_serial_device()
    print(f"Virtual serial device created at {slave_name} and linked to /dev/ttyUSB0")

    # Start generating mock data on the master side of the PTY
    data_thread = threading.Thread(target=generate_mock_data, args=(master_fd,), daemon=True)
    data_thread.start()

    print("Mock data generation started. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Exiting.")
        os.remove('/dev/ttyUSB0')


if __name__ == "__main__":
    main()