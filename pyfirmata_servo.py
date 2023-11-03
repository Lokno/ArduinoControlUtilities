# Live Servo Sweep Viewer

# Connects to a microcontroller running StandardFirmata
# and provides a GUI for addressing a servo.
# Servo position is presented digitally in the UI, and
# can be manually moved by clicking and dragging the needle.
# The GUI also allows for defining servo sweeps with various
# parameters for setting the duration of the sweep and cubic easing.
#
# Requirements: tkdial, pyfirmata
#
# pip install pyfirmata tkdial

import platform
import sys
import re
import logging
import threading
import time

logging.basicConfig(filename='error.log', level=logging.ERROR, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

major,minor,_ = platform.python_version_tuple()
if major != '3':
    logging.error('ERROR: Python 3 required to run.')
    sys.exit(-1)
if minor >= '11':
    # 3.11 fix for property name change in inspect for pyfirmata
    import inspect
    if not hasattr(inspect, 'getargspec'):
        inspect.getargspec = inspect.getfullargspec

try:
    import tkinter as tk
    import pyfirmata
    from tkdial import Meter
except Exception as e:
    logging.error("An error occurred: %s", str(e))

class SweepHistory:
    def __init__(self, primary):
        self.primary = primary
        self.create_widgets()

    def create_widgets(self):

        self.window = tk.Toplevel(self.primary)
        self.window.title("Sweep History")

        self.listbox = tk.Listbox(self.window, width=100, selectmode=tk.SINGLE)
        self.listbox.pack()
        
        self.button_frame = tk.Frame(self.window)
        self.button_frame.pack()
        
        self.remove_button = tk.Button(self.button_frame, text="Remove Action", command=self.remove_action)
        self.remove_button.pack(side=tk.LEFT)
        
        self.move_up_button = tk.Button(self.button_frame, text="Move Up", command=self.move_up)
        self.move_up_button.pack(side=tk.LEFT)
        
        self.move_down_button = tk.Button(self.button_frame, text="Move Down", command=self.move_down)
        self.move_down_button.pack(side=tk.LEFT)
        
    def move_up(self):
        selected_index = self.listbox.curselection()
        if selected_index:
            selected_index = int(selected_index[0])
            if selected_index > 0:
                text = self.listbox.get(selected_index)
                self.listbox.delete(selected_index)
                self.listbox.insert(selected_index - 1, text)
                self.listbox.selection_clear(0, tk.END)
                self.listbox.select_set(selected_index - 1)
    
    def move_down(self):
        selected_index = self.listbox.curselection()
        if selected_index:
            selected_index = int(selected_index[0])
            if selected_index < self.listbox.size() - 1:
                text = self.listbox.get(selected_index)
                self.listbox.delete(selected_index)
                self.listbox.insert(selected_index + 1, text)
                self.listbox.selection_clear(0, tk.END)
                self.listbox.select_set(selected_index + 1)
    
    def remove_action(self):
        selected_index = self.listbox.curselection()
        if selected_index:
            self.listbox.delete(selected_index)

    def add_action(self, action_text):
        if action_text:
            self.listbox.insert(tk.END, action_text)
    
    def select_first(self):
        if self.listbox.size() > 0:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.select_set(0)

    def select_next(self):
        advanced = False
        selected_index = self.listbox.curselection()
        if selected_index:
            selected_index = int(selected_index[0])
            if selected_index < self.listbox.size() - 1:
                advanced = True
                self.listbox.selection_clear(0, tk.END)
                self.listbox.select_set(selected_index + 1)
        return advanced

    def get_selection(self):
        selected = None
        selected_index = self.listbox.curselection()
        if selected_index:
            selected_index = int(selected_index[0])
            if selected_index >= 0:
                selected = self.listbox.get(selected_index)
        return selected

    def get_history(self):
        return self.listbox.get(0,self.listbox.size())

    def disable(self):
        self.remove_button.config(state=tk.DISABLED)
        self.move_up_button.config(state=tk.DISABLED)
        self.move_down_button.config(state=tk.DISABLED)

    def enable(self):
        self.remove_button.config(state=tk.NORMAL)
        self.move_up_button.config(state=tk.NORMAL)
        self.move_down_button.config(state=tk.NORMAL)

class ServoTester:
    def __init__(self, primary):
        self.primary = primary
        self.create_widgets()

    def create_widgets(self):
        self.window = self.primary
        self.window.title("Servo Sweep Viewer")

        # add a label for each field
        tk.Label(self.window, text="Port").grid(row=0, column=0)
        tk.Label(self.window, text="PIN").grid(row=1, column=0)
        tk.Label(self.window, text="Max Angle").grid(row=2, column=0)
        tk.Label(self.window, text="Start").grid(row=3, column=0)
        tk.Label(self.window, text="End").grid(row=4, column=0)
        tk.Label(self.window, text="Duration").grid(row=5, column=0)
        tk.Label(self.window, text="Ease In").grid(row=6, column=0)
        tk.Label(self.window, text="Ease Out").grid(row=7, column=0)
        tk.Label(self.window, text="Update Interval").grid(row=8, column=0)

        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.port_entry = tk.Entry(self.window)
        self.port_entry.grid(row=0, column=1)
        self.pin_entry = tk.Entry(self.window)
        self.pin_entry.grid(row=1, column=1)
        self.max_angle_entry = tk.Entry(self.window, validate="focusout", validatecommand = self.update_marks)
        self.max_angle_entry.grid(row=2, column=1)
        self.start_entry = tk.Entry(self.window, validate="focusout", validatecommand = self.update_marks)
        self.start_entry.grid(row=3, column=1)
        self.end_entry = tk.Entry(self.window, validate="focusout", validatecommand = self.update_marks)
        self.end_entry.grid(row=4, column=1)
        self.duration_entry = tk.Entry(self.window)
        self.duration_entry.grid(row=5, column=1)
        self.ease_in_entry = tk.Entry(self.window)
        self.ease_in_entry.grid(row=6, column=1)
        self.ease_out_entry = tk.Entry(self.window)
        self.ease_out_entry.grid(row=7, column=1)

        self.interval_entry = tk.Entry(self.window)
        self.interval_entry.grid(row=8, column=1)

        self.button_frame = tk.Frame(self.window)
        self.button_frame.grid(row=10, columnspan=3, rowspan=10, padx=10, pady=10)

        self.update_button = tk.Button(self.button_frame, text="Sweep", command=self.run_sweep, width=20)
        self.update_button.pack(side=tk.LEFT)

        self.reverse_button = tk.Button(self.button_frame, text="Reverse", command=self.reverse, width=20)
        self.reverse_button.pack(side=tk.LEFT)

        self.perform_selected_button = tk.Button(self.button_frame, text="Perform Selected", command=self.perform_selected, width=20)
        self.perform_selected_button.pack(side=tk.LEFT)

        self.perform_history_button = tk.Button(self.button_frame, text="Perform History", command=self.perform_history, width=20)
        self.perform_history_button.pack(side=tk.LEFT)

        self.export_csv_button = tk.Button(self.button_frame, text="Export CSV", command=self.export_csv, width=20)
        self.export_csv_button.pack(side=tk.LEFT)

        self.dial = Meter(self.window, radius=300, start=0, end=270, start_angle=-90, end_angle=-270, border_width=0, 
               major_divisions=15, minor_divisions=1, fg="grey", text_font="DS-Digital 24",
               scale_color="white", needle_color="red", command = self.move_servo)

        self.dial.grid(row=0, column=2, rowspan=10, padx=10, pady=10)

        self.sweep_re = re.compile('Sweep Servo at Pin ([0-9]+) on ([^ ]+) from ([0-9]+) to ([0-9]+) for ([0-9]+)ms \(ease in for ([0-9]+)ms, ease out for ([0-9]+)ms\)')

        self.servos = {}
        self.thread = None
        self.board = None
        self.servo = None

        self.pin = 9
        self.max_angle = 180
        self.start = 0
        self.end = 180
        self.duration = 3000
        self.ease_in = 0
        self.ease_out = 0

        self.history_run = False
        self.select_from_history_run = False

        self.port = ''

        self.position = self.start

        self.perform_sweep = False

        self.update_interval = 15

        self.pin_entry.insert(0,str(self.pin))
        self.max_angle_entry.insert(0,str(self.max_angle))
        self.start_entry.insert(0,str(self.start))
        self.end_entry.insert(0,str(self.end))

        self.duration_entry.insert(0,str(self.duration))
        self.ease_in_entry.insert(0,str(self.ease_in))
        self.ease_out_entry.insert(0,str(self.ease_out))

        self.interval_entry.insert(0,str(self.update_interval))

        self.dial.bind("<Button-1>", self.on_left_click)
        self.dial.bind("<Button-2>", self.on_middle_click)
        self.dial.bind("<Button-3>", self.on_right_click)
        self.dial.bind("<MouseWheel>", self.on_mouse_scroll)

        if self.port:
            self.connect()

        self.update_marks()

        self.history_view = SweepHistory(self.window)

    def map(self, x, in_min, in_max, out_min, out_max):
        return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    def on_closing(self):
        self.perform_sweep = False
        if self.board is not None:
            self.board.exit()
        self.window.destroy()

    def on_mouse_scroll(self,event):
        self.dial.set(self.constrain(self.dial.get() + event.delta/120.0,0,self.max_angle))
        self.move_servo()

    def on_left_click(self,event):
        self.start_entry.delete(0, tk.END)
        self.start_entry.insert(0,str(int(self.dial.get())))
        self.update_marks()

    def on_middle_click(self,event):
        self.run_sweep()

    def on_right_click(self,event):
        self.end_entry.delete(0, tk.END)
        self.end_entry.insert(0,str(int(self.dial.get())))
        self.update_marks()

    def connect(self):
        if self.board is not None:
            self.board.exit()
        self.board = pyfirmata.Arduino(self.port)
        self.servos = {}
        self.set_servo(self.pin)

    def update_sweep(self,start,end,duration,ease_in,ease_out):
        self.start    = start
        self.end      = end
        self.duration = duration
        self.ease_in  = ease_in
        self.ease_out = ease_out

        self.displacement = self.estimate_servo_displacement(self.duration,self.ease_in,self.ease_out)

    def constrain(self,x,xmin,xmax):
        return xmin if x < xmin else xmax if x > xmax else x

    def iterate_sweep(self,elapsed_time,delta_time):
        direction = 1 if self.end > self.position else -1
        
        speed = self.calculate_speed_at_time(elapsed_time, self.duration, self.ease_in, self.ease_out)
        speed_factor = abs(self.end-self.start)/(self.displacement)

        self.position += direction*speed*delta_time*speed_factor
        self.position = self.constrain(self.position, 0, self.max_angle)

    def sweep(self):
        start_time = time.time()
        time_last_iteration = start_time
        duration_s = self.duration/1000
        current_time = time.time()
        elapsed = current_time-start_time
        while elapsed < duration_s and self.perform_sweep:
            self.iterate_sweep(elapsed*1000,(current_time-time_last_iteration)*1000)
            self.set_servo_pos(self.position)
            time.sleep(self.update_interval/1000)
            time_last_iteration = current_time
            current_time = time.time()
            elapsed = current_time-start_time

        self.perform_sweep = False
        self.update_button.config(state=tk.NORMAL)
        self.reverse_button.config(state=tk.NORMAL)
        self.perform_selected_button.config(state=tk.NORMAL)
        self.perform_history_button.config(state=tk.NORMAL)
        self.export_csv_button.config(state=tk.NORMAL)
        self.history_view.enable()
        self.on_sweep_complete()

    def move_servo(self):
        if self.servo is not None:
            if self.dial.get() > self.max_angle:
                self.dial.set(self.max_angle)
            self.servo.write(self.map(self.dial.get(),0.0,self.max_angle,0.0,180.0))

    def set_servo_pos(self,p):
        self.dial.set(p)
        self.servo.write(self.map(p,0.0,self.max_angle,0.0,180.0))

    def set_servo(self,pin):
        if pin in self.servos:
            self.servo = self.servos[pin]
        else:
            self.servo = self.board.get_pin(f'd:{pin}:s')
            self.servos[pin] = self.servo
        self.pin = pin

    def reverse(self):
        start     = self.start_entry.get()
        end       = self.end_entry.get()

        self.start_entry.delete(0, tk.END)
        self.end_entry.delete(0, tk.END)

        self.start_entry.insert(0,str(end))
        self.end_entry.insert(0,str(start))

    def update_marks(self):
        max_angle = self.max_angle_entry.get()
        start     = self.start_entry.get()
        end       = self.end_entry.get()

        if max_angle.isnumeric():
            max_angle = int(max_angle)
        if start.isnumeric():
            start = int(start)
        if end.isnumeric():
            end = int(end)

        if start > end:
            temp = start
            start = end
            end = temp

        self.dial.set_mark(0, max_angle, "green")
        self.dial.set_mark(max_angle, 270, "black")  
        self.dial.set_mark(start,end,"blue")

    def run_sweep(self):
        port            = self.port_entry.get()
        pin             = self.pin_entry.get()
        max_angle       = self.max_angle_entry.get()
        start           = self.start_entry.get()
        end             = self.end_entry.get()
        duration        = self.duration_entry.get()
        ease_in         = self.ease_in_entry.get()
        ease_out        = self.ease_out_entry.get()
        update_interval = self.interval_entry.get()

        if port == "":
            return

        if pin.isnumeric():
            pin = int(pin)

        if max_angle.isnumeric():
            self.max_angle = int(max_angle)

        self.update_marks()

        if start.isnumeric():
            start = int(start)
        if end.isnumeric():
            end = int(end)
        if duration.isnumeric():
            duration = int(duration)
        if ease_in.isnumeric():
            ease_in = int(ease_in)
        if ease_out.isnumeric():
            ease_out = int(ease_out)

        self.run_sweep_ex(pin, port, start, end, duration, ease_in, ease_out)

    def run_sweep_ex(self, pin, port, start, end, duration, ease_in, ease_out):
        if not self.perform_sweep:
   
           if port != self.port:
               self.port = port
               self.connect()

           if pin != self.pin:
               self.set_servo(pin)

           self.update_button.config(state=tk.DISABLED)
           self.reverse_button.config(state=tk.DISABLED)
           self.perform_selected_button.config(state=tk.DISABLED)
           self.perform_history_button.config(state=tk.DISABLED)
           self.export_csv_button.config(state=tk.DISABLED)
           self.history_view.disable()

           if not self.history_run and not self.select_from_history_run:
               s = f'Sweep Servo at Pin {pin} on {port} from {start} to {end} for {duration}ms (ease in for {ease_in}ms, ease out for {ease_out}ms)'
               print(s)
               self.history_view.add_action(s)

           self.perform_sweep = False
           self.update_sweep(start,end,duration,ease_in,ease_out)
           self.set_servo_pos(start)
           if abs(self.position - self.start) > 1.0:
               time.sleep(0.5)
           self.perform_sweep = True
           self.position = start

           #if self.thread is None or not self.thread.is_alive():
           self.thread = threading.Thread(target=self.sweep)
           self.thread.start()

    def on_sweep_complete(self):
        if self.history_run:
            if self.history_view.select_next():
                self.perform_selected_sweep()
            else:
                self.history_run = False
        else:
            self.select_from_history_run = False

    def perform_history(self):
        self.history_run = True
        self.history_view.select_first()
        self.perform_selected_sweep()

    def perform_selected(self):
        self.select_from_history_run = True
        self.perform_selected_sweep()

    def perform_selected_sweep(self):
        selected_text = self.history_view.get_selection()
        if selected_text is not None:
            print(selected_text)
            m = self.sweep_re.match(self.history_view.get_selection())
            if m:
                self.select_from_history_run = True
                pin,port,start,end,duration,ease_in,ease_out = m.groups()
                pin      = int(pin)
                start    = int(start)
                end      = int(end)
                duration = int(duration)
                ease_in  = int(ease_in)
                ease_out = int(ease_out)
                self.run_sweep_ex(pin,port,start,end,duration,ease_in,ease_out)

    def export_csv(self):
        with open('servo_history.csv','w') as f:
            f.write('Scene,Name,Pin,Position,Time,Ease In,Ease Out\n')
            position = None
            scene_id = 1
            for sweep_text in self.history_view.get_history():
                m = self.sweep_re.match(sweep_text)
                if m:
                    pin,_,start,end,duration,ease_in,ease_out = m.groups()
    
                    if position is None:
                        position = start
                        f.write(f'0,,{pin},{position},500,0,0\n')
    
                    if start != position:
                        logging.warning(f'Sweep missing from {position} to {start}')
                        f.write(f'{scene_id},,{pin},{start},2000,0,0\n')
                        scene_id += scene_id
    
                    f.write(f'{scene_id},,{pin},{end},{duration},{ease_in},{ease_out}\n')

                    position = end
                    scene_id += scene_id

    def estimate_servo_displacement(self, total_duration, ease_in_duration, ease_out_duration):
        n = 10000 # fixed number of integration steps
        dt = total_duration / n
        displacement = 0
    
        for i in range(0,n):
            t = i*dt
            if t < ease_in_duration:
                speed = self.cubic_ease_out(t, 0, 1, ease_in_duration)
            elif t < (total_duration-ease_out_duration):
                speed = 1;
            else:
                speed = self.cubic_ease_in(t - total_duration + ease_out_duration, 1, -1, ease_out_duration)
    
            displacement += speed * dt
    
        return displacement

    def calculate_speed_at_time(self, elapsed_time, total_duration, ease_in_duration, ease_out_duration):
        speed = 0.0

        # Calculate speed at current time using cubic easing
        if elapsed_time < ease_in_duration:
            speed = self.cubic_ease_out(elapsed_time, 0, 1, ease_in_duration)
        elif elapsed_time < (total_duration-ease_out_duration):
            speed = 1
        else:
            speed = self.cubic_ease_in(elapsed_time - total_duration + ease_out_duration, 1, -1, ease_out_duration)
    
        return speed

    def cubic_ease_out(self, t, b, c, d):
        t /= d
        t -= 1
        return c * (t * t * t + 1) + b
    
    def cubic_ease_in(self, t, b, c, d):
        t /= d
        return c*(t**3) + b

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = ServoTester(root)
        root.mainloop()
    except Exception as e:
        logging.error("An error occurred: %s", str(e))
