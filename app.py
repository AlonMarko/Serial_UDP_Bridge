import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
import threading
import serial
import socket
import time
import configparser
import select
import os
import sys

def resource_path(relative_path):
    """ Get the absolute path to the resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
class SerialToUDPApp:
    def __init__(self, master):
        self.master = master
        master.title("Serial to UDP Bridge")
        master.geometry("800x600")
        master.resizable(False, False)

        self.config = configparser.ConfigParser()
        self.config.read(resource_path('config.ini'))

        self.ip_config = configparser.ConfigParser()
        self.ip_config.read(resource_path('ip_descriptions.ini'))

        self.settings = self.config['Settings']
        self.ip_list = self.config['IP_List']

        self.frame = ttk.Frame(master, padding="10 10 10 10")
        self.frame.grid(column=0, row=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        for i in range(1, 11):
            self.frame.rowconfigure(i, weight=1)
        for i in range(1, 3):
            self.frame.columnconfigure(i, weight=1)

        self.serial_port_label = ttk.Label(self.frame, text="Serial Port:")
        self.serial_port_label.grid(column=1, row=1, sticky=tk.W)
        self.serial_port_entry = ttk.Entry(self.frame)
        self.serial_port_entry.grid(column=2, row=1, sticky=(tk.W, tk.E))
        self.serial_port_entry.insert(0, self.settings.get('serial_port', ''))

        self.baud_rate_label = ttk.Label(self.frame, text="Baud Rate:")
        self.baud_rate_label.grid(column=1, row=2, sticky=tk.W)
        self.baud_rate_entry = ttk.Entry(self.frame)
        self.baud_rate_entry.grid(column=2, row=2, sticky=(tk.W, tk.E))
        self.baud_rate_entry.insert(0, self.settings.get('baud_rate', ''))

        self.target_ip_label = ttk.Label(self.frame, text="Target IP:")
        self.target_ip_label.grid(column=1, row=3, sticky=tk.W)
        self.target_ip_combobox = ttk.Combobox(self.frame)
        self.target_ip_combobox['values'] = [f"{key} - {self.ip_config[key]['description']}" for key in self.ip_list]
        self.target_ip_combobox.grid(column=2, row=3, sticky=(tk.W, tk.E))
        self.target_ip_combobox.set(self.settings.get('target_ip', ''))

        self.target_port_label = ttk.Label(self.frame, text="Target Port:")
        self.target_port_label.grid(column=1, row=4, sticky=tk.W)
        self.target_port_entry = ttk.Entry(self.frame)
        self.target_port_entry.grid(column=2, row=4, sticky=(tk.W, tk.E))
        self.target_port_entry.insert(0, self.settings.get('target_port', ''))

        self.interval_label = ttk.Label(self.frame, text="Sampling Interval (ms):")
        self.interval_label.grid(column=1, row=5, sticky=tk.W)
        self.interval_entry = ttk.Entry(self.frame)
        self.interval_entry.grid(column=2, row=5, sticky=(tk.W, tk.E))
        self.interval_entry.insert(0, self.settings.get('sampling_interval', ''))

        self.listen_port_label = ttk.Label(self.frame, text="Listening UDP Port:")
        self.listen_port_label.grid(column=1, row=6, sticky=tk.W)
        self.listen_port_entry = ttk.Entry(self.frame)
        self.listen_port_entry.grid(column=2, row=6, sticky=(tk.W, tk.E))
        self.listen_port_entry.insert(0, self.settings.get('listen_port', ''))

        self.start_button = ttk.Button(self.frame, text="Start Bridge", command=self.start_bridge)
        self.start_button.grid(column=1, row=7, sticky=tk.W)

        self.stop_button = ttk.Button(self.frame, text="Stop Bridge", command=self.stop_bridge, state=tk.DISABLED)
        self.stop_button.grid(column=2, row=7, sticky=tk.W)

        self.clear_log_button = ttk.Button(self.frame, text="Clear Log", command=self.clear_log)
        self.clear_log_button.grid(column=1, row=8, columnspan=2, sticky=tk.W)

        self.status_label = ttk.Label(self.frame, text="Status: Not running")
        self.status_label.grid(column=1, row=9, columnspan=2, sticky=(tk.W, tk.E))

        self.log_text = tk.Text(self.frame, state=tk.DISABLED, height=15, fg="black")
        self.log_text.grid(column=1, row=10, columnspan=2, sticky=(tk.W, tk.E))

        self.serial_conn = None
        self.udp_socket = None
        self.listen_socket = None
        self.s = None
        self.stop_event = threading.Event()

        for child in self.frame.winfo_children():
            child.grid_configure(padx=5, pady=5)

    def clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

    def start_bridge(self):
        serial_port = self.serial_port_entry.get()
        baud_rate = self.baud_rate_entry.get()
        target_ip_key = self.target_ip_combobox.get().split(' ')[0]
        target_ip = self.ip_list.get(target_ip_key, '')
        target_port = self.target_port_entry.get()
        listen_port = self.listen_port_entry.get()
        interval = self.interval_entry.get()

        if not serial_port or not baud_rate or not target_ip or not target_port or not listen_port or not interval:
            messagebox.showwarning("Input Error", "All fields must be filled.")
            return

        try:
            self.serial_conn = serial.Serial(serial_port, baudrate=int(baud_rate), timeout=1)
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.listen_socket.bind(('', int(listen_port)))
        except Exception as e:
            self.log(f"Error setting up connections: {e}")
            return

        self.log(f"Starting bridge: {serial_port} <-> UDP {target_ip}:{target_port}")

        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_label.config(text="Status: Running")

        self.interval = int(interval) / 1000.0
        self.stop_event.clear()

        self.read_thread = threading.Thread(target=self.read_and_send_serial_data, daemon=True)
        self.read_thread.start()
        self.listen_thread = threading.Thread(target=self.listen_and_forward_udp_data, daemon=True)
        self.listen_thread.start()

    def stop_bridge(self):
        self.stop_event.set()
        if self.read_thread.is_alive():
            self.read_thread.join()
        if self.listen_thread.is_alive():
            self.log("Stopping Listening UDP Thread")
            try:
                if self.listen_socket:
                    self.listen_socket.sendto(b'', self.listen_socket.getsockname())
                    self.log("Dummy packet sent.")
            except Exception as e:
                self.log(f"Exception while sending dummy packet: {e}")
            finally:
                if self.listen_socket:
                    self.listen_socket.close()
                    self.listen_socket = None
                    self.log("Socket closed.")

                # Wait for the thread to finish
            if self.listen_thread:
                self.log("Waiting for the thread to join.")
                self.listen_thread.join(timeout=2)  # Add a timeout to join
                self.log("Thread joined.")
            # self.listen_socket.sendto(b'', self.listen_socket.getsockname())
            # self.listen_thread.join()
        if self.listen_socket:
            self.listen_socket.close()
        if self.serial_conn:
            self.serial_conn.close()
        if self.udp_socket:
            self.udp_socket.close()


        self.log("Bridge stopped.")
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_label.config(text="Status: Not running")

    def read_and_send_serial_data(self):
        self.log("Serial->UDP thread started")
        while not self.stop_event.is_set():
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    self.udp_socket.sendto(data, (self.ip_list[self.target_ip_combobox.get().split(' ')[0]], int(self.target_port_entry.get())))
                    self.log(f"Sent: {data}")
            except Exception as e:
                self.log(f"Error: {e}")
            time.sleep(self.interval)

    def listen_and_forward_udp_data(self):
        """
        Listen for UDP packets and forward the data to the serial port.
        This function runs in a background thread.
        """
        self.listen_socket.setblocking(False)  # Set socket to non-blocking mode
        self.log("UDP->Serial thread started")
        while not self.stop_event.is_set():
            try:
                # print("recvfrom blocking....")
                ready_to_read, _, _ = select.select([self.listen_socket], [], [], 1.0)
                if ready_to_read:
                    data, addr = self.listen_socket.recvfrom(1024)  # Buffer size 1024 bytes
                    # print('recvfrom  %s  %s' % (data, addr))
                    if data:
                        self.serial_conn.write(data)
                        self.log(f"Received from {addr}: {data}")
                    else:
                        time.sleep(0.1)
            except socket.error as e:
                self.log(f"Error: {e}")
                break
        # if self.stop_event.is_set() and self.listen_thread.is_alive():
        #     self.listen_socket.shutdown(socket.SHUT_RDWR)
        # if self.stop_event.is_set():
        #
        #     self.listen_socket.close()
        #     print("closing")
        self.log("Listening thread terminated")

    def log(self, message):
        # print("log")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    app = SerialToUDPApp(root)
    root.mainloop()
