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

major,minor,_ = platform.python_version_tuple()
if major != '3':
    logging.error('ERROR: Python 3 required to run.')
    sys.exit(-1)
if minor >= '11':
    # 3.11 fix for property name change in inspect for pyfirmata
    import inspect
    if not hasattr(inspect, 'getargspec'):
        inspect.getargspec = inspect.getfullargspec

def write_csv_row(filename, data): 

    d = zip(data.keys(),data.values())
    d = sorted(d)
    keys,values = zip(*d)

    if int(data["frame"]) == 1:
        with open(filename,'w') as f:
            f.write(','.join(keys) + '\n')

    with open(filename,'a') as f:
        l = ''
        for i,v in enumerate(values):
            if isinstance(v,str):
                l += v
            elif isinstance(v,float):
                l += str(int(v))
            else:
                l += str(v)
            if i < (len(values) - 1):
                l += ','
        f.write(l + '\n')


class BoardControl:
    def __init__(self):
        self.port = None
        self.board = None
        self.io = {}

    def clamp(self, x, min_val, max_val):
        return max(min_val, min(x, max_val))

    def update(self, port, data):
        if port != self.port:
            if self.board is not None:
                self.board.exit()
            self.port = port
            self.board = pyfirmata.Arduino(self.port)
            self.io = {}

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
        

connected_clients = set()
board_ctrl = BoardControl()
write_csv = False
serve_host = "127.0.0.1"
serve_port = 22300
csv_file_name = "output.csv"

async def register(websocket):
    connected_clients.add(websocket)
    print(f"Client connected: {websocket.remote_address}")

async def unregister(websocket):
    connected_clients.remove(websocket)
    print(f"Client disconnected: {websocket.remote_address}")

async def echo(websocket, path):
    await register(websocket)
    try:
        async for message in websocket:
            data = json.loads(message)
            board_ctrl.update(data['port'],data)

            if write_csv:
                write_csv_row("output.csv",data)

    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed with {websocket.remote_address}: {e.reason}")
    finally:
        await unregister(websocket)

async def main():

    async with websockets.serve(echo, serve_host, serve_port):
        print(f'Serving Websocket at {serve_host}:{serve_port}')
        if write_csv:
            print(f'Writing output to {csv_file_name}')
        await asyncio.Future()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Websocket Server to directly control the GPIO output of a microcontroller")

    # Optional arguments
    parser.add_argument("--host", nargs="?", help="host for websocket (default: 127.0.0.1)")
    parser.add_argument("-p", "--port", type=int, nargs="?", help="port for websocket (default: 22300)")
    parser.add_argument("-c", "--csv", nargs="?", help="Optional CSV file for dumping GPIO output values each frame")
    
    args = parser.parse_args()

    if args.csv is not None:
        write_csv = True
        csv_file_name = args.csv

    if args.host is not None:
        serve_host = args.host

    if args.port is not None:
        serve_port = args.port   

    asyncio.run(main())