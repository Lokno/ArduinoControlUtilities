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

    arduino_code = '#include <Servo.h>\n'

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

    arduino_code += 'Servo ' + ','.join([f'servo{pin}' for pin in pins if pins[pin]["type"] == "servo"]) + ';\n\n'

    arduino_code += 'unsigned int frame = 0;\n'
    arduino_code += f'unsigned int frame_count = {frame_count};\n'
    arduino_code += 'unsigned long last_frame;\n'
    arduino_code += f'unsigned long target_delta = {int(1000/fps)};\n\n'

    #unsigned int idxA;
    #unsigned int idxAzero;

    arduino_code += 'void setup() {\n'

    for pin in pins:
        if pins[pin]["type"] == "servo":
             arduino_code += f"    servo{pin}.attach({pins[pin]['pin']});\n"

    for pin in pins:
        if pins[pin]["type"].startswith("analog"):
             arduino_code += f"  pinMode(A{pin}, OUTPUT);\n"

    for pin in pins:
        if pins[pin]["type"].startswith("digital"):
             arduino_code += f"  pinMode({pin}, OUTPUT);\n"

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
            arduino_code += f"analogWrite({pin}, accum{pin});\n"
        else:
            arduino_code += f"digitalWrite({pin}, accum{pin});\n"

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate an Arduino Sketch from a CSV of GPIO output values")

    # Positional arguments
    parser.add_argument("csv_file", help="Input CSV file")
    parser.add_argument("sketch_name", help="Desired output filename for sketch (will append .ino)")
    parser.add_argument("fps", type=int, help="Desired frames per second (integer)")

    args = parser.parse_args()

    generate_arduino_sketch(args.csv_file, args.sketch_name, args.fps)
