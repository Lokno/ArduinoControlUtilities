# Servo Sequence Sketch Generator
# Generates an Arduino sketch from CSV Tables
# 
# usage: servo_sketch_generator.py [-h] [-r ROUTINE_TABLE] [-s SERVO_TABLE]
#
# If no arguments are given, the script will launch a GUI
#
# Routine Table Columns:
# Scene Name,Pin Position,Time,Ease In,Ease Out
#
# ServoInfo Table Columns:
# Pin,Full Sweep,Minimum,Maximum
#
# Each row in the routine table defines a servo sweep. 
# There can be multiple servos defined per scene.
# Each servo sweeps will be grouped by scene name in row-order.
# The first scene is an initialization scene, and is only visited at reset.
# The routine will loop though the remaining scenes forever.
#
# Requirements: python-benedict, argparse, appdirs, tk
#
# Install required modules with pip:
# > python -m pip install python-benedict argparse appdirs
#
# Additional Requirements for live demo: pyfirmata
#
# TODO: Handle stepper motors 
# degrees_per_steps = 360 / steps
# steps_to_advance = int(delta / steps)

from benedict import benedict

import appdirs
import os
import sys
import json

try:
    import pyfirmata
    import threading
    import platform
    import time
    
    major,minor,_ = platform.python_version_tuple()
    if major != '3':
        print('ERROR: Python 3 required to run.')
        sys.exit(-1)
    if minor >= '11':
        # 3.11 fix for property name change in inspect for pyfirmata
        import inspect
        if not hasattr(inspect, 'getargspec'):
            inspect.getargspec = inspect.getfullargspec

    pyfirmata_loaded = True
except:
    print('Warning: pyFirmata not found. Live Demo disabled.')
    pyfirmata_loaded = False

class SweepSketchGen:
    def __init__(self, pyfirmata_loaded):

        self.full_sweep = 270
        self.servo_speed_factor = 1.0
        self.servo_min_microseconds = 544
        self.servo_max_microseconds = 2400
        self.servo_standby_degrees = 135
        self.update_interval = 15
        self.reset_duration = 1000

        self.pyfirmata_loaded = pyfirmata_loaded

        self.loaded = False
        self.board  = None
        self.port   = None
        self.thread = None
        self.perform = False

        self.attached_servos = {}

    def validate_csv(self,file,field_name):
        success = True
        msg = ''
        if not file:
            msg = f"{field_name} is required."
            success = False
        elif not os.path.exists(file):
            msg = f"{field_name} does not exist."
            success = False
        elif not os.path.isfile(file):
            msg = f"{field_name} is not a file."
            success = False
        else:
            filename, file_extension = os.path.splitext(file)
            
            if file_extension != '.csv':
                msg = f"{field_name} is not a CSV file. It must end in '.csv'"
                success = False
        return success,msg

    def validate_dir(self,directory,field_name):
        success = True
        msg = ''
        if not os.path.exists(directory):
            msg = f"{field_name} does not exist."
            success = False
        elif not os.path.isdir(directory):
            msg = f"{field_name} is not a directory."
            success = False
        return success,msg

    def cubic_ease_out(self, t, b, c, d):
        t /= d
        t -= 1
        return c * (t * t * t + 1) + b
    
    def cubic_ease_in(self, t, b, c, d):
        t /= d
        return c*(t**3) + b

    def map(self, x, in_min, in_max, out_min, out_max):
        return (x - in_min) * (out_max - out_min) // (in_max - in_min) + out_min

    def constrain(self,x,xmin,xmax):
        return xmin if x < xmin else xmax if x > xmax else x

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

        if elapsed_time < ease_in_duration:
            speed = self.cubic_ease_out(elapsed_time, 0, 1, ease_in_duration)
        elif elapsed_time < (total_duration-ease_out_duration):
            speed = 1
        else:
            speed = self.cubic_ease_in(elapsed_time - total_duration + ease_out_duration, 1, -1, ease_out_duration)
    
        return speed

    def attach_servo(self,servo):
        pin = servo["Pin"]
        if pin not in self.attached_servos:
            self.attached_servos[pin] = self.board.get_pin(f'd:{pin}:s')
        servo['Servo'] = self.attached_servos[pin]

    def perform_scenes(self):
        print('Moving to standby position')
        for _,servo_data in self.servos.items():
            standby = self.map(int(servo_data['Standby']),0,int(servo_data['Full Sweep']),int(servo_data['Minimum']),int(servo_data['Maximum']))
            servo_data['Servo'].write(standby)
            servo_data['Current Position'] = standby
            servo_data['Start Position'] = standby
            servo_data['Minimum'] = int(servo_data['Minimum'])
            servo_data['Maximum'] = int(servo_data['Maximum'])

        time.sleep(1)

        current_scene = 0
        start_time = time.time()
        current_time = start_time

        total_scenes = len(self.scenes)

        while self.perform:
            scene_data = self.scenes[current_scene]
            scene_duration = max(int(d['Time']) for d in scene_data)

            time_last_iteration = current_time
            current_time = time.time()
            elapsed_time = (current_time-start_time)*1000
            delta_time = (current_time-time_last_iteration)*1000

            for sweep in scene_data:
                servo_data = self.servos[sweep['Pin']]
                target = self.map(int(sweep['Position']),0,int(servo_data['Full Sweep']),int(servo_data['Minimum']),int(servo_data['Maximum']));
                start_position = servo_data['Start Position']
                position = servo_data['Current Position']
                displacement = sweep['MaxDisplacement']
                ease_in = int(sweep['Ease In'])
                ease_out = int(sweep['Ease Out'])
                duration = int(sweep['Time'])

                if elapsed_time < duration and self.perform:
                    direction = 1 if target > start_position else -1
                    
                    speed = self.calculate_speed_at_time(elapsed_time, duration, ease_in, ease_out)
                    speed_factor = abs(target-start_position)/(displacement)

                    delta = direction*speed*delta_time*speed_factor
                    position += delta
                    position = self.constrain(position, servo_data['Minimum'],servo_data['Maximum'])

                    servo_data['Current Position'] = position
                    servo_data['Servo'].write(position)

            if (current_time-start_time)*1000 > scene_duration:
                if (current_scene := current_scene + 1) == total_scenes:
                    current_scene = 1
                print(f'Scene {current_scene}')
                start_time = current_time

                for _,servo_data in self.servos.items():
                    servo_data['Start Position'] = servo_data['Current Position']


            time.sleep(self.update_interval/1000) 

    def run(self,port,is_cmdline=False):
        if not self.loaded:
            msg='ERROR: Called run() before load()'
            if is_cmdline:
                print(msg)
            return False,msg

        if not self.pyfirmata_loaded:
            msg='ERROR: pyfirmata module required to simulate'
            if is_cmdline:
                print(msg)
            return False,msg

        if self.perform:
            self.perform = False
            time.sleep(1)

        if port != self.port:
            self.port = port
            if self.board is not None:
                self.board.exit()
            self.board = pyfirmata.Arduino(self.port)

        for _,servo_data in self.servos.items():
            self.attach_servo(servo_data)

        self.perform = True

        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self.perform_scenes)
            self.thread.start()

        return True,'Performing Sweeps'

    def load(self,routine_table,servo_table,is_cmdline):
        success,msg = self.validate_csv(routine_table,'Routine File')
        if not success:
            return success,msg
        if servo_table:
            success,msg = self.validate_csv(servo_table,'Servo File')
            if not success:
                return success,msg
        
        datatbl = benedict(routine_table, format='csv')

        self.loaded = True
        
        self.servos = {}
        self.scene_dict = {}
        
        self.servo_count = 0
        self.scene_order = []

        # Organize Scene Data
        for v in datatbl['values']:
            if v['Scene'] not in self.scene_dict:
                self.scene_order.append(v['Scene'])
                self.scene_dict[v['Scene']] = [v]
            else:
                self.scene_dict[v['Scene']].append(v)
        
            if v['Pin'].isnumeric():
                pin = int(v['Pin'])
                v['Pin'] = pin
                if pin in self.servos:
                    self.servos[pin]['Scenes'].append(v['Scene'])
                else:
                    self.servos[pin] = {'Index': self.servo_count, 'Pin': pin, 'Scenes': [v['Scene']]}
                    self.servo_count += 1

        self.scenes = [self.scene_dict[scene_name] for scene_name in self.scene_order]

        # Resolve starting positions
        servo_positions = {}
        for scene_data in self.scenes:
            for sweep in scene_data:
                servo_positions[int(sweep['Pin'])] = int(sweep['Position'])
    
        reset_scene = []
        for pin,position in servo_positions.items():
            self.servos[pin]['Standby'] = position
            reset_scene.append({
                'Scene':'0',
                'Name': f'Reset Servo on pin {pin}',
                'Pin':pin,
                'Position':str(position),
                'Time':str(self.reset_duration),
                'Ease In':str(self.reset_duration),
                'Ease Out':'0'})

        # Add reset scene
        self.scenes = [reset_scene] + self.scenes
        
        # Retrieve or set servo data
        if servo_table:
            datatbl = benedict(servo_table, format='csv')
            for v in datatbl['values']:
                if v['Pin'].isnumeric():
                    pin = int(v['Pin'])
                    v['Pin'] = pin
                    if pin not in self.servos and is_cmdline:
                        print(f'Warning: Servo on pin {pin} is not used in routine')
                    elif pin in self.servos:
                        self.servos[pin].update(v)

        for _,servo_data in self.servos.items():
            if 'Full Sweep' not in servo_data:
                servo_data['Full Sweep'] = self.full_sweep
            if 'Minimum' not in servo_data:
                servo_data['Minimum'] = self.servo_min_microseconds
            if 'Maximum' not in servo_data:
                servo_data['Maximum'] = self.servo_max_microseconds
            if 'Standby' not in servo_data:
                servo_data['Standby'] = self.servo_standby_degrees

        # Determine speed factors for each sweep
        for scene in self.scenes:
            for sweep in scene:
                if sweep['Pin']:
                    servo_data = self.servos[sweep['Pin']]
                    sweep['MaxDisplacement'] = self.estimate_servo_displacement(int(sweep['Time']), int(sweep['Ease In']), int(sweep['Ease Out']))

        return True, 'Tables loaded'

    def write_sketch( self, output_filename, use_motion, motion_pin ):
        if not self.loaded:
            return False,'Data Not Loaded'

        if use_motion and not motion_pin.isnumeric():
            return False,'Motion Pin Invalid'

        fout = open(output_filename,'w')
        
        # Print Header
        fout.write('''
#include <Servo.h>

#define UPDATE_INTERVAL {}

#ifndef TRUE
#define TRUE 1
#endif

#ifndef FALSE
#define FALSE 0
#endif
'''.format(self.update_interval))

        if use_motion:
            fout.write(f'\n#define MOTION_PIN {motion_pin}\n')

        # Print servo macros and variables
        
        for _,servo_data in self.servos.items():
            fout.write('''
// Servo on pin {Pin} settings

#define SERVO{Pin} {Index}
#define SERVO{Pin}_MIN {Minimum}
#define SERVO{Pin}_MAX {Maximum}
#define SERVO{Pin}_STANDBY_DEGREES {Standby}
#define SERVO{Pin}_DEGREES_MAX {Full Sweep}
'''.format(**servo_data))

        fout.write('''
typedef struct
{
    Servo servo;
    float positionf;
    short position;
    short scene_start_position;
    short pin;
    short min;
    short max;
    short standby;
    short degrees_max;
} ServoData;

''')

        fout.write('#define SERVO_COUNT {}\n'.format(self.servo_count))
        fout.write('ServoData servos[SERVO_COUNT];')
        fout.write('''

float lerp(float a, float b, float x) {
  return b*x+a*(1-x);
}

float cubic_ease_in(float t, float b, float c, float d) {
    t /= d;
    return c*t*t*t + b;
}

float cubic_ease_out(float t, float b, float c, float d) {
    t /= d;
    t--;
    return c*(t*t*t + 1) + b;
}

unsigned long scene_start_time;
unsigned long scene_last_update;
short current_scene;
short total_scenes;

void advance_scene() {

    if(++current_scene == total_scenes) current_scene = 1;

    scene_last_update = scene_start_time;

    for(short i = 0; i < SERVO_COUNT; i++) {
        servos[i].scene_start_position = servos[i].position;
        servos[i].positionf = (float)servos[i].position;
    }
}

short check_interval(unsigned long* start, unsigned long duration) {
    unsigned long curr = millis();
    short interval_over = FALSE;
    if((curr-*start) > duration) {
        *start = curr;
        interval_over = TRUE;
    }
    return interval_over;
}

float calculate_speed_at_time(unsigned long elapsed, unsigned long total_duration, unsigned long ease_in_duration, unsigned long ease_out_duration) {
    float speed = 0.0;

    // clamp to n-1
    elapsed = elapsed >= total_duration ? (total_duration-1) : elapsed;
    
    // Calculate speed at current time using cubic easing
    if (elapsed < ease_in_duration) {
        speed = cubic_ease_out(elapsed, 0, 1, ease_in_duration);
    } else if (elapsed < (total_duration-ease_out_duration)) {
        speed = 1;
    } else {
        speed = cubic_ease_in(elapsed - total_duration + ease_out_duration, 1, -1, ease_out_duration);
    }

    return speed;
}

void update_servo(unsigned long current_time, short index, short target, unsigned long duration, unsigned long ease_in, unsigned long ease_out, float max_displacement) {
    unsigned long elapsed_time = current_time-scene_start_time;
    unsigned long delta_time = current_time-scene_last_update;

    if( elapsed_time <= duration )
    {
        ServoData* s = &servos[index];
        short direction = target > s->scene_start_position ? 1 : -1;

        float speed = calculate_speed_at_time(elapsed_time, duration, ease_in, ease_out);
        float speed_factor = fabs(target-s->scene_start_position)/max_displacement;

        s->positionf += direction*speed*speed_factor*delta_time;

        s->position = constrain((short)s->positionf, servos[index].min, servos[index].max);
        s->servo.writeMicroseconds(s->position);
    }
}

''')

        # Print Setup Function
        
        fout.write('void setup() {')

        for i,(_,servo_data) in enumerate(self.servos.items()):
            fout.write('''
    servos[SERVO{Pin}].servo.attach({Pin}, SERVO{Pin}_MIN, SERVO{Pin}_MAX);
    servos[SERVO{Pin}].standby = map(SERVO{Pin}_STANDBY_DEGREES,0,SERVO{Pin}_DEGREES_MAX,SERVO{Pin}_MIN,SERVO{Pin}_MAX);
    servos[SERVO{Pin}].position = servos[SERVO{Pin}].standby;
    servos[SERVO{Pin}].positionf = (float)servos[SERVO{Pin}].position;
    servos[SERVO{Pin}].scene_start_position = servos[SERVO{Pin}].position;
    servos[SERVO{Pin}].min = SERVO{Pin}_MIN;
    servos[SERVO{Pin}].max = SERVO{Pin}_MAX;
    servos[SERVO{Pin}].degrees_max = SERVO{Pin}_DEGREES_MAX;
    servos[SERVO{Pin}].servo.writeMicroseconds(servos[SERVO{Pin}].position);
'''.format(i,**servo_data))

        if use_motion:
            fout.write(f'\n    pinMode(MOTION_PIN, INPUT);\n')

        fout.write('''
    current_scene = {};
    total_scenes = {};
    scene_start_time = millis();
    scene_last_update = scene_start_time;
}}

'''.format(0,len(self.scenes)))

        fout.write('''void loop() {
    unsigned long scene_interval;
    unsigned long current_time = millis();
''')

        if use_motion:
            fout.write('''
    if(current_scene != 0 && digitalRead(MOTION_PIN) == LOW) {
        current_scene = -1;
        scene_start_time = millis();
        advance_scene();
    }
''')

        fout.write('    switch(current_scene)\n    {\n')

        for i,scene_data in enumerate(self.scenes):
            fout.write('         case {}: // Scene {}\n'.format(i,scene_data[0]['Scene']))
        
            if i != 0 or use_motion:
                for servo_data in scene_data:
                    if servo_data['Name'] != 'Delay' and servo_data['Pin']:
                        fout.write('             // {}\n'.format(servo_data['Name']))
                        fout.write('             update_servo(current_time,SERVO{Pin},map({Position},0,SERVO{Pin}_DEGREES_MAX,SERVO{Pin}_MIN,SERVO{Pin}_MAX),{Time},{Ease In},{Ease Out},{MaxDisplacement:.5f});\n'.format(**servo_data))
        
            fout.write('             scene_interval = {};\n             break;\n'''.format( max(int(d['Time']) for d in scene_data) ))
         
        fout.write('''
    }}

    if({}check_interval(&scene_start_time, scene_interval)) advance_scene();

    scene_last_update = current_time;

    delay(UPDATE_INTERVAL);
}}'''.format('digitalRead(MOTION_PIN) == HIGH && ' if use_motion else ''))

        fout.close()
        return True, f'Wrote {output_filename}'

import tkinter as tk
from tkinter import filedialog

class FileSelectorGUI:
    def __init__(self, master, pyfirmata_loaded):

        self.app_name = "ServoSketchGenerator"
        self.app_author = "Lokno"

        config_data = self.load_config()

        self.sweep_gen = SweepSketchGen(pyfirmata_loaded)

        if not config_data:
            config_data['Routine'] = ''
            config_data['ServoInfo'] = ''
            config_data['OutputDir'] = '.'
            config_data['OutputFile'] = 'ServoSequence.ino'
            config_data['UseMotion'] = False
            config_data['MotionPin'] = ''

        self.master = master
        master.title("Servo Sketch Generator")

        self.routine_file_label = tk.Label(master, text="Select Routine CSV file:")
        self.routine_file_label.grid(row=0, column=0, sticky="w")

        self.routine_directory_text = tk.Text(master, height=1, width=40)
        self.routine_directory_text.grid(row=1, column=0, sticky="w")
        self.routine_directory_text.insert("1.0",config_data['Routine'])

        self.routine_file_button = tk.Button(master, text="Browse", command=lambda:self.browse_file(self.routine_directory_text))
        self.routine_file_button.grid(row=1, column=1, sticky="w")

        self.servo_file_label = tk.Label(master, text="Select ServoInfo CSV file (optional):")
        self.servo_file_label.grid(row=2, column=0, sticky="w")

        self.servo_directory_text = tk.Text(master, height=1, width=40)
        self.servo_directory_text.grid(row=3, column=0, sticky="w")
        self.servo_directory_text.insert("1.0",config_data['ServoInfo'])

        self.servo_file_button = tk.Button(master, text="Browse", command=lambda:self.browse_file(self.servo_directory_text))
        self.servo_file_button.grid(row=3, column=1, sticky="w")

        self.output_directory_label = tk.Label(master, text="Select output directory:")
        self.output_directory_label.grid(row=4, column=0, sticky="w")

        self.output_directory_text = tk.Text(master, height=1, width=40)
        self.output_directory_text.grid(row=5, column=0, sticky="w")
        self.output_directory_text.insert("1.0",config_data['OutputDir'])

        self.output_directory_button = tk.Button(master, text="Browse", command=lambda:self.browse_directory(self.output_directory_text))
        self.output_directory_button.grid(row=5, column=1, sticky="w")

        self.motion_frame = tk.Frame(master)
        self.motion_frame.grid(row=6, column=0, columnspan=2, padx=5, pady=5, sticky="w")

        self.use_motion = tk.BooleanVar()
        self.use_motion.set(config_data['UseMotion'])
        self.motion_checkbox = tk.Checkbutton(self.motion_frame, text='Use Motion Sensor',variable=self.use_motion, onvalue=True, offvalue=False, command=self.toggle_motion_pin)
        self.motion_checkbox.pack(side="left")

        self.motion_pin_label = tk.Label(self.motion_frame, text="Pin")
        self.motion_pin_label.pack(side="left")

        self.motion_pin_entry = tk.Entry(self.motion_frame, width=6, state=tk.NORMAL if config_data['UseMotion'] else tk.DISABLED)
        self.motion_pin_entry.insert("end", config_data['MotionPin'])
        self.motion_pin_entry.pack(side="left")

        self.output_frame = tk.Frame(master)
        self.output_frame.grid(row=7, column=0, columnspan=2, padx=5, pady=5, sticky="w")

        self.output_file_label = tk.Label(self.output_frame, text="Enter output file name:")
        self.output_file_label.pack(side="left")

        self.output_file_entry = tk.Entry(self.output_frame)
        self.output_file_entry.insert("end", config_data['OutputFile'])
        self.output_file_entry.pack(side="left", padx=5)

        self.button_frame = tk.Frame(master, width=200, height=50)
        self.button_frame.grid(row=8, column=0, columnspan=2)

        self.generate_button = tk.Button(self.button_frame, text="Write Sketch", command=self.generate_output)
        self.generate_button.grid(row=0, column=0, padx=5, pady=5)

        self.run_button = tk.Button(self.button_frame, text="Perform Scenes", command=self.live_demo)
        self.run_button.grid(row=0, column=1, padx=5, pady=5)

        self.port_label = tk.Label(self.button_frame, text="Port")
        self.port_label.grid(row=0, column=2)
        self.port_entry = tk.Entry(self.button_frame, width=6)
        self.port_entry.grid(row=0, column=3)

        if not pyfirmata_loaded:
            self.run_button.config(state=tk.DISABLED)
            self.port_label.config(state=tk.DISABLED)
            self.port_entry.config(state=tk.DISABLED)

        self.message_text = tk.Label(master, height=1, width=40)
        self.message_text.grid(row=9, column=0, columnspan=2, pady=5)

        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

    def toggle_motion_pin(self):
        self.motion_pin_entry.config(state=(tk.NORMAL if self.use_motion.get() else tk.DISABLED))

    def on_closing(self):
        self.sweep_gen.perform = False
        self.master.destroy()

    def store_config(self,data):
        data_dir = appdirs.user_data_dir(self.app_name, self.app_author)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        data_file = os.path.join(data_dir, "config.json")
        with open(data_file, "w") as f:
            f.write(json.dumps(data))
    
    def load_config(self):
        data_dir = appdirs.user_data_dir(self.app_name, self.app_author)
        data_file = os.path.join(data_dir, "config.json")
        if not os.path.exists(data_file):
            return {}
        with open(data_file, "r") as f:
            return json.loads(f.read())
        
    def browse_file(self, directory_text_widget):
        filename = filedialog.askopenfilename()
        directory_text_widget.delete("1.0", "end")
        directory_text_widget.insert("end", filename)

    def browse_directory(self, directory_text_widget):
        directory = filedialog.askdirectory()
        directory_text_widget.delete("1.0", "end")
        directory_text_widget.insert("end", directory)

    def update_message_text(self, message, is_error=False):
        self.message_text.config(text=message)
        if is_error:
            self.message_text.config(foreground="red")
        else:
            self.message_text.config(foreground="black")

    def load_data(self,routine_table,servo_table):
        return self.sweep_gen.load( routine_table, servo_table, False )

    def live_demo(self):
        routine_table = self.routine_directory_text.get("1.0", "end-1c")
        servo_table = self.servo_directory_text.get("1.0", "end-1c")
        success,msg = self.load_data(routine_table,servo_table)
        if success:
            port = self.port_entry.get()
            success,msg = self.sweep_gen.run(port)

        self.run_button.config(text="Stop Performing", command=self.end_demo)

        self.update_message_text(msg, False if success else True)

    def end_demo(self):
        self.sweep_gen.perform = False
        self.run_button.config(text="Perform Scenes", command=self.live_demo)

    def generate_output(self):
        routine_table = self.routine_directory_text.get("1.0", "end-1c")
        servo_table = self.servo_directory_text.get("1.0", "end-1c")
        output_directory = self.output_directory_text.get("1.0", "end-1c")
        output_filename = self.output_file_entry.get()
        success,msg = self.load_data(routine_table,servo_table)
        if success:
            success,msg = self.sweep_gen.validate_dir(output_directory,'Output Directory')
            if success:
                output_filename = os.path.join(output_directory,output_filename)
                success,msg = self.sweep_gen.write_sketch( output_filename, self.use_motion.get(), self.motion_pin_entry.get() )
                if success:
                    self.store_config({
                        'Routine': routine_table,
                        'ServoInfo': servo_table,
                        'OutputDir': output_directory, 
                        'OutputFile': self.output_file_entry.get(),
                        'UseMotion': self.use_motion.get(),
                        'MotionPin': self.motion_pin_entry.get()
                        })
        self.update_message_text(msg, False if success else True)

if __name__ == "__main__":
    if '-h' in sys.argv:
        printf('usage: servo_sketch_generator.py [-h] [ROUTINE_TABLE] [SERVO_TABLE]')
        printf('    ROUTINE_TABLE - Table that defines the servo sweeps in the animation')
        printf('    SERVO_TABLE - Table that defines details for each servo (optional)')
        sys.exit(-1)
    
    if len(sys.argv) > 1:
        routine_table = sys.argv[1]
        servo_table = None if len(sys.argv) < 2 else sys.argv[2] 

        sweep_gen = SweepSketchGen(pyfirmata_loaded)
        sweep_gen.load(routine_table, servo_table, True)
        success,msg = sweep_gen.write_sketch( 'ServoSequence.ino' )
        if not success:
            print(msg)
    else:
        root = tk.Tk()
        app = FileSelectorGUI(root,pyfirmata_loaded)
        root.mainloop()
