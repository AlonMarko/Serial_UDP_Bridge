import tkinter as tk
from tkinter import ttk, messagebox
import threading
import serial
import socket
import time
import configparser
import select
import os
import sys
import psutil
from datetime import datetime


def resource_path(relative_path):
    """ Get the absolute path to the resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


class SettingsWindow(tk.Toplevel):
    def __init__(self, master, connection_name, config, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.title(f"Settings for {connection_name}")
        self.geometry("300x300")
        self.config = config
        self.connection_name = connection_name

        # Create entry fields for each setting
        self.create_settings_fields()

        # Load current settings
        self.load_settings()

        # Add save button
        self.save_button = ttk.Button(self, text="Save", command=self.save_settings)
        self.save_button.pack(pady=10)

    def create_settings_fields(self):
        """Create input fields for serial port, target port, and listen port."""
        self.entries = {}
        settings = ["serial_port", "target_port", "listen_port"]
        for setting in settings:
            label = ttk.Label(self, text=setting.replace("_", " ").title())
            label.pack(pady=5)
            entry = ttk.Entry(self)
            entry.pack(pady=5)
            self.entries[setting] = entry

    def load_settings(self):
        """Load current settings into input fields."""
        for setting, entry in self.entries.items():
            entry.insert(0, self.config.get(self.connection_name, setting))

    def save_settings(self):
        """Save settings to the configuration file."""
        for setting, entry in self.entries.items():
            self.config.set(self.connection_name, setting, entry.get())
        with open("config.ini", "w") as configfile:
            self.config.write(configfile)
        messagebox.showinfo("Settings Saved", "Settings have been saved successfully.")
        self.destroy()


class SerialToUDPApp:
    def __init__(self, master):
        self.master = master
        master.title("Serial to UDP Bridge")
        master.geometry("1000x700")  # Adjusted window size
        master.resizable(False, False)  # Window not resizable

        self.config = configparser.ConfigParser()
        self.config.read(resource_path('config.ini'))

        # Load common settings
        self.baud_rate = self.config.getint('Common', 'baud_rate')
        self.interval = self.config.getint('Common', 'interval')

        self.ip_list = {k: v for k, v in self.config.items('IP_List')}
        self.connections = ["Connection1", "Connection2"]
        self.threads = []

        self.create_main_gui()

        # Bind the closing event to send the stop packet
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_main_gui(self):
        """Create the main GUI layout."""
        self.frame = ttk.Frame(self.master, padding="10 10 10 10")
        self.frame.grid(column=0, row=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        for i in range(1, 11):
            self.frame.rowconfigure(i, weight=1)
        for i in range(1, 3):
            self.frame.columnconfigure(i, weight=1)

        # Create common settings
        common_label = ttk.Label(self.frame, text="Common Settings")
        common_label.grid(row=0, column=0, columnspan=2, pady=10)

        # Target IP selection
        target_ip_label = ttk.Label(self.frame, text="Target IP")
        target_ip_label.grid(row=1, column=0, sticky=tk.W, pady=5)
        self.target_ip_combobox = ttk.Combobox(self.frame)
        self.target_ip_combobox['values'] = [f"{key} - {value}" for key, value in self.ip_list.items()]
        self.target_ip_combobox.grid(row=1, column=1, sticky=tk.EW, pady=5)
        self.target_ip_combobox.set(next((f"{key} - {value}" for key, value in self.ip_list.items()), ''))

        # Baud rate and interval
        baud_rate_label = ttk.Label(self.frame, text="Baud Rate")
        baud_rate_label.grid(row=2, column=0, sticky=tk.W, pady=5)
        self.baud_rate_entry = ttk.Entry(self.frame)
        self.baud_rate_entry.insert(0, self.baud_rate)
        self.baud_rate_entry.grid(row=2, column=1, sticky=tk.EW, pady=5)

        interval_label = ttk.Label(self.frame, text="Sampling Interval (ms)")
        interval_label.grid(row=3, column=0, sticky=tk.W, pady=5)
        self.interval_entry = ttk.Entry(self.frame)
        self.interval_entry.insert(0, self.interval)
        self.interval_entry.grid(row=3, column=1, sticky=tk.EW, pady=5)

        # Create buttons to open settings windows for each connection
        for idx, connection in enumerate(self.connections, start=4):
            button = ttk.Button(self.frame, text=f"Settings for {connection}",
                                command=lambda c=connection: self.open_settings_window(c))
            button.grid(row=idx, column=0, columnspan=2, pady=10)

        # Add start and stop buttons
        self.start_button = ttk.Button(self.frame, text="Start Bridge", command=self.start_bridge)
        self.start_button.grid(row=7, column=0, pady=10)

        self.stop_button = ttk.Button(self.frame, text="Stop Bridge", command=self.stop_bridge, state=tk.DISABLED)
        self.stop_button.grid(row=7, column=1, pady=10)

        # Clear log button
        self.clear_log_button = ttk.Button(self.frame, text="Clear Log", command=self.clear_log)
        self.clear_log_button.grid(row=8, column=0, columnspan=2, pady=10)

        # Status label
        self.status_label = ttk.Label(self.frame, text="Status: Not running")
        self.status_label.grid(row=9, column=0, columnspan=2, pady=10)

        # Log text area with scrollbar
        self.log_frame = ttk.Frame(self.master)
        self.log_frame.grid(row=10, column=0, columnspan=2, pady=10, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.log_text = tk.Text(self.log_frame, state=tk.DISABLED, height=15, fg="black")
        self.log_scroll = ttk.Scrollbar(self.log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text['yscrollcommand'] = self.log_scroll.set
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.log_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))

    def open_settings_window(self, connection_name):
        """Open the settings window for a specific connection."""
        SettingsWindow(self.master, connection_name, self.config)

    def start_bridge(self):
        """Start the serial to UDP bridge."""
        try:
            selected_item = self.target_ip_combobox.get()
            selected_ip_key = selected_item.split(' ')[0]
            self.target_ip = self.ip_list.get(selected_ip_key, None)
            if self.target_ip is None:
                raise ValueError(f"Invalid IP address key: {selected_ip_key}")
            self.baud_rate = int(self.baud_rate_entry.get())
            self.interval = int(self.interval_entry.get())

            self.config.set('Common', 'target_ip', self.target_ip)
            self.config.set('Common', 'baud_rate', str(self.baud_rate))
            self.config.set('Common', 'interval', str(self.interval))
            with open("config.ini", "w") as configfile:
                self.config.write(configfile)

            self.send_start_packet()

            self.stop_event = threading.Event()
            for connection in self.connections:
                self.start_connection(connection)
            self.status_label.config(text="Status: Running")
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
        except Exception as e:
            self.log(f"Error in start_bridge: {e}")
            self.status_label.config(text="Status: Not running")
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)

    def stop_bridge(self):
        """Stop the serial to UDP bridge."""
        try:
            self.send_stop_packet()
            self.stop_event.set()
            for thread in self.threads:
                thread.join()
            self.status_label.config(text="Status: Not running")
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
        except Exception as e:
            self.log(f"Error in stop_bridge: {e}")

    def start_connection(self, connection):
        """Start the connection for a specific serial port and corresponding UDP ports."""
        # try:
        serial_port = self.config.get(connection, "serial_port")
        target_port = self.config.getint(connection, "target_port")
        listen_port = self.config.getint(connection, "listen_port")

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
        # except Exception as e:
        #     self.log(f"Error in start_connection for {connection}: {e}")

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
        finally:
            listen_socket.close()

    def get_ipv4_address(self):
        """Get the IPv4 address of the enp interfaces."""
        addresses = psutil.net_if_addrs()
        for interface_name, interface_addresses in addresses.items():
            if interface_name.startswith('enp'):
                for addr in interface_addresses:
                    if addr.family == socket.AF_INET:
                        return addr.address

        self.log("Failed to send packet: No 'enp' interface with IPv4 address found.")
        return None

    def send_start_packet(self):
        """Send a start packet to the target IP."""
        ip_address = self.get_ipv4_address()
        if ip_address is None:
            return  # Do not send packet if IP address is not found

        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        start_packet = f"{ip_address} start".encode()
        for i in range(5):
            # Send 5 Times to make sure recieve.
            udp_socket.sendto(start_packet, (self.target_ip, 7000))
            time.sleep(0.05)
        udp_socket.close()
        self.log(f"Sent start packet to {self.target_ip}:7000")

    def send_stop_packet(self):
        """Send a stop packet to the target IP."""
        ip_address = self.get_ipv4_address()
        if ip_address is None:
            return  # Do not send packet if IP address is not found

        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        stop_packet = f"{ip_address} stop".encode()
        udp_socket.sendto(stop_packet, (self.target_ip, 7000))
        udp_socket.close()
        self.log(f"Sent stop packet to {self.target_ip}:7000")

    def log(self, message):
        """Log messages with timestamps."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"{timestamp} - {message}"
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_message + "\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def clear_log(self):
        """Clear the log text area."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

    def on_closing(self):
        """Handle the GUI closing event."""
        self.stop_bridge()
        self.master.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = SerialToUDPApp(root)
    root.mainloop()
