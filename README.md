# ArduinoControlUtilities
Utilities designed to enable controlling GPIO output from a microcontroller without writing code.

## Utilities

* gensketch.py - Translates a CSV table into an arduino sketch that performs the represented effects
* pyfirmata_servo.py - Live Control of a Servo via a GUI using pyFirmata
* servo_sketch_generator.py - Translates a CSV table into an arduino sketch that performs a series of servo sweeps

## pyfirmata_servo.py

Live Control of a Servo via a GUI using pyFirmata. Records a history of servo sweeps which can be played back or export to CSV.

![Screenshot 2023-09-06 001433](https://github.com/Lokno/ArduinoControlUtilities/assets/2483797/30635c8d-d640-4ba1-bc51-21d0bdec810a)

![Screenshot 2023-09-06 001701](https://github.com/Lokno/ArduinoControlUtilities/assets/2483797/bc3c6aae-fbbf-4d47-8f5d-4a8684960134)

### Dependencies
* Python 3
* pyFirmata (https://github.com/tino/pyFirmata)
* tkDial

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
  * Export CSV - exports the sweeps in the order they appear in the "Sweep History" window to a CSV file called "servo_history.csv"
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

  
