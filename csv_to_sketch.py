# Generate an Arduino Sketch from a CSV of GPIO output values
# Uses zero compression to save memory
# 
# CSV File Schema (in no particular order):
#
# frame,pin_A,value_A,type_A,pin_B,value_B,type_B,...
#
# frame (integer) - 1-indexed frame number
#     - file must have a complete set of frames 1 through n
#     - n will be determined automatically from the largest frame number in the file
# pin_ (integer)   - output pin number on microcontroller
# value_ (integer) - output value to go out on pin on this frame
# type_ (string)   - type of pin, assumed to be a constant
#     *** Valid Types ***
#     servo       - A connected servo on the pin. Uses Arduino Servo library (valid values 0-180)
#     digital     - digital pin (D2,D3,..) for digital output (valid values 0-1)
#     analog      - analog pin  (A0,A1,...) for digital output (valid values 0-1)
#     digital_pwm - digital pin (D2,D3,..) for pwm output (valid values 0-1)
#     analog_pwm  - analog pin  (A0,A1,...) for pwm output (valid values 0-1)
#

from benedict import benedict
import argparse
import os

def get_deltas(arr):
    deltas = []
    if len(arr) > 0:
        a = int(arr[0])
        for v in arr:
            deltas.append(int(v)-a)
            a = int(v)
    return deltas

def compress_zeros(arr):
    compressed_arr = []
    count = 0

    for element in arr:
        if element == 0:
            count += 1
        else:
            if count > 0:
                compressed_arr.append(0)
                compressed_arr.append(count)
                count = 0
            compressed_arr.append(element)

    if count > 0:
        compressed_arr.append(0)
        compressed_arr.append(count)

    return compressed_arr

def validate_csv(file,field_name):
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


def validate_dir(directory,field_name):
    success = True
    msg = ''
    if not os.path.exists(directory):
        msg = f"{field_name} does not exist."
        success = False
    elif not os.path.isdir(directory):
        msg = f"{field_name} is not a directory."
        success = False
    return success,msg

# Add a directory to the end of base_path with the
# same basename as filename, if isn't already there.
# Assumes base_path is a valid directory
def create_path(base_path, filename):
    filename_base,_ = os.path.splitext(filename)
    last_directory = os.path.basename(os.path.normpath(base_path))
    
    if last_directory != filename_base:
        base_path = os.path.join(base_path, filename_base)
        os.makedirs(base_path, exist_ok=True)
    
    complete_path = os.path.join(base_path, filename)
    return complete_path

def generate_arduino_sketch(csv_file,sketch_name,fps):

    if not sketch_name.endswith(".ino"):
        sketch_name += ".ino"
    if not csv_file.endswith(".csv"):
        csv_file += ".csv"

    d = benedict(csv_file, format="csv")

    # reduce a single set of frames
    frames = set()
    fdata = {}
    for row in d['values']:
        if 'frame' in row and int(row['frame']) not in frames:
            frame_idx = int(row['frame'])-1
            fdata[frame_idx] = row
            frames.add(frame_idx)

    # Check we have at least one of each frame
    if (max(frames)-min(frames)+1) != len(frames):
        print("Error: Missing frames.")
        return

    # Determine pins
    pins = {}
    for k,v in fdata[0].items():
        if k.startswith("pin_") or k.startswith("type_"):
            attrib,pin_name = k.split("_")
            if pin_name not in pins:
                pins[pin_name] = {'values' : []}
            pins[pin_name][attrib] = v
   
    for i in range(len(fdata)):
        for k,v in fdata[i].items():
            if k.startswith("value_"):
                _,pin_name = k.split("_")
                pins[pin_name]['values'].append(v)

    frame_count = len(fdata)

    servo_count = sum([1 for pin in pins if pins[pin]["type"] == "servo"])

    arduino_code = ''
    if servo_count > 0:
        arduino_code += '#include <Servo.h>\n'

    arduino_code += '''
typedef struct {
    int ypos;
    int xpos;
} CompressionInfo;

unsigned char next_value( unsigned char* values, CompressionInfo* info )
{
    signed char ret = 0;
    if( values[info->ypos] == 0 ) // in zero sequence
    {
        info->xpos++;
        if( info->xpos == values[info->ypos+1] )
        {
            info->xpos = 0;
            info->ypos+=2;
        }
    }
    else
    {
        ret = values[info->ypos];
        info->ypos++;
    }

    return ret;
}

'''

    arduino_code += '// Initial Values\n'
    for pin_name,attrib in pins.items():
        arduino_code += f'const unsigned char init{pin_name} = {pins[pin_name]["values"][0]};\n'

    arduino_code += '\n// Accumulated Values\n'
    arduino_code += 'unsigned char ' + ','.join([f'accum{pin}' for pin in pins]) + ';\n'

    arduino_code += '\n// Position Info\n'
    arduino_code += 'CompressionInfo ' + ','.join([f'info{pin}' for pin in pins]) + ';\n'

    arduino_code += '\n// Compressed Deltas\n'

    for pin_name,attrib in pins.items():
        deltas = get_deltas(pins[pin_name]["values"])
        compressed_values = compress_zeros(deltas)
        arduino_code += f'const signed char val{pin_name}[{len(compressed_values)}] = {{{",".join([str(v) for v in compressed_values])}}};\n\n'

    if servo_count > 0:
        arduino_code += 'Servo ' + ','.join([f'servo{pin}' for pin in pins if pins[pin]["type"] == "servo"]) + ';\n\n'

    arduino_code += 'unsigned int frame = 0;\n'
    arduino_code += f'unsigned int frame_count = {frame_count};\n'
    arduino_code += 'unsigned long last_frame;\n'
    arduino_code += f'unsigned long target_delta = {int(1000/fps)};\n\n'

    arduino_code += 'void setup() {\n'

    for pin in pins:
        if pins[pin]["type"] == "servo":
             arduino_code += f"    servo{pin}.attach({pins[pin]['pin']});\n"

    for pin in pins:
        if pins[pin]["type"].startswith("analog"):
             arduino_code += f"    pinMode(A{pins[pin]['pin']}, OUTPUT);\n"

    for pin in pins:
        if pins[pin]["type"].startswith("digital"):
             arduino_code += f"    pinMode({pins[pin]['pin']}, OUTPUT);\n"

    for pin_name,attrib in pins.items():
        arduino_code += f'    accum{pin_name} = init{pin_name};\n'

    for pin_name,attrib in pins.items():
        arduino_code += f'    info{pin_name}.ypos = info{pin_name}.xpos = 0;\n'

    arduino_code += '\n    last_frame = millis();'

    arduino_code += '\n}\n\n'

    arduino_code += f'''void loop() {{

    if( (millis()-last_frame) > target_delta)
    {{
        last_frame = millis();

'''

    for pin_name,attrib in pins.items():
        arduino_code += f'        accum{pin_name} += next_value(val{pin_name},&info{pin_name});\n'

    for pin in pins:
        arduino_code += ' ' * 8
        if pins[pin]["type"] == "servo":
            arduino_code += f"servo{pin}.write(accum{pin});\n"
        elif 'pwm' in pins[pin]["type"]:
            arduino_code += f"analogWrite({pins[pin]['pin']}, accum{pin});\n"
        else:
            arduino_code += f"digitalWrite({pins[pin]['pin']}, accum{pin});\n"

    arduino_code += '\n        frame++;\n'

    arduino_code += '        if( frame >= frame_count )\n        {\n            frame = 0;\n'
    for pin_name,attrib in pins.items():
        arduino_code += f'            accum{pin_name} = init{pin_name};\n'
    for pin_name,attrib in pins.items():
        arduino_code += f'            info{pin_name}.ypos = info{pin_name}.xpos = 0;\n'
    
    arduino_code += '        }\n    }\n}\n'

    with open(sketch_name,'w') as f:
        f.write(arduino_code)

    print("Arduino sketch generated successfully.")

class FileSelectorGUI:
    def __init__(self, master):

        self.app_name = "CSVToSketch"
        self.app_author = "Lokno"

        config_data = self.load_config()

        if not config_data:
            config_data['csv_file'] = ''
            config_data['fps'] = 30
            config_data['sketch_dir'] = '.'
            config_data['sketch_file'] = 'GeneratedSketch.ino'

        self.master = master
        master.title("CSV To Sketch")

        self.csv_file_label = tk.Label(master, text="Select CSV file:")
        self.csv_file_label.grid(row=0, column=0, sticky="w")

        self.csv_directory_text = tk.Text(master, height=1, width=40)
        self.csv_directory_text.grid(row=1, column=0, sticky="w")
        self.csv_directory_text.insert("1.0",config_data['csv_file'])

        self.csv_file_button = tk.Button(master, text="Browse", command=lambda:self.browse_file(self.csv_directory_text))
        self.csv_file_button.grid(row=1, column=1, sticky="w")

        self.output_directory_label = tk.Label(master, text="Select output directory:")
        self.output_directory_label.grid(row=4, column=0, sticky="w")

        self.output_directory_text = tk.Text(master, height=1, width=40)
        self.output_directory_text.grid(row=5, column=0, sticky="w")
        self.output_directory_text.insert("1.0",config_data['sketch_dir'])

        self.output_directory_button = tk.Button(master, text="Browse", command=lambda:self.browse_directory(self.output_directory_text))
        self.output_directory_button.grid(row=5, column=1, sticky="w")

        self.output_frame = tk.Frame(master)
        self.output_frame.grid(row=6, column=0, columnspan=2, padx=5, pady=5, sticky="w")

        self.output_file_label = tk.Label(self.output_frame, text="Enter sketch file name:")
        self.output_file_label.pack(side="left")

        self.output_file_entry = tk.Entry(self.output_frame)
        self.output_file_entry.insert("end", config_data['sketch_file'])
        self.output_file_entry.pack(side="left", padx=5)

        self.fps_label = tk.Label(self.output_frame, text="FPS:")
        self.fps_label.pack(side="left")

        self.fps_entry = tk.Entry(self.output_frame)
        self.fps_entry.insert("end",config_data['fps'])  
        self.fps_entry.pack(side="left", padx=5)

        self.button_frame = tk.Frame(master, width=200, height=50)
        self.button_frame.grid(row=7, column=0, columnspan=2)

        self.generate_button = tk.Button(self.button_frame, text="Write Sketch", command=self.generate_output)
        self.generate_button.grid(row=0, column=0, padx=5, pady=5)

        self.message_text = tk.Label(master, height=1, width=40)
        self.message_text.grid(row=8, column=0, columnspan=2, pady=5)

        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
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

    def generate_output(self):
        csv_file = self.csv_directory_text.get("1.0", "end-1c")
        output_directory = self.output_directory_text.get("1.0", "end-1c")
        output_filename = self.output_file_entry.get()
        fps = self.fps_entry.get()

        success,msg = validate_csv(csv_file,'CSV File')
        if success:
            success,msg = validate_dir(output_directory,'Output Directory')
            if success:
                if not fps.isnumeric():
                    msg = 'fps value is not a number'
                    success = False
                if success:
                    output_filename = create_path(output_directory,output_filename)
                    generate_arduino_sketch(csv_file, output_filename, int(fps))
        
                    msg = f'Wrote {output_filename}'
        
                    self.store_config({
                        'csv_file': csv_file,
                        'fps': fps,
                        'sketch_dir': output_directory, 
                        'sketch_file': self.output_file_entry.get(),
                        })

        self.update_message_text(msg, False if success else True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate an Arduino Sketch from a CSV of GPIO output values")

    # Positional arguments
    parser.add_argument("csv_file", nargs="?", help="Input CSV file")
    parser.add_argument("sketch_name", nargs="?", help="Desired output filename for sketch (will append .ino)")
    parser.add_argument("fps", type=int, nargs="?", help="Desired frames per second (integer)")

    args = parser.parse_args()

    fps = 30
    if args.fps is not None:
        fps = args.fps

    if args.csv_file is not None and args.sketch_name is not None:
        output_filename = create_path('.',args.sketch_name)
        generate_arduino_sketch(args.csv_file, output_filename, int(fps))
    else:
        import tkinter as tk
        from tkinter import filedialog
        import appdirs
        import json

        root = tk.Tk()
        app = FileSelectorGUI(root)
        root.mainloop() 
