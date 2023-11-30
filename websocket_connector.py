# Websocket Server to directly control the GPIO output of a microcontroller
# Designed to be used with the Websocket Sender node in Pixel Composer
#
# https://makham.itch.io/pixel-composer

import asyncio
import websockets
import json
import platform
import argparse
import logging
from serial import serialutil
import sys

import tracemalloc

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
    def __init__(self,event_loop):
        self.port = None
        self.board = None
        self.io = {}
        self.schema = {
            'digital' : tuple(x for x in range(20)), # Use all analog pins: A0-A5(14-19).
            'analog' : (), # Analog pins has been used as digital ones
            'pwm' : (3, 5, 6, 9, 10, 11),
            'use_ports' : True,
            'disabled' : (0, 1) # Rx, Tx, Crystal
        }
        self.module_name = "PyFirmata"
        self.event_loop = event_loop

    async def connect(self,port,module_name,layout=None):
        if self.board is None:
            self.port = port
            self.module_name = module_name
            try:
                if self.module_name == "PyFirmata" and 'pyfirmata' not in sys.modules:
                    global pyfirmata
                    import pyfirmata
                    logging.info('Imported PyFirmata')
                elif self.module_name == "Telemetrix" and 'telemetrix' not in sys.modules:
                    global telemetrix
                    from telemetrix import telemetrix
                elif self.module_name == "TelemetrixAioEsp32" and 'telemetrix_aio_esp32' not in sys.modules:
                    global telemetrix_aio_esp32
                    from telemetrix_aio_esp32 import telemetrix_aio_esp32
            except:
                logging.info(f"Failed to import module {self.module_name}")
                return

            try:
                if layout is not None:
                    self.schema = layout

                if self.module_name == "PyFirmata":
                    self.board = pyfirmata.Board(self.port,layout=self.schema)
                elif self.module_name == "Telemetrix":
                    if port is not None:
                        self.board = telemetrix.Telemetrix(port)
                    else:
                        self.board = telemetrix.Telemetrix()
                        self.port = self.board.serial_port.port
                elif self.module_name == "TelemetrixAioEsp32":
                    self.board = telemetrix_aio_esp32.TelemetrixAioEsp32(transport_address=port,loop=self.event_loop,autostart=False)
                    await self.board.start_aio()
                    self.port = port

                logging.info(f"Connected to {self.port}")
                self.io = {}
            except Exception as connection_error:  
                import traceback
                traceback.print_exc()
                logging.error(f"Failed to connect to {self.port}. Error: {str(connection_error)}")
                self.board = None

    async def disconnect(self):
        if self.board is not None:
            if self.module_name == "PyFirmata":
                self.board.exit()
            elif self.module_name == "Telemetrix":
                self.board.shutdown()
            elif self.module_name == "TelemetrixAioEsp32":
                await self.board.shutdown()

            self.board = None
            self.io = {}

    def is_connected(self):
        return self.board is not None

    async def update(self, data):
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

            # we must demote a pin to pure digital output if pwm is not supported
            if io_type == 'digital_pwm' and pin not in self.schema['pwm']:
                io_type = 'digital'

            if self.module_name == 'PyFirmata':
                if pin not in self.io:
                    if io_type == 'servo':
                        self.io[pin] = self.board.get_pin(f'd:{pin}:s')
                    elif io_type == 'digital':
                        self.io[pin] = self.board.get_pin(f'd:{pin}:o')
                        self.io[pin].mode = pyfirmata.OUTPUT
                    elif io_type == 'digital_pwm':
                        self.io[pin] = self.board.get_pin(f'd:{pin}:p')

                if io_type == 'servo':
                    self.io[pin].write(max(0, min(int(value), 180)))
                elif io_type == 'digital':
                    self.io[pin].write(max(0, min(int(value), 1)))
                elif io_type == 'digital_pwm' or io_type == 'pwm':
                    self.io[pin].write(max(0, min(int(value), 255))/255.0)
            elif self.module_name == 'Telemetrix':
                if pin not in self.io:
                    if io_type == 'servo':
                        self.io[pin] = True
                        self.board.set_pin_mode_servo(pin,544,2400)
                    elif io_type == 'digital':
                        self.io[pin] = True
                        self.board.set_pin_mode_digital_output(pin)
                    elif io_type == 'digital_pwm' or io_type == 'pwm':
                        self.io[pin] = True
                        self.board.set_pin_mode_analog_output(pin)

                if io_type == 'servo':
                    self.board.servo_write(pin, max(0, min(int(value), 180)))
                elif io_type == 'digital':
                    self.board.digital_write(pin, max(0, min(int(value), 1)))
                elif io_type == 'digital_pwm' or io_type == 'pwm':
                    self.board.analog_write(pin, max(0, min(int(value), 255))/255.0)
            elif self.module_name == 'TelemetrixAioEsp32':
                if pin not in self.io:
                    if io_type == 'servo':
                        self.io[pin] = True
                        await self.board.set_pin_mode_servo(pin,544,2400)
                    elif io_type == 'digital':
                        self.io[pin] = True
                        await self.board.set_pin_mode_digital_output(pin)
                    elif io_type == 'digital_pwm' or io_type == 'pwm':
                        self.io[pin] = True
                        await self.board.set_pin_mode_analog_output(pin)

                if io_type == 'servo':
                    await self.board.servo_write(pin, max(0, min(int(value), 180)))
                elif io_type == 'digital':
                    await self.board.digital_write(pin, max(0, min(int(value), 1)))
                elif io_type == 'digital_pwm' or io_type == 'pwm':
                    await self.board.analog_write(pin, max(0, min(int(value), 255))/255.0)

class WebSocketServer:
    def __init__(self,event_loop):
        self.host = "127.0.0.1"
        self.port = 22300
        self.server = None
        self.connected_clients = set()
        self.board_ctrl = BoardControl(event_loop)
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
                await self.board_ctrl.update(data)

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

    async def connect(self, port, module_name, layout=None):
         await self.board_ctrl.connect(port, module_name, layout)

    async def disconnect(self):
        await self.board_ctrl.disconnect()

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
            if isinstance(v,float):
                values.append(str(max(0, min(int(v), 255))))
            elif isinstance(v,bool):
                values.append(str(int(v)))
            elif isinstance(v,int):
                values.append(str(max(0, min(v, 255))))
            else:
                values.append(str(v))

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
        self.root.title("Websocket Connector")

        self.app_name = "WebsocketConnector"
        self.app_author = "Lokno"

        config_data = self.load_config()

        if not config_data:
            config_data['csv_file'] = ''
            config_data['host'] = "127.0.0.1"
            config_data['port'] = '22300'
            config_data['module_attrib'] = ''
            config_data['module_name'] = 'PyFirmata'

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
        self.comm_port_label = tk.Label(self.controller_frame, text="Serial Port:" if config_data['module_name'] != 'TelemetrixAioEsp32' else 'IP Address:')
        self.comm_port_label.pack(side="left")
        self.comm_port_entry = tk.Entry(self.controller_frame)
        self.comm_port_entry.pack(side="left", padx=5)
        self.comm_port_entry.insert("end",config_data['module_attrib'])

        self.connect_button = tk.Button(self.controller_frame, text="Connect", command=self.connect)
        self.connect_button.pack(side="left", padx=5)

        self.controller_module_name = tk.StringVar() 
        self.controller_module_name.trace_add("write", self.module_changed) 
        self.controller_module_name.set( config_data['module_name'] ) 

        self.controller_module_name_dropdown = tk.OptionMenu( self.controller_frame, self.controller_module_name , 'PyFirmata', 'Telemetrix', 'TelemetrixAioEsp32' ) 
        self.controller_module_name_dropdown.pack(side="left", padx=5)

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

        self.event_loop = asyncio.get_event_loop()
        asyncio.set_event_loop(self.event_loop)

        self.server = WebSocketServer(self.event_loop)
        self.server.set_host(config_data['host'])
        self.server.set_port(config_data['port'])
        self.server.set_csv_file(config_data['csv_file'])
        self.server.enable_csv(False)

        self.showing = True

        self.re_host = re.compile("([0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+|localhost)")

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.request_connection_change = False

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

            if self.request_connection_change:
                self.request_connection_change = False

                if self.server.is_connected():
                    await self.server.disconnect()
                    self.connect_button["text"] = 'Connect'
                    self.update_status('Disconnected')
                    self.controller_module_name_dropdown['state'] = tk.NORMAL
                else:
                    comm_port = self.comm_port_entry.get().strip()
                    module_name = self.controller_module_name.get()
                    if module_name == 'Telemetrix' or comm_port != '':
                        if comm_port == '':
                            comm_port = None
                        await self.server.connect(comm_port,module_name,self.load_board_schema())
                        if self.server.is_connected():
                            self.connect_button["text"] = 'Disconnect'
                            self.controller_module_name_dropdown['state'] = tk.DISABLED
                            self.update_status('Connected Successfully')
                        else:
                            self.update_status('Connection Failed', True)
                    else:
                        self.update_status(f'{"Serial Port" if module_name == "PyFirmata" else "IP Address"} Cannot Be Empty', True)

                self.connect_button['state'] = tk.NORMAL

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
        self.request_connection_change = True
        self.connect_button['state'] = tk.DISABLED

    def checkbox_changed(self, *args):
        if self.enable_csv_var.get() == 1:
            logging.debug("CSV Output Enabled")
            self.server.enable_csv(True)

        else:
            logging.debug("CSV Output Disabled")
            self.server.enable_csv(False)

    def module_changed(self, *args):
        module_name = self.controller_module_name.get()
        if module_name == 'TelemetrixAioEsp32':
            self.comm_port_label["text"] = 'IP Address:'
        else:
            self.comm_port_label["text"] = 'Serial Port:'

    def on_closing(self):
        if self.server.is_running():
            self.server.stop()
            self.update_status('Stopping')
        self.showing = False

        self.store_config({
            'csv_file': self.csv_entry.get(),
            'host': self.host_entry.get(),
            'port': self.port_entry.get(),
            'module_attrib' : self.comm_port_entry.get().strip(),
            'module_name' : self.controller_module_name.get(),
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

    def load_board_schema(self):
        board_schema = None
        if os.path.exists("board_schema.json"):
            with open("board_schema.json","r") as f:
                schema_file = f.read()
            try:
                board_schema = json.loads(schema_file)
            except json.decoder.JSONDecodeError:
                logging.info("Error loading board_schema.json.")
                logging.info("Using default board layout...")
        return board_schema

    def run(self):
        self.event_loop.run_until_complete(self.show())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Websocket Server to directly control the GPIO output of a microcontroller")

    # Optional arguments
    parser.add_argument("--host", nargs="?", help="host for websocket (default: 127.0.0.1)")
    parser.add_argument("-p", "--port", type=int, nargs="?", help="port for websocket (default: 22300)")
    parser.add_argument("--csv", nargs="?", help="Optional CSV file for dumping GPIO output values each frame")
    parser.add_argument("-d", "--debug", nargs="?", help="Enable Logging")
    parser.add_argument("-s", "--serial", nargs="?", help="serial port of microcontroller")
    
    args = parser.parse_args()

    tracemalloc.start()

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