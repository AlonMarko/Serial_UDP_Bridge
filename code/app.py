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
        self.entries = {}
        self.title(f"Settings for {connection_name}")
        self.geometry("500x400")
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
        """Create input fields for serial port, target port, listen port, etc."""
        settings = {
            "serial_port": "The serial port to use (e.g., /dev/ttyUSB0).",
            "target_port": "The target UDP port to send data to.",
            "listen_port": "The UDP port to listen for incoming data.",
            "baud_rate": "The baud rate for the serial communication.",
            "data_bits": "The number of data bits per byte (5, 6, 7, or 8).",
            "parity": "The parity setting (None, Even, Odd, Mark, or Space).",
            "stop_bits": "The number of stop bits (1, 1.5, or 2).",
            "buffer_size": "The size of the buffer in bytes (default, 50, 100, 200, 300, 400, 500, 600, 700, 800, "
                           "900, 1024).",
            "Mode": "The connection Mode - single way or both way reading and udp forwarding."
        }

        for setting, description in settings.items():
            frame = ttk.Frame(self)
            frame.pack(fill='x', pady=5)

            label = ttk.Label(frame, text=setting.replace("_", " ").title())
            label.pack(side='left', padx=5)

            # Add The Setting as combox in TK
            if setting in ["data_bits", "parity", "stop_bits", "buffer_size", "baud_rate", "Mode"]:
                if setting == "data_bits":
                    options = [5, 6, 7, 8]
                elif setting == "parity":
                    options = ["None", "Even", "Odd", "Mark", "Space"]
                elif setting == "stop_bits":
                    options = [1, 1.5, 2]
                elif setting == "buffer_size":
                    options = ["default", 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1024]
                elif setting == "baud_rate":
                    options = [4800, 9600, 19200, 38400, 57600, 115200]
                elif setting == "Mode":
                    options = ["Rx", "Tx", "Tx/Rx"]

                combobox = ttk.Combobox(frame, values=options)
                combobox.pack(side='left', fill='x', expand=True, padx=5)
                self.entries[setting] = combobox
            else:
                entry = ttk.Entry(frame)
                entry.pack(side='left', fill='x', expand=True, padx=5)
                self.entries[setting] = entry

            info_button = ttk.Button(frame, text="?", command=lambda d=description: self.show_info(d))
            info_button.pack(side='right', padx=5)

    def show_info(self, info_text):
        messagebox.showinfo("Info", info_text)

    def load_settings(self):
        """Load current settings into input fields."""
        for setting, widget in self.entries.items():
            value = self.config.get(self.connection_name, setting)
            if isinstance(widget, ttk.Combobox):
                widget.set(value)
            else:
                widget.insert(0, value)

    def save_settings(self):
        """Save settings to the configuration file."""
        for setting, widget in self.entries.items():
            value = widget.get()
            self.config.set(self.connection_name, setting, value)
        with open("../configs/config.ini", "w") as configfile:
            self.config.write(configfile)
        messagebox.showinfo("Settings Saved", "Settings have been saved successfully.")
        self.destroy()


class SerialToUDPApp:
    def __init__(self, master):
        self.interval_entry = None
        self.master = master
        master.title("Serial to UDP Bridge")
        master.geometry("680x680")  # Adjusted window size
        master.resizable(False, False)  # Window not resizable

        self.config = configparser.ConfigParser()
        self.config.read(resource_path('config.ini'))
        self.ip_list = {k: v for k, v in self.config.items('IP_List')}
        self.connections = [section for section in self.config.sections() if section.startswith('Connection')]
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

        # interval
        self.interval_entry = self.add_common_setting("Sampling Interval (ms)",
                                                      "The sampling interval in milliseconds.", 3)

        # Create buttons to open settings windows for each connection
        for idx, connection in enumerate(self.connections, start=4):
            connection_name = self.config.get(connection, "name")
            button = ttk.Button(self.frame, text=f"Settings for {connection_name}",
                                command=lambda c=connection: self.open_settings_window(c))
            button.grid(row=idx, column=0, columnspan=2, pady=10)

        # Add start and stop buttons
        self.start_button = ttk.Button(self.frame, text="Start Bridge", command=self.start_bridge)
        self.start_button.grid(row=4 + len(self.connections), column=0, pady=10)

        self.stop_button = ttk.Button(self.frame, text="Stop Bridge", command=self.stop_bridge, state=tk.DISABLED)
        self.stop_button.grid(row=4 + len(self.connections), column=1, pady=10)

        # Clear log button
        self.clear_log_button = ttk.Button(self.frame, text="Clear Log", command=self.clear_log)
        self.clear_log_button.grid(row=5 + len(self.connections), column=0, columnspan=2, pady=10)

        # Status label
        self.status_label = ttk.Label(self.frame, text="Status: Not running")
        self.status_label.grid(row=6 + len(self.connections), column=0, columnspan=2, pady=10)

        # Log text area with scrollbars
        self.log_frame = ttk.Frame(self.master)
        self.log_frame.grid(row=7 + len(self.connections), column=0, columnspan=2, pady=10,
                            sticky=(tk.W, tk.E, tk.N, tk.S))
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

            self.interval = (int(self.interval_entry.get()))
            self.config.set('Common', 'target_ip', self.target_ip)
            self.config.set('Common', 'interval', str(self.interval))
            self.interval = self.interval / 1000.0
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
        baud_rate = self.config.getint(connection, 'baud_rate')
        data_bits = self.config.getint(connection, 'data_bits')
        parity = self.config.get(connection, 'parity')[0].upper()
        stop_bits = self.config.getfloat(connection, 'stop_bits')
        buffer_size_str = self.config.get(connection, 'buffer_size', fallback='default')
        conn_direction = self.config.get(connection, 'Mode')

        # Convert buffer size to integer or set to None for default
        if buffer_size_str == 'default':
            buffer_size = None
        else:
            buffer_size = int(buffer_size_str)

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
            read_thread = threading.Thread(target=self.read_and_send_serial_data,
                                           args=(serial_conn, udp_socket, target_port, buffer_size))
            self.threads.extend([read_thread])
            read_thread.start()
        elif conn_direction == "Rx":
            listen_thread = threading.Thread(target=self.listen_and_forward_udp_data, args=(serial_conn, listen_socket))
            self.threads.extend([listen_thread])
            listen_thread.start()
        elif conn_direction == "Tx/Rx":
            read_thread = threading.Thread(target=self.read_and_send_serial_data,
                                           args=(serial_conn, udp_socket, target_port, buffer_size))
            listen_thread = threading.Thread(target=self.listen_and_forward_udp_data, args=(serial_conn, listen_socket))
            self.threads.extend([read_thread, listen_thread])
            read_thread.start()
            listen_thread.start()

    def read_and_send_serial_data(self, serial_conn, udp_socket, target_port, buffer_size):
        """Read data from serial port and send it via UDP."""
        try:
            while not self.stop_event.is_set():
                if serial_conn.in_waiting > 0:
                    data = serial_conn.read(
                        min(buffer_size, serial_conn.in_waiting) if buffer_size else serial_conn.in_waiting)
                    udp_socket.sendto(data, (self.target_ip, target_port))
                    self.log(f"Sent: {data}")
                time.sleep(self.interval)
        except Exception as e:
            self.log(f"Error in read_and_send_serial_data: {e}")
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
                        self.log(f"Received from {addr}: {data}")
        except Exception as e:
            self.log(f"Error in listen_and_forward_udp_data: {e}")
        finally:
            listen_socket.close()

    def error_listener(self):
        """Listen for error messages on port 7000 and update the GUI."""
        listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listen_socket.bind(('', 7000))  # Default Comm port.
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
        udp_socket.sendto(start_packet, (self.target_ip, 7000))  # Hard coded default port
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
