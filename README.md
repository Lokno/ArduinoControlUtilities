# ArduinoControlUtilities
Utilities designed to enable controlling GPIO output from a microcontroller without writing code.

## Utilities

* csv_to_sketch.py - Translates a CSV table representing a sequence of GPIO output values to an Arduino Sketch
* websocket_pyfirmata.py - Websocket server for controlling a microcontroller over serial using PyFirmata
* pyfirmata_servo.py - Live Control of a Servo via a GUI using pyFirmata
* servo_sketch_generator.py - Translates a CSV table into an Arduino sketch that performs a series of servo sweeps

## csv_to_sketch.py

Translates a CSV table representing a sequence of GPIO output values to an Arduino Sketch

![Screenshot 2023-11-25 230808](https://github.com/Lokno/ArduinoControlUtilities/assets/2483797/895eb9e5-99fb-440d-8a9c-eabde1e146c5)

Uses zero compression to save memory

### Dependencies
* Python 3
* python-benedict
* appdirs

### CSV File Schema (in no particular order):

frame,pin_A,value_A,type_A,pin_B,value_B,type_B,...

* frame (integer) - 1-indexed frame number
  - file must have a complete set of frames 1 through n
  - n will be determined automatically from the largest frame number in the file
* pin_ (integer)   - output pin number on microcontroller
* value_ (integer) - output value to go out on pin on this frame
* type_ (string)   - type of pin, assumed to be a constant
  - Valid Types
    * servo       - A connected servo on the pin. Uses Arduino Servo library (valid values 0-180)
    * digital     - digital pin (D2,D3,..) for digital output (valid values 0-1)
    * analog      - analog pin  (A0,A1,...) for digital output (valid values 0-1)
    * digital_pwm - digital pin (D2,D3,..) for pwm output (valid values 0-1)
    * analog_pwm  - analog pin  (A0,A1,...) for pwm output (valid values 0-1)
   
## websocket_pyfirmata.py

![Screenshot 2023-11-25 230803](https://github.com/Lokno/ArduinoControlUtilities/assets/2483797/2bd1ce8a-f942-4cf3-91a0-d82e118efe5b)

Creates a websocket server for interactively controlling a microcontroller over serial using PyFirmata.
Intended for use with Pixel Composer using the WebSocket Sender node: https://makham.itch.io/pixel-composer

### Dependencies
* Python 3
* appdirs
* argparse
* pyfirmata
* tkinter (for GUI when opened without arguments)

Expects to receive the following data values:

* port (string)   - string of serial port where microcontroller is connected
* frame (integer) - 1-indexed frame number
  - file must have a complete set of frames 1 through n
  - n will be determined automatically from the largest frame number in the file
* pin_ (integer)   - output pin number on microcontroller
* value_ (integer) - output value to go out on pin on this frame
* type_ (string)   - type of pin, assumed to be a constant
  - Valid Types
    * servo       - A connected servo on the pin. Uses Arduino Servo library (valid values 0-180)
    * digital     - digital pin (D2,D3,..) for digital output (valid values 0-1)
    * analog      - analog pin  (A0,A1,...) for digital output (valid values 0-1)
    * digital_pwm - digital pin (D2,D3,..) for pwm output (valid values 0-1)
    * analog_pwm  - analog pin  (A0,A1,...) for pwm output (valid values 0-1)

## pyfirmata_servo.py

Live Control of a Servo via a GUI using pyFirmata. Records a history of servo sweeps which can be played back or exported to CSV.

![Screenshot 2023-09-06 001433](https://github.com/Lokno/ArduinoControlUtilities/assets/2483797/30635c8d-d640-4ba1-bc51-21d0bdec810a)

![Screenshot 2023-09-06 001701](https://github.com/Lokno/ArduinoControlUtilities/assets/2483797/bc3c6aae-fbbf-4d47-8f5d-4a8684960134)

### Dependencies
* Python 3
* pyFirmata (https://github.com/tino/pyFirmata)
* tkDial (https://github.com/Akascape/TkDial)

### Setup
* Install Python 3
* Install python package dependencies, pyFirmata and tkDial (see: install_python_dependencies.bat)
* Connect your microcontroller to your PC and install StandardFirmata or ServoFirmata via the Arduino IDE
* Take note of the serial port name for your microcontroller
* Double-Click pyfirmata_servo.py, or run it from a commandline terminal.

### How to use
* Enter the serial port of your microcontroller connected to your PC
* Set the parameters to define the servo to use and how it should move
* Click Sweep to connect to the board via serial and perform the sweep
* Once connected, directly controlling the dial with mouse controls will move the physical servo in real-time.
* Mouse controls for using the dial on the right
  * Use the scroll wheel to move the needle
  * Left-Click to select the "Start" position
  * Right-Click to select the "End" position
  * Middle-Click to perform the sweep
* Buttons in the main window:
  * Sweep - perform the sweep using the current parameters
  * Reverse - swap "Start" and "End"
  * Perform Selected - perform the sweep selected in the "Sweep History" window (second screenshot)
  * Perform History - perform all the sweeps in the order they appear in the "Sweep History" window (second screenshot)
  * Export CSV - exports the sweeps in the order they appear in the "Sweep History" window to a CSV file called `servo_history.csv`. This CSV can be used as input to servo_sketch_generator.py
* Buttons in the "Sweep History" window:
  * Remove Action - deletes the selected line representing a previously performed servo sweep
  * Move Up - moves the selected line upwards. This will change the order the sweeps are performed by "Perform History"
  * Move Down - moves the selected line downwards. This will change the order the sweeps are performed by "Perform History"
* Parameters
  * Port - Serial port name of connected microcontroller running listening via Firmata
  * Pin - Pin on your microcontroller that is controlling the servo
  * Max angle - The largest degree position your servo can be set to
  * Start - The starting position of the sweep
  * End - The end position of the sweep
  * Duration - The duration of the sweep (milliseconds)
  * Ease In - Period at the start of the sweep to accelerate (cubic)
  * Ease Out - Period at the end of the sweep to deccelerate (cubic)
  * Update Interval - Interval to update the positon of the servo

## servo_sketch_generator.py

![Capture](https://github.com/Lokno/ArduinoControlUtilities/assets/2483797/c8056bd1-596a-4660-95bd-f07fbed3584b)

Translates a CSV table representing a sequence of servo sweeps to an Arduino sketch.
The generated Arduino sketch uses Renaud Bédard's coroutine library to handle concurrent operation of multiple servos (https://github.com/renaudbedard/littlebits-arduino/tree/master/Libraries/Coroutines).
CSV exported from `pyfirmata_servo.py` can be used directly as input.

### Dependencies
* Python 3
* python-benedict
* appdirs
* pyFirmata (For "Perform Scenes" feature)

### Interface
* Select Routine CSV file - path to a CSV file with the sequence of servo sweeps
* Select ServoInfo CSV file (optional) - path to a CSV file with specifications for each servo
* Select output directory - path to an existing directory to place the sketch.
* Use motion Sensor (checkbox) - whether to check on a input pin for motion before executing the routine
* Pin - input pin to listen for motion. Debouncing not addressed, HIGH = motion
* Enter output file name - What to call the output sketch (not a path)
* Write Sketch (button) - Generate the Arduino sketch
* Perform Scenes - Connect to serial port and perform the sequence of sweeps using pyFirmata
* Port - serial port of a connected microcontroller running StandardFirmata or ServoFirmata

### Routine CSV File Format (column order is not important)
| Scene |	Name  |	Pin   |	Position |	Time  |	Ease In |	Ease Out |
| ----- | ----- | ----- | -------- | ----- | ------- | -------- |
| Integer | String | Integer | Integer | Integer | Integer | Integer |

* Scene - Integer id of scene during which the sweep should be performed (Scene 0 sets the reset sweep and starting position)
* Name - The string name of the sweep (used in the script for readability
* Pin - The output pin on the microcontroller for the servo. Only one sweep should be run on each pin during the same scene
* Position - End position of the sweep. The starting position is implied by the position of that servo the end of the the previous scene
* Time - Duration of the sweep. The length of a scene will be the largest duration of all the sweeps in that scene
* Ease In - Time to accelerate (cubic easing)
* Ease Out - Time to decelerate (cubic easing)

### ServoInfo CSV File Format (column order is not important)
| Pin   |	Full Sweep  |	Minimum   |	Maximum  |
| ----- | ----------- | --------- | -------- |
| Integer | Integer | Integer | Integer |

* Pin - The output pin on the microcontroller for the servo.
* Full Sweep - The extreme position in degrees the servo is capable of reaching (default: 270)
* Minimum - The pulse with in microseconds to set the servo to the 0 position (default: 544)
* Maximum - The pulse width in microseconds to set the servo to the extreme position (default: 2400)
