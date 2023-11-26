# Websocket Server to directly control the GPIO output of a microcontroller
# Designed to be used with the Websocket Sender node in Pixel Composer
#
# https://makham.itch.io/pixel-composer

import asyncio
import websockets
import pyfirmata
import json
import platform
import argparse
import logging
from serial import serialutil

major,minor,_ = platform.python_version_tuple()
if major != '3':
    logging.error('ERROR: Python 3 required to run.')
    sys.exit(-1)
if minor >= '11':
    # 3.11 fix for property name change in inspect for pyfirmata
    import inspect
    if not hasattr(inspect, 'getargspec'):
        inspect.getargspec = inspect.getfullargspec

class BoardControl:
    def __init__(self):
        self.port = None
        self.board = None
        self.io = {}

    def clamp(self, x, min_val, max_val):
        return max(min_val, min(x, max_val))

    def connect(self,port,layout=None):
        if self.board is None:
            self.port = port
            try:
                self.board = pyfirmata.Arduino(self.port)
                logging.info(f"Connected to {self.port}")
                self.io = {}
            except serialutil.SerialException:
                logging.info(f"Failed to connect to {self.port}")
                self.board = None

    def disconnect(self):
        if self.board is not None:
            self.board.exit()
            self.board = None
            self.io = {}

    def is_connected(self):
        return self.board is not None

    def update(self, data):
        if self.board is None:
            return

        gdata = {}

        for key, value in data.items():
            if key == "port" or key == "frame":
                continue
            attrib,name = key.split('_')
            if name not in gdata:
                gdata[name] = {}
            gdata[name][attrib] = value

        for io_name,io_attrib in gdata.items():
            pin = int(io_attrib['pin'])
            value = io_attrib['value']
            io_type = io_attrib['type']

            if pin not in self.io:
                if io_type == 'servo':
                    self.io[pin] = self.board.get_pin(f'd:{pin}:s')
                elif io_type == 'digital':
                    self.io[pin] = self.board.get_pin(f'd:{pin}:o')
                elif io_type == 'analog':
                    self.io[pin] = self.board.get_pin(f'a:{pin}:o')
                elif io_type == 'digital_pwm':
                    self.io[pin] = self.board.get_pin(f'd:{pin}:p')
                elif io_type == 'analog_pwm':
                    self.io[pin] = self.board.get_pin(f'a:{pin}:p')

            if io_type == 'servo':
                self.io[pin].write(self.clamp(int(value),0,180))
            elif io_type == 'digital':
                self.io[pin].write(self.clamp(int(value),0,1))
            elif io_type == 'analog':
                self.io[pin].write(self.clamp(int(value),0,1))
            elif io_type == 'digital_pwm':
                self.io[pin].write(self.clamp(value,0.0,1.0))
            elif io_type == 'analog_pwm':
                self.io[pin].write(self.clamp(value,0.0,1.0))

class WebSocketServer:
    def __init__(self):
        self.host = "127.0.0.1"
        self.port = 22300
        self.server = None
        self.connected_clients = set()
        self.board_ctrl = BoardControl()
        self.write_csv = False
        self.csv_file_name = None

    async def register(self,websocket):
        self.connected_clients.add(websocket)
        logging.info(f"Client connected: {websocket.remote_address}")
    
    async def unregister(self,websocket):
        self.connected_clients.remove(websocket)
        logging.info(f"Client disconnected: {websocket.remote_address}")

    async def echo(self, websocket, path):
        await self.register(websocket)
        try:
            async for message in websocket:
                logging.debug(message)
                data = json.loads(message)
                self.board_ctrl.update(data)

                if self.write_csv:
                    self.write_csv_row(self.csv_file_name,data)
        except websockets.exceptions.ConnectionClosed as e:
            logging.info(f"Connection closed with {websocket.remote_address}: {e.reason}")
        finally:
            await self.unregister(websocket)

    async def show(self):
        while self.showing:
            self.root.update()
            await asyncio.sleep(0.1)

    async def main(self):
        try:
            self.server = await websockets.serve(self.echo, self.host, self.port)
            await self.server.wait_closed()
        except asyncio.exceptions.CancelledError as e:
            pass

    def set_host(self, host):
        self.host = host

    def set_port(self, port):
        self.port = port

    def set_csv_file(self, csv_file_name):
        self.csv_file_name = csv_file_name

    def enable_csv(self, enable):
        self.write_csv = enable

    def connect(self, port, layout=None):
         self.board_ctrl.connect(port, layout)

    def disconnect(self):
        self.board_ctrl.disconnect()

    def is_connected(self):
        return self.board_ctrl.is_connected()

    def start(self):
        if not self.is_running():
            asyncio.create_task(self.main())

    def stop(self):
        if self.is_running():
            self.server.close()

    def is_running(self):
        return self.server is not None and self.server.is_serving()

    def write_csv_row(self, filename, data): 
        keys = sorted(data.keys())
        values = []

        for key in keys:
            v = data[key]
            if isinstance(v,str):
                values.append(v)
            elif isinstance(v,float):
                values.append(str(int(v)))
            elif isinstance(v,bool):
                values.append(str(int(v)))
            else:
                values.append(str(v))

        if 'port' in keys:
            idx = keys.index('port')
            keys = list(keys)
            values = list(values)
            keys.pop(idx)
            values.pop(idx)
    
        if not os.path.exists(self.csv_file_name):
            with open(filename,'w') as f:
                f.write(','.join(keys) + '\n')
    
        with open(filename,'a') as f:
            f.write(','.join(values) + '\n')

    def clear_csv(self):
        if self.csv_file_name is not None and os.path.exists(self.csv_file_name):
            os.remove(self.csv_file_name)

class WebSocketGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Websocket PyFirmata")

        self.app_name = "WebsocketPyFirmata"
        self.app_author = "Lokno"

        config_data = self.load_config()

        if not config_data:
            config_data['csv_file'] = ''
            config_data['host'] = "127.0.0.1"
            config_data['port'] = '22300'
            config_data['comm_port'] = ''

        # Host and Port Entry
        self.server_frame = tk.Frame(self.root)
        self.server_frame.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)

        self.host_label = tk.Label(self.server_frame, text="Host:")
        self.host_label.pack(side="left")
        self.host_entry = tk.Entry(self.server_frame)
        self.host_entry.pack(side="left", padx=5)
        self.host_entry.insert("end",config_data['host'])  

        self.port_label = tk.Label(self.server_frame, text="Port:")
        self.port_label.pack(side="left", padx=5)
        self.port_entry = tk.Entry(self.server_frame, width=10)
        self.port_entry.pack(side="left", padx=5)
        self.port_entry.insert("end",config_data['port'])  

        # Run and Stop Buttons
        self.run_button = tk.Button(self.server_frame, text="Run Server", command=self.start_stop_server)
        self.run_button.pack(side="left", padx=5)

        # Mircocontroller
        self.controller_frame = tk.Frame(self.root)
        self.controller_frame.grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.comm_port_label = tk.Label(self.controller_frame, text="Serial Port:")
        self.comm_port_label.pack(side="left")
        self.comm_port_entry = tk.Entry(self.controller_frame)
        self.comm_port_entry.pack(side="left", padx=5)
        self.comm_port_entry.insert("end",config_data['comm_port'])

        self.connect_button = tk.Button(self.controller_frame, text="Connect", command=self.connect)
        self.connect_button.pack(side="left", padx=5)

        # CSV File Entry and Browse Button
        self.csv_frame = tk.Frame(self.root)
        self.csv_frame.grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        self.csv_label = tk.Label(self.csv_frame, text="CSV File:")
        self.csv_label.pack(side="left")
        self.csv_entry = tk.Entry(self.csv_frame)
        self.csv_entry.pack(side="left", padx=5)
        self.csv_entry.insert("end",config_data['csv_file'])  

        self.browse_button = tk.Button(self.csv_frame, text="Browse", command=self.browse)
        self.browse_button.pack(side="left", padx=5)

        # Enable CSV Output Checkbox and Clear CSV Button
        self.enable_csv_var = tk.IntVar()
        self.enable_csv_var.trace_add("write", self.checkbox_changed) 
        self.enable_csv_checkbox = tk.Checkbutton(self.csv_frame, text="Enable CSV Output", variable=self.enable_csv_var)
        self.enable_csv_checkbox.pack(side="left", padx=5)

        self.clear_csv_button = tk.Button(self.csv_frame, text="Clear CSV", command=self.clear_csv)
        self.clear_csv_button.pack(side="left", padx=5)

        self.message_text = tk.Label(self.root, height=1, width=40)
        self.message_text.grid(row=3, column=0, columnspan=2, pady=5)

        self.server = WebSocketServer()
        self.server.set_host(config_data['host'])
        self.server.set_port(config_data['port'])
        self.server.set_csv_file(config_data['csv_file'])
        self.server.enable_csv(False)

        self.event_loop = asyncio.get_event_loop()

        self.showing = True

        self.re_host = re.compile("([0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+|localhost)")

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def update_status(self, message, is_error=False):
        self.message_text.config(text=message)
        if is_error:
            self.message_text.config(foreground="red")
        else:
            self.message_text.config(foreground="black")

    def load_config(self):
        data_dir = appdirs.user_data_dir(self.app_name, self.app_author)
        data_file = os.path.join(data_dir, "config.json")
        if not os.path.exists(data_file):
            return {}
        with open(data_file, "r") as f:
            return json.loads(f.read())

    def store_config(self,data):
        data_dir = appdirs.user_data_dir(self.app_name, self.app_author)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        data_file = os.path.join(data_dir, "config.json")
        with open(data_file, "w") as f:
            f.write(json.dumps(data))

    async def show(self):
        while self.showing:
            self.root.update()
            await asyncio.sleep(0.1)

    def start_stop_server(self):
        if not self.server.is_running():

            host = self.host_entry.get()
            port = self.port_entry.get()

            if not self.re_host.match(host):
                self.update_status('Host name not valid',True)
            elif not port.isnumeric():
                self.update_status('Port not valid',True)
            else:

                self.server.set_host(host)
                self.server.set_port(port)
                self.update_status('Running')
                self.server.start();
                self.run_button["text"] = 'Stop Server'
        else:
            self.server.stop()
            self.update_status('Stopping')
            self.run_button["text"] = 'Start Server'

    def connect(self):
        if self.server.is_connected():
            self.server.disconnect()
            self.connect_button["text"] = 'Connect'
            self.update_status('Disconnected')
        else:
            comm_port = self.comm_port_entry.get().strip()
            if comm_port != '':
                self.server.connect(comm_port)
                if self.server.is_connected():
                    self.connect_button["text"] = 'Disconnect'
                    self.update_status('Connected Successfully')
                else:
                    self.update_status('Connection Failed', True)
            else:
                self.update_status('Empty Serial Port', True)

    def checkbox_changed(self, *args):
        if self.enable_csv_var.get() == 1:
            logging.debug("CSV Output Enabled")
            self.server.enable_csv(True)

        else:
            logging.debug("CSV Output Disabled")
            self.server.enable_csv(False)

    def on_closing(self):
        if self.server.is_running():
            self.server.stop()
            self.update_status('Stopping')
        self.showing = False

        self.store_config({
            'csv_file': self.csv_entry.get(),
            'host': self.host_entry.get(),
            'port': self.port_entry.get(),
            'comm_port' : self.comm_port_entry.get(),
            })

        self.root.destroy()

    def browse(self):
        file_path = filedialog.asksaveasfilename(title="Select CSV File", filetypes=[("CSV files", "*.csv")])
        self.csv_entry.delete(0, tk.END)
        self.csv_entry.insert(0, file_path)
        self.server.set_csv_file(file_path)

    def clear_csv(self):
        logging.debug("Clear CSV button pressed")
        self.server.clear_csv()

    async def run_tk(self):
        try:
            await self.show();
        finally:
            self.event_loop.close()

    def run(self):
        asyncio.run(self.run_tk())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Websocket Server to directly control the GPIO output of a microcontroller")

    # Optional arguments
    parser.add_argument("--host", nargs="?", help="host for websocket (default: 127.0.0.1)")
    parser.add_argument("-p", "--port", type=int, nargs="?", help="port for websocket (default: 22300)")
    parser.add_argument("--csv", nargs="?", help="Optional CSV file for dumping GPIO output values each frame")
    parser.add_argument("-d", "--debug", nargs="?", help="Enable Logging")
    parser.add_argument("-s", "--serial", nargs="?", help="serial port of microcontroller")
    
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    serve_host = "127.0.0.1"
    serve_port = 22300

    if (args.csv is not None or args.host is not None or args.port is not None) and args.serial is not None:
        if args.host is not None:
            serve_host = args.host
    
        if args.port is not None:
            serve_port = args.port   

        server = WebSocketServer()
        server.set_host(serve_host)
        server.set_port(serve_port)

        if args.csv is not None:
            server.enable_csv(True)
            server.set_csv_file(args.csv)

        server.connect(args.serial)
    
        asyncio.run(server.main())
    else:
        import tkinter as tk
        from tkinter import filedialog
        import appdirs
        import os
        import re

        gui = WebSocketGUI()
        gui.run()