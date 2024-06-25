import os
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk, messagebox, filedialog
import configparser
import xml.etree.ElementTree as ET

class DirectoryDropdownApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Convert LightShow to Arduino Sketch")

        self.frame = ttk.Frame(root)
        self.frame.pack(padx=10, pady=10, anchor='w')

        self.dropdown_label = ttk.Label(self.frame, text="LightShow:")
        self.dropdown_label.grid(row=0, column=0, padx=5, pady=5, sticky='w')

        self.selected_directory = tk.StringVar()
        self.dropdown = ttk.Combobox(self.frame, textvariable=self.selected_directory)
        self.dropdown.grid(row=0, column=1, padx=5, pady=5, sticky='w')
        self.dropdown.bind("<<ComboboxSelected>>", self.on_directory_selected)

        self.scenes_frame = ttk.Frame(root)
        self.scenes_frame.pack(padx=10, pady=10, anchor='w')

        canvas = tk.Canvas(root, width=500, height=6)
        canvas.pack()

        canvas.create_line(0, 2, 500, 2, fill="black", width=2)

        self.dir_frame = tk.Frame(root)
        self.dir_frame.pack(pady=10, padx=10, anchor='w')

        self.dir_label = tk.Label(self.dir_frame, text="Sketch Output Directory:")
        self.dir_label.grid(row=0, column=0, padx=5, pady=5, sticky='w')

        self.dir_text = tk.Label(self.dir_frame, text="Choose an output directory")
        self.dir_text.grid(row=0, column=1, padx=5, pady=5, sticky='w')
        
        browse_button = tk.Button(self.dir_frame, text="Browse", command=self.browse_directory)
        browse_button.grid(row=0, column=2, padx=5, pady=5, sticky='e')

        self.file_frame = tk.Frame(root)
        self.file_frame.pack(pady=10, padx=10, anchor='w')

        self.file_label = tk.Label(self.file_frame, text="Sketch Name:")
        self.file_label.grid(row=0, column=0, padx=5, pady=5, sticky='w')

        self.file_text = tk.Entry(self.file_frame, justify='right')
        self.file_text.grid(row=0, column=1, padx=5, pady=5, sticky='w')

        self.file_text.insert(0, "LightShow.ino")

        button_style = {
            "font": ("Sans-Serif", 12, "bold"),  # Set font size
            "bg": "green",              # Set background color
            "fg": "white",              # Set text color
            "activebackground": "dark green",  # Set background color when clicked
            "activeforeground": "white",       # Set text color when clicked
            "relief": tk.RAISED,        # Add a raised effect
            "bd": 3                     # Set border width
        }

        self.generate_button = tk.Button(self.file_frame, text="Generate Sketch", command=self.generate_sketch, **button_style, state='disabled')
        self.generate_button.grid(row=0, column=2, padx=100, pady=5, sticky='e')

        self.status_message = tk.Text(root, height=4, width=50, state='disabled')
        self.status_message.pack(pady=5)

        self.populate_dropdown()

    def _read_lightshow_fixtures(self, config_str):
        config = configparser.ConfigParser()
        self.fixtures = {}
        config.read_string(config_str)
        for section in config.sections():
            fid = config[section]['id']
            fname = config[section]['name']
            faddress = int(config[section]['address'])-1
            self.fixtures[fid] = {'name': fname, 'address': faddress}

    def load_lightshow_fixtures(self, fixtures_file):
        lightshow_header = b'\xef\xbb\xbf'
        if os.path.exists(fixtures_file):
            try:
                with open(fixtures_file, 'rb') as f:
                    fixtures_header = f.read(3)
                    if lightshow_header == fixtures_header:
                        fixtures_str = f.read().decode()
                        self._read_lightshow_fixtures(fixtures_str)
                    else:
                        self.update_status(f'Error: unexpected header in fixtures.ini')

            except Exception as e:
                self.update_status(f'Error: {e}')
        else:
            self.update_status(f"Error: fixtures.ini not found in project")

    def convert_wrgb_to_int(self,w,r,g,b):
        return w << 24 | r << 16 | g << 8 | b

    def generate_sketch(self):
        selected_directory = self.selected_directory.get()
        output_directory = self.dir_text.cget('text')
        output_filename = self.file_text.get().strip()

        if not os.path.isdir(output_directory):
            self.update_status(f"You must choose a valid output directory.")
            return

        if output_filename == '':
            self.update_status(f"You must choose an output filename.")
            return  

        output_directory = os.path.normpath(output_directory)

        base_file_name, file_extension = os.path.splitext(output_filename)

        last_directory = os.path.basename(output_directory)

        if file_extension != '.ino':
            output_filename = base_file_name + '.ino'

        if last_directory != base_file_name:
            output_path = os.path.join( output_directory, base_file_name, output_filename )
        else:
            output_path = os.path.join( output_directory, output_filename )

        fixtures_file = os.path.join(os.path.expanduser('~'), 'TheLightingController', 'LightShows', selected_directory, 'fixtures.ini')
        scenes_path = os.path.join(os.path.expanduser('~'), 'TheLightingController', 'LightShows', selected_directory, 'scenes')

        if not os.path.exists(fixtures_file):
            self.update_status("Fixtures file not found.")
            return

        if not os.path.exists(scenes_path):
            self.update_status(f"Path {scenes_path} does not exist.")
            return

        self.load_lightshow_fixtures(fixtures_file)

        scene_out_data = []
        start_up_scene = None
        fixture_count = 0
        max_steps = 0
        data_pin = 14
        led_count = 0
        scene_count = 0
        max_address = 0

        try:
            for si, sd in enumerate(self.scene_data):

                is_startup = self.checkbox_vars[si].get()

                if self.trigger_pins[si] == -1 and not is_startup:
                    continue

                idx = sd['idx']
                scene_path = os.path.join(scenes_path,sd['path'])
                tree = ET.parse(scene_path)
                root = tree.getroot()
    
                for fixture in root.findall('./Fixtures/Fixture'):
                    fid = fixture.get('id')

                    if fid not in self.fixtures:
                        self.update_status(f"Fixture {fid} referenced in {sd['path']} not found in 'fixtures.ini'.")

                steps = root.findall('./Steps/Step')
                step_count = len(steps)

                step_out_data = []

                prev_colors = {}

                for i, step in enumerate(steps):
                    step_length = int(step.get('length'))*10
                    #print(f'Step of length {step_length}')
                    fixtures = step.findall('./Fixture')
                    fixture_count = len(fixtures)

                    colors = {}

                    for fixture in fixtures:
                        fid = fixture.get('id')
                        faddress = self.fixtures[fid]['address']
                        channels = fixture.findall('./Channel')
                        channel_count = len(channels)

                        for channel in fixture.findall('./Channel'):
                            cidx = int(channel.get('index'))
                            cval = int(channel.get('value'))
                            cfade = channel.get('fade')

                            col_idx = (faddress // 3) + cidx // 3

                            max_address = max(max_address,col_idx)

                            if col_idx not in colors:
                                colors[col_idx] = [0,0,0]

                            colors[col_idx][cidx%3] = cval

                    # fill any that are missing
                    for i in range(max_address+1):
                        if i not in colors:
                            if i not in prev_colors:
                                colors[i] = [0,0,0]
                            else:
                                colors[i] = prev_colors[i]

                    prev_colors = colors

                    icolors = [0] * (max_address+1)

                    for k,v in colors.items():
                        icolors[k] = str(self.convert_wrgb_to_int(0,*v)) + 'u'

                    step_out_data.append({'length' : step_length, 'colors': icolors})

                max_steps = max(max_steps,len(step_out_data))

                # add to output scenes
                scene_out_data.append({'steps': step_out_data, 'count': len(step_out_data), 'pin' : self.trigger_pins[si], 'fade_in' : self.fade_values[si][0], 'fade_out' : self.fade_values[si][1]})

                if is_startup:
                    start_up_scene = len(scene_out_data)-1

        except Exception as e:
            self.update_status(f"Error: {e}")

        # Generate Sketch
        led_count = max_address+1
        scene_count = len(scene_out_data)
        scene_str = ''

        if start_up_scene is None:
            # add an empty scene
            scene_count += 1
            scene_str = '''
    {
    },'''
        else:
            # swap start up to the start
            tmp = scene_out_data[start_up_scene]
            scene_out_data[start_up_scene] = scene_out_data[0]
            scene_out_data[0] = tmp

        defines_str = f'''
#define LED_COUNT {led_count}
#define SCENE_COUNT {scene_count}
#define MAX_STEPS {max_steps}
#define DATA_PIN {data_pin}
        '''

        for scene in scene_out_data:

            step_str = ''
            for step in scene['steps']:
                step_str += f'''
             {{
                 .color = {{{','.join(step['colors'])}}},
                 .length = {step['length']}u
             }},  
'''

            pin = 0
            if scene['pin'] > 0:
                pin = scene['pin']

            scene_str += f'''
    {{
        .steps = {{
{step_str}
        }},
        .count = {scene['count']}u,
        .pin = {pin}u,
        .fade_in = {scene['fade_in']}u,
        .fade_out = {scene['fade_out']}u,
        .button = NULL
    }},'''

        file_str = f'''
#include <Adafruit_NeoPixel.h>
#include <LoknoButton.h>
{defines_str}
union Color {{
    uint32_t value;
    struct {{
        uint8_t b;
        uint8_t g;
        uint8_t r;
        uint8_t w;
    }};
}};

typedef struct {{
    Color color[LED_COUNT];
    uint32_t length;
}} State;

typedef struct {{
    State steps[MAX_STEPS];
    uint32_t count;
    uint32_t pin;
    uint32_t fade_in;
    uint32_t fade_out;
    LoknoButton* button;
}} Scene;

Adafruit_NeoPixel strip( LED_COUNT, DATA_PIN, NEO_GRB);

Scene scenes[SCENE_COUNT] = {{
{scene_str}
}};

uint16_t current_scene;
uint16_t current_step;
uint16_t start_up_scene;
uint32_t start;
bool fade;
uint32_t fade_duration;
State start_state;

uint8_t lerp(uint8_t a, uint8_t b, uint32_t elapsed, uint32_t period) {{
    uint32_t result = b;
    if (period > 0 && elapsed < period)
    {{
        if (a <= b) result = a + (elapsed * (b - a)) / period;
        else result = a - (elapsed * (a - b)) / period;
    }}
    return (uint8_t)result;
}}

void init_state() {{
    start_up_scene = {0 if start_up_scene is None else start_up_scene}u;
    current_scene = start_up_scene;
    current_step = 0u;
    fade = true;
    fade_duration = scenes[current_scene].fade_in;
    start = millis();
    strip.begin();

    for(uint16_t i = 0u; i < SCENE_COUNT; ++i)
    {{
        if( scenes[i].pin != 0u ) scenes[i].button = new LoknoButton(scenes[i].pin, 50, true, true);
    }}
}}

void update() {{
    uint32_t elapsed = millis()-start;

    uint32_t step_length = fade ? fade_duration : scenes[current_scene].steps[current_step].length;

    for(uint16_t i = 0u; i < LED_COUNT; ++i)
    {{
         Color s = start_state.color[i];
         Color t = scenes[current_scene].steps[current_step].color[i];

         Color v;

         v.w = 0;//lerp(s.w,t.w,elapsed,step_length);
         v.r = lerp(s.r,t.r,elapsed,step_length);
         v.g = lerp(s.g,t.g,elapsed,step_length);
         v.b = lerp(s.b,t.b,elapsed,step_length);

         strip.setPixelColor(i, v.value);
    }}

    if( elapsed > step_length ) 
    {{
        current_step = (current_step+1u) % scenes[current_scene].count;
        fade = false;
        store_state();
        start = millis();
    }}

    strip.show();
}}

void store_state() {{
    for(uint16_t i = 0u; i < LED_COUNT; ++i)
    {{
        start_state.color[i].value = strip.getPixelColor(i);
    }}
}}

void check_scene_switch()
{{
    for(uint16_t i = 0u; i < SCENE_COUNT; ++i)
    {{
        if( current_scene != i && scenes[i].button != NULL && scenes[i].button->wasPressed() )
        {{
            store_state();
            current_scene = i;
            current_step = 0u;
            fade = true;
            fade_duration = i == start_up_scene ? scenes[current_scene].fade_out : scenes[i].fade_in;
            start = millis();
        }}
    }}
}}

void setup() {{
    init_state();
}}

void loop() {{
    update();
    check_scene_switch();
    delay(10);
}}
'''
        if last_directory != base_file_name:
            os.makedirs(os.path.join( output_directory, base_file_name), exist_ok=True)

        with open(output_path,'w') as fout:
            fout.write(file_str)

        self.update_status(f"Wrote {output_path}")

    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.dir_text.config(text=directory)

    def populate_dropdown(self):
        err = False

        base_path = os.path.join(os.path.expanduser('~'), 'TheLightingController', 'LightShows')
        if not os.path.exists(base_path):
            self.update_status(f"Path {base_path} does not exist.")
            self.dropdown.config(state='disabled')
            return
        try:
            directories = [d for d in os.listdir(base_path) 
                           if os.path.isdir(os.path.join(base_path, d))]

            directories.insert(0, '')
            if not directories:
                self.update_status("No projects found.")
                self.dropdown.config(state='disabled')
            else:
                self.dropdown['values'] = directories
                self.dropdown.config(state='normal')
                self.dropdown.current(0)
        except Exception as e:
            self.update_status(f"Error: {e}")
            self.dropdown.config(state='disabled')

    def on_checkbutton_change(self, idx):
        if self.checkbox_vars[idx].get():
            self.pin_entries[idx].config(state='disabled')
            self.pin_labels[idx].config(state='disabled')
            self.trigger_pins[idx] = -1
            self.trigger_vars[idx].set('')
            for i,c in enumerate(self.checkbox_vars):
                if i != idx and c.get():
                    c.set(False)
                    self.pin_entries[i].config(state='normal')
                    self.pin_labels[i].config(state='normal')
        else:
            self.pin_entries[idx].config(state='normal')
            self.pin_labels[idx].config(state='normal')

    def parse_int(self, s, max_length, min_value, max_value, default):
        if s.isdigit() and len(s) <= max_length:
            return max(min(int(s),max_value),min_value)
        else:
            return default

    def parse_flt(self, s, max_length, min_value, max_value, default):
        if s.replace('.', '', 1).isdigit() and len(s) <= max_length:
            return max(min(float(s),max_value),min_value),True
        else:
            return default,False

    def on_pin_entry_change(self, idx):
        try:
            value = self.parse_int(self.trigger_vars[idx].get(), 2, 0, 99, -1)
            self.trigger_pins[idx] = value
            if value > -1:
                self.trigger_vars[idx].set(str(value))
            else:
                self.trigger_vars[idx].set('')
            print(f"Pin Entry value changed to: {self.trigger_pins[idx]}")
        except ValueError:
            print("Invalid entry, not an integer")

    def on_fade_in_entry_change(self, idx):
        try:
            value,valid = self.parse_flt(self.fade_vars[idx][0].get(), 11, 0.0, 4294967.295, 0.0)
            self.fade_values[idx][0] = int(value * 1000.0)
            if not valid: 
                self.fade_vars[idx][0].set('')
            print(f"Fade In Entry value changed to: {self.fade_values[idx][0]}")
        except ValueError:
            print("Invalid entry, not an integer")

    def on_fade_out_entry_change(self, idx):
        try:
            value,valid = self.parse_flt(self.fade_vars[idx][1].get(), 11, 0.0, 4294967.295, 0.0)
            self.fade_values[idx][1] = int(value * 1000.0)

            if not valid:
                self.fade_vars[idx][1].set('')
            print(f"Fade Out Entry value changed to: {self.fade_values[idx][1]}")
        except ValueError:
            print("Invalid entry, not an integer")

    def on_directory_selected(self, event):
        selected_directory = self.selected_directory.get()

        self.clear_scenes()
        self.update_status('')

        self.generate_button.config(state='disabled')

        if selected_directory == '':
            return

        scenes_path = os.path.join(os.path.expanduser('~'), 'TheLightingController', 'LightShows', selected_directory, 'scenes')
        if not os.path.exists(scenes_path):
            self.update_status(f"Path {scenes_path} does not exist.")
            return
        try:
            scene_files = [f for f in os.listdir(scenes_path) if f.endswith('.scex')]
            if not scene_files:
                self.update_status(f"No scene files found in {selected_directory}.")
            else:
                max_length = len(max(scene_files))-5
                self.checkbox_vars = []
                self.pin_entries = []
                self.trigger_vars = []
                self.trigger_pins = []
                self.pin_labels = []
                self.scene_data = []
                self.fade_vars = []
                self.fade_values = []
                idx = 0

                for i, scene_file in enumerate(scene_files):
                    scene_frame = ttk.Frame(self.scenes_frame)
                    scene_frame.grid(row=i, column=0, padx=5, pady=2, sticky='e')

                    file_stem = os.path.splitext(scene_file)[0]

                    scene_label = ttk.Label(scene_frame, text=file_stem)
                    scene_label.grid(row=0, column=0, padx=5, pady=2, sticky='w')

                    cb_var = tk.BooleanVar()
                    pin_var = tk.StringVar()
                    fade_in_var = tk.StringVar()
                    fade_out_var = tk.StringVar()
                    cb_var.trace_add("write", lambda *args, idx=idx: self.on_checkbutton_change(idx))
                    pin_var.trace_add("write", lambda *args, idx=idx: self.on_pin_entry_change(idx))
                    fade_in_var.trace_add("write", lambda *args, idx=idx: self.on_fade_in_entry_change(idx))
                    fade_out_var.trace_add("write", lambda *args, idx=idx: self.on_fade_out_entry_change(idx))

                    idx += 1
                    scene_checkbox = tk.Checkbutton(scene_frame, text='Startup Scene', variable=cb_var)
                    scene_checkbox.grid(row=0, column=1, padx=5, pady=2, sticky='w')

                    scene_pin_entry = tk.Entry(scene_frame, textvariable=pin_var, width=4, justify='right')
                    scene_pin_entry.grid(row=0, column=2, padx=5, pady=2, sticky='w')

                    pin_label = ttk.Label(scene_frame, text='Trigger Pin')
                    pin_label.grid(row=0, column=3, padx=5, pady=2, sticky='w')

                    fade_in_entry = tk.Entry(scene_frame, textvariable=fade_in_var, width=6, justify='right')
                    fade_in_entry.grid(row=0, column=4, padx=5, pady=2, sticky='w')

                    fade_in_label = ttk.Label(scene_frame, text='Fade In')
                    fade_in_label.grid(row=0, column=5, padx=5, pady=2, sticky='w')

                    fade_out_entry = tk.Entry(scene_frame, textvariable=fade_out_var, width=6, justify='right')
                    fade_out_entry.grid(row=0, column=6, padx=5, pady=2, sticky='w')

                    fade_out_label = ttk.Label(scene_frame, text='Fade Out')
                    fade_out_label.grid(row=0, column=7, padx=5, pady=2, sticky='w')

                    self.checkbox_vars.append(cb_var)
                    self.trigger_vars.append(pin_var)
                    self.trigger_pins.append(-1)
                    self.pin_labels.append(pin_label)
                    self.pin_entries.append(scene_pin_entry)
                    self.fade_vars.append([fade_in_var,fade_out_var])
                    self.fade_values.append([1000,1000])

                    fade_in_var.set('1.0')
                    fade_out_var.set('1.0')

                    self.scene_data.append({'path' : scene_file, 'idx' : i})

                self.update_status(f"Found {len(scene_files)} scene files in {selected_directory}.")

                self.generate_button.config(state='normal')

        except Exception as e:
            self.update_status(f"Error: {e}")

    def clear_scenes(self):
        for widget in self.scenes_frame.winfo_children():
            widget.destroy()

    def update_status(self, message):
        self.status_message.config(state='normal')
        self.status_message.delete(1.0, tk.END)
        self.status_message.insert(tk.END, message)
        self.status_message.config(state='disabled')


if __name__ == "__main__":
    root = tk.Tk()
    app = DirectoryDropdownApp(root)
    root.mainloop()
