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
        # Adjust the base path to point to the parent directory (project root)
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    path = os.path.join(base_path, 'configs/', relative_path)

    return path


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
        with open("../configs/config.ini", "w") as configfile:
            self.config.write(configfile)
        messagebox.showinfo("Settings Saved", "Settings have been saved successfully.")
        self.destroy()


class SerialToUDPApp:
    def __init__(self, master):
        self.master = master
        master.title("Serial to UDP Bridge")
        master.geometry("800x800")  # Adjusted window size
        master.resizable(False, False)  # Window not resizable

        self.config = configparser.ConfigParser()
        self.config.read(resource_path('config.ini'))

        # Load common settings
        self.baud_rate = self.config.getint('Common', 'baud_rate')
        self.interval = self.config.getint('Common', 'interval')
        self.data_bits = self.config.getint('Common', 'data_bits', fallback=8)
        self.parity = self.config.get('Common', 'parity', fallback='None')
        self.stop_bits = self.config.getfloat('Common', 'stop_bits', fallback=1)


        self.ip_list = {k: v for k, v in self.config.items('IP_List')}
        self.connections = ["Connection1", "Connection2"]
        self.threads = []

        self.create_main_gui()

        # Add error listener for port 7000
        self.error_listener_thread = threading.Thread(target=self.error_listener)
        self.error_listener_thread.daemon = True
        self.error_listener_thread.start()

        # Bind the closing event to send the stop packet
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_main_gui(self):
        """Create the main GUI layout."""
        self.frame = ttk.Frame(self.master, padding="10 10 10 10")
        self.frame.grid(column=0, row=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        for i in range(1, 11):
            self.frame.rowconfigure(i, weight=1)
        for i in range(2):  # Configure two columns
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
        self.baud_rate_entry = self.add_common_setting("Baud Rate", "The baud rate for the serial communication.", 2)
        self.interval_entry = self.add_common_setting("Sampling Interval (ms)", "The sampling interval in milliseconds.", 3)

        # Data bits selection
        self.data_bits_combobox = self.add_common_setting("Data Bits", "The number of data bits per byte (5, 6, 7, or 8).", 4, [5, 6, 7, 8])

        # Parity selection
        self.parity_combobox = self.add_common_setting("Parity", "The parity setting (None, Even, Odd, Mark, or Space).", 5, ['None', 'Even', 'Odd', 'Mark', 'Space'])

        # Stop bits selection
        self.stop_bits_combobox = self.add_common_setting("Stop Bits", "The number of stop bits (1, 1.5, or 2).", 6, [1, 1.5, 2])

        # Create buttons to open settings windows for each connection
        for idx, connection in enumerate(self.connections, start=7):
            button = ttk.Button(self.frame, text=f"Settings for {connection}", command=lambda c=connection: self.open_settings_window(c))
            button.grid(row=idx, column=0, columnspan=2, pady=10)

        # Add start and stop buttons
        self.start_button = ttk.Button(self.frame, text="Start Bridge", command=self.start_bridge)
        self.start_button.grid(row=7 + len(self.connections), column=0, pady=10)

        self.stop_button = ttk.Button(self.frame, text="Stop Bridge", command=self.stop_bridge, state=tk.DISABLED)
        self.stop_button.grid(row=7 + len(self.connections), column=1, pady=10)

        # Clear log button
        self.clear_log_button = ttk.Button(self.frame, text="Clear Log", command=self.clear_log)
        self.clear_log_button.grid(row=8 + len(self.connections), column=0, columnspan=2, pady=10)

        # Status label
        self.status_label = ttk.Label(self.frame, text="Status: Not running")
        self.status_label.grid(row=9 + len(self.connections), column=0, columnspan=2, pady=10)

        # Log text area with scrollbars
        self.log_frame = ttk.Frame(self.master)
        self.log_frame.grid(row=10 + len(self.connections), column=0, columnspan=2, pady=10, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.log_text = tk.Text(self.log_frame, state=tk.DISABLED, height=15, wrap='none')
        self.log_scroll_y = ttk.Scrollbar(self.log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_scroll_x = ttk.Scrollbar(self.log_frame, orient=tk.HORIZONTAL, command=self.log_text.xview)
        self.log_text['yscrollcommand'] = self.log_scroll_y.set
        self.log_text['xscrollcommand'] = self.log_scroll_x.set
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.log_scroll_y.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.log_scroll_x.grid(row=1, column=0, sticky=(tk.W, tk.E))

        # Configure tags for log text
        self.log_text.tag_config('info', foreground='black')
        self.log_text.tag_config('error', foreground='red')

    def add_common_setting(self, label_text, info_text, row, values=None):
        label = ttk.Label(self.frame, text=label_text)
        label.grid(row=row, column=0, sticky=tk.W, pady=5)

        # Mapping for label text to configuration keys
        config_key_mapping = {
            "Baud Rate": "baud_rate",
            "Sampling Interval (ms)": "interval",
            "Data Bits": "data_bits",
            "Parity": "parity",
            "Stop Bits": "stop_bits"
        }

        config_key = config_key_mapping[label_text]

        if values:
            widget_var = ttk.Combobox(self.frame)
            widget_var['values'] = values
            widget_var.set(self.config.get('Common', config_key, fallback=values[0]))
        else:
            widget_var = ttk.Entry(self.frame)
            widget_var.insert(0, self.config.get('Common', config_key))
        widget_var.grid(row=row, column=1, sticky=tk.EW, pady=5)

        info_button = ttk.Button(self.frame, text="?", command=lambda: self.show_info(info_text))
        info_button.grid(row=row, column=2, sticky=tk.W, pady=5)

        return widget_var

    def show_info(self, info_text):
        messagebox.showinfo("Info", info_text)

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
            self.data_bits = int(self.data_bits_combobox.get())
            self.parity = self.parity_combobox.get()
            self.stop_bits = float(self.stop_bits_combobox.get())

            self.config.set('Common', 'target_ip', self.target_ip)
            self.config.set('Common', 'baud_rate', str(self.baud_rate))
            self.config.set('Common', 'interval', str(self.interval))
            self.config.set('Common', 'data_bits', str(self.data_bits))
            self.config.set('Common', 'parity', self.parity)
            self.config.set('Common', 'stop_bits', str(self.stop_bits))
            with open("../configs/config.ini", "w") as configfile:
                self.config.write(configfile)

            self.stop_event = threading.Event()
            for connection in self.connections:
                self.start_connection(connection)
            self.status_label.config(text="Status: Running")
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.send_start_packet()
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
            self.log("Bridge Stop......")
            self.status_label.config(text="Status: Not running")
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
        except Exception as e:
            self.log(f"Error in stop_bridge: {e}")

    def start_connection(self, connection):
        """Start the connection for a specific serial port and corresponding UDP ports."""

        serial_port = self.config.get(connection, "serial_port")
        target_port = self.config.getint(connection, "target_port")
        listen_port = self.config.getint(connection, "listen_port")
        data_bits = self.data_bits
        parity = self.parity[0].upper()  # Get the first letter (N, E, O, M, S)
        stop_bits = self.stop_bits

        # Mapping parity value
        parity_mapping = {
            'N': serial.PARITY_NONE,
            'E': serial.PARITY_EVEN,
            'O': serial.PARITY_ODD,
            'M': serial.PARITY_MARK,
            'S': serial.PARITY_SPACE
        }

        serial_conn = serial.Serial(
            port=serial_port,
            baudrate=self.baud_rate,
            bytesize={5: serial.FIVEBITS, 6: serial.SIXBITS, 7: serial.SEVENBITS, 8: serial.EIGHTBITS}[data_bits],
            parity=parity_mapping.get(parity, serial.PARITY_NONE),
            stopbits={1: serial.STOPBITS_ONE, 1.5: serial.STOPBITS_ONE_POINT_FIVE, 2: serial.STOPBITS_TWO}[
                stop_bits],
            timeout=1
        )

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

    def error_listener(self):
        """Listen for error messages on port 7000 and update the GUI."""
        listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listen_socket.bind(('', 7000)) # Default Comm port.
        listen_socket.setblocking(False)

        try:
            while True:
                ready_to_read, _, _ = select.select([listen_socket], [], [], 1.0)
                if ready_to_read:
                    data, addr = listen_socket.recvfrom(1024)
                    if data:
                        message = data.decode()
                        self.log(f"Error received from {addr}: {message}", 'error')
                        self.stop_bridge()
                        self.status_label.config(text="Status: Not running")
                        self.start_button.config(state=tk.NORMAL)
                        self.stop_button.config(state=tk.DISABLED)
        except Exception as e:
            self.log(f"Error in error_listener: {e}", 'error')
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
        # for i in range(5):
            # Send 5 Times to make sure recieve.
        udp_socket.sendto(start_packet, (self.target_ip, 7000)) # Hard coded default port
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

    def log(self, message, level='info'):
        """Log messages with timestamps."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"{timestamp} - {message}"
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_message + "\n", level)
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
