# Author     : Lokno Decker
# Usage      : python3 gensketch.py <CSV INPUT>[.csv] <SKETCH OUTPUT>[.ino]
# Description : Translates a CSV table into an arduino sketch that performs the represented effects
#     Uses Renaud Bedard's Coroutine library
#         https://github.com/renaudbedard/littlebits-arduino/tree/master/Libraries/Coroutines
#     Schema of the CSV table is as follows:
#         Cue,Effect,Input,Trigger,Trigger State,Exit State,Output,Output Type,Offset (ms),Duration (ms),Signal,Frequency,Min,Max,Dormant
#     Alterative Schema which omits the state fields (for when the program does not require more than one state):
#         Cue,Effect,Input,Trigger,Output,Output Type,Offset (ms),Duration (ms),Signal,Frequency,Min,Max,Dormant
#
# Cue    - Unique name of a cue, which groups multiple effects
# Effect - Description of the effect
# Input  - Input pin or variable which controls the cue. Effect loops as long as the input is high.
#          If no input is given (left blank or defined as NONE) then the effect is always on.
# Trigger - The even when the cue triggers 
#     Types of triggers supported:
#         on_open - the input switch is open (LOW signal)
#         on_closed - the input switch is closed (HIGH signal)
#         on_open_to_closed - the input switch changes from open to closed
#         on_closed_to_open - the input switch changes from closed to open
# Trigger State - The state within which this cue may be triggered. Program starts in state A.
#                 The default value is 'A' when this field is left blank or says 'NONE'
# Exit State - The state to change to when all of the effects within a cue have terminated. 
#              Note: For all effects to terminate, the cue must have an input. Program starts in state A.
# Output   - Output pin or variable on which the effect is written
# Output Type - Type of output
#     Types of output supported:
#         DIGITAL - Possible values LOW,HIGH
#         PWM - Possible values in range 0-255
#         SERVO - mircoseconds representing angle of a servo (default range between 544 (0 degrees) and 2400 (180 degrees))
#         VARIABLE - Required if the output is a variable name. Output will converted to digital.
# Offset (ms) - Delay in milliseconds before the effect starts its first iteration
# Duration (ms) - Time in milliseconds effect will last, if the input pin is pressed once
# Signal - Type of signal to send to output when the effect is active.
#     Types of signals supported:
#         BOUNCEIN      - increases from Min to Max, but bounces up and down along the way
#         BOUNCEINOUT   - increases from Min to Max and then back to Min, but bounces up and down along the way
#         BOUNCEOUT     - inverse of BOUNCEIN
#         BOX           - alternates between the given Min and Max values at the given frequency
#         EASEIN        - linearly increases from Min to Max
#         EASEINCIRC    - increases from Min to Max in a circular arch  
#         EASEINEXPO    - increases from Min to Max exponentialy 
#         EASEINOUT     - linearly increases from Min to Max and than back to Min
#         EASEINOUTCIRC - increases from Min to Max in a circular arch, and then back to Min
#         EASEINOUTEXPO - exponentialy increases from Min to Max and than back to Min
#         EASEINOUTSINE - increases from Max to Min in a circular arch 
#         EASEINSINE    - increases from Min to Max along a sine wave
#         EASEOUT       - linearly decreases from Max to Min (inverse of EASEIN)
#         EASEOUTCIRC   - inverse of EASEINCIRC
#         EASEOUTEXPO   - decreases from Max to Min exponentialy (inverse of EASEINEXPO)
#         EASEOUTSINE   - decreases from Max to Min along a sine wave
#         HIGH          - remains at the Max value as long as the effect is active
#         LOW           - remains at the Min value as long as the effect is active
#         LANTERN       - simulates a flickering lantern flame within the given range at the given frequency
#         NOISE         - changes to random values within the given range at the given frequency
#         PULSE         - alias for EASEINOUTSINE
#         RANDOM        - Alias for NOISE
#         SQUARE        - Alias for BOX
#         TRIANGLE      - Alias for EASEINOUT
# Frequency - The number of times the signal repeats per second
# Min - The minimum value of the output
# Max - The maximum value of the output
# Dormant - The value of the output when the effect is inactive (initialization, offset period, when duration ends and input is low)
#           This value can be left blank or defined as NONE. In this case the output pin will be initialized to zero/LOW, but will
#           not be set when a signal terminates after its duration ends.
# Param1 - For the RANDOM signal this is how often the randomness occurs. 100 means it will always be random, 0 means it will always
#          be at the maximum value (Default: 100)

# TODO: Define macros for constants for better readablity

import argparse
import random
import sys
import re
from pathlib import Path

defaultServoMin = 544
defaultServoMax = 2400

class FunctionData():
    def __init__(self):
        self.signals = {}
        self.all_known_types = {}
        self.lambdas = {}

    def add( self, aliases, dependency_list, function_name, function_str, function_lambda ):
        found = any([a in self.all_known_types for a in aliases])
        if len(aliases) > 0 and not found:
            akey = aliases[0]
            for a in aliases:
                self.all_known_types[a] = akey
            self.lambdas[akey] = function_lambda
            self.signals[akey] = {'function' : function_str, 'function_name' : function_name, 'function_lambda' : function_lambda, 'dependencies' : dependency_list}

    def get_functions( self, signal_list ):
        funcs = []
        unique_signals = set()
        while len(signal_list) > 0:
            name = signal_list.pop()
            if name in self.all_known_types:
                primary_name = self.all_known_types[name]
                if primary_name not in unique_signals:
                    funcs.insert(0,self.signals[primary_name]['function'])
                    unique_signals.add(primary_name)
                    for s in self.signals[primary_name]['dependencies']:
                        signal_list.append(s)
        return funcs

    def is_known( self, name ):
        return name in self.all_known_types

    def get_primary_name( self, alias ):
        name = ''
        if alias in self.all_known_types:
            name = self.all_known_types[alias]
        return name

    def get_function_name(self,alias):
        func_name = ''
        if alias in self.all_known_types:
            func_name = self.signals[self.all_known_types[alias]]['function_name']
        return func_name

    def get_lambda(self,alias):
        func_lambda = None
        if alias in self.all_known_types:
            func_lambda = self.lambdas[self.all_known_types[alias]]['function_lambda']
        return func_lambda

    def lambdas(self):
        return self.lambdas

    def is_dependency(self,alias,candidate):
        return alias in self.all_known_types and self.get_primary_name(candidate) in self.signals[self.all_known_types[alias]]['dependencies']       

funcData = FunctionData()

funcData.add(['RANDOM','NOISE'],[],'randomSignal','''
typedef struct 
{
    bool isLevel;
    int cache;
    unsigned long cacheTime;
} randCache;

int randomSignal( randCache* rc, int minVal, int maxVal, float freq, unsigned long t, float severity  )
{
    if( (t-rc->cacheTime) >= (unsigned long)(1000.0f / freq) )
    {
        if( !rc->isLevel )
        {
            rc->cacheTime = t;
            rc->cache = random(minVal,maxVal+1);

            if( random(1000) > severity * 1000 )
            {
                rc->cacheTime = t;
                rc->cache = maxVal;
                rc->isLevel = true;
            }
        }
        else if( random(1000) < severity * 1000 )
        {
            rc->cacheTime = t;
            rc->isLevel = false;
        }
        else
        {
            rc->cache = maxVal;
        }
    }

    return rc->cache;
}''',
None )

funcData.add(['BOX','SQUARE'],[],'squareWave','''
float squareWave( float t )
{ 
    return t < 0.5f ? 0.0f : 1.0f;
}''',
lambda t,d: 0.0 if t < 0.5 else 1.0 )

funcData.add(['TRIANGLE','EASEINOUT'],['SCALE'],'triangleWave','''
float triangleWave( float t )
{
    return t < 0.5f ? t*2.0f : 1.0f-(t*2.0f-1.0f);
}''',
lambda t,d: t*2.0 if t < 0.5 else 1.0-(t*2.0-1.0) )

funcData.add(['EASEIN'],[],'easeIn','''
float easeIn( float t )
{
    return t;
}''',
lambda t,d: t )

funcData.add(['EASEOUT'],[],'easeOut','''
float easeOut( float t )
{
    return 1.0f-t;
}''',
lambda t,d: 1.0-t )

funcData.add(['EASEINSINE'],[],'easeInSine','''
float easeInSine( float t )
{ 
    return 1.0f - cosf(t * M_PI_2);
}''',
lambda t,d: 1.0 - math.cos(t*math.pi*0.5) )

funcData.add(['EASEOUTSINE'],[],'easeOutSine','''
float easeOutSine( float t )
{ 
    return sinf(t * M_PI_2);
}''',
lambda t,d: math.sin(t*math.pi*0.5) )

funcData.add(['EASEINOUTSINE','PULSE'],[],'easeInOutSine','''
float easeInOutSine( float t )
{ 
    return -(cosf(M_PI * x) - 1.0f) * 0.5f;
}''',
lambda t,d: -(math.cos(math.pi * x) - 1.0) * 0.5 )

funcData.add(['EASEINEXPO'],[],'easeInExpo','''
float easeInExpo( float t )
{ 
    return t == 0 ? 0.0f : powf(2.0f,10.0f * t - 10.0f);
}''',
lambda t,d: 0.0 if t == 0.0 else math.pow(2,10.0 * t - 10.0) )

funcData.add(['EASEOUTEXPO'],[],'easeOutExpo','''
float easeOutExpo( float t )
{ 
    return t == 1.0f ? 1.0f : 1.0f - powf(2.0f, -10.0f * t);
}''',
lambda t,d: 1.0 if t == 1.0 else math.pow(2,-10.0 * t) )

funcData.add(['EASEINOUTEXPO'],[],'easeInOutExpo','''
float easeInOutExpo( float t )
{ 
    return return t == 0.0f ? 0.0f : t == 1.0f ? 1.0f : t < 0.5f ? pow(2.0f, 20.0f * t - 10.0f) * 0.5f : (2.0f - pow(2.0f, -20.0f * t + 10.0f)) * 0.5f;

}''',
lambda t,d: 0.0 if t == 0.0 else 1.0 if t == 1.0 else math.pow(2.0, 20.0 * t - 10.0) * 0.5 if t < 0.5 else (2.0 - math.pow(2.0, -20.0 * t + 10.0)) * 0.5 )

funcData.add(['EASEINCIRC'],[],'easeInCirc','''
float easeInCirc( float t )
{ 
    return 1.0f - sqrtf( 1.0f - t * t );
}''',
lambda t,d: 1.0 - math.sqrt( 1.0 - t * t ) )

funcData.add(['EASEOUTCIRC'],[],'easeOutCirc','''
float easeOutCirc( float t )
{ 
    return sqrtf( 1.0f - ((t-1.0f) * (t-1.0f)));
}''',
lambda t,d: math.sqrt( 1.0 - ((t-1.0) * (t-1.0))) )

funcData.add(['EASEINOUTCIRC'],[],'easeInOutCirc','''
float easeInOutCirc( float t )
{ 
    return t < 0.5 ? (1 - sqrtf(1 - 4.0f*t*t)) * 0.5f : (sqrtf(1.0f - (-2.0f*t+2.0f)*(-2.0f*t+2.0f)) + 1.0f) * 0.5f;
}''',
lambda t,d: (1 - math.sqrt(1 - 4.0*t*t)) * 0.5 if t < 0.5 else (math.sqrt(1.0 - (-2.0*t+2.0)*(-2.0*t+2.0)) + 1.0) * 0.5 )

funcData.add(['BOUNCEIN'],['BOUNCEOUT'],'bounceIn','''
float bounceIn( float t )
{
    return 1.0f - bounceOut(1.0f - t);
}''',
lambda t,d : 1.0 - d['bounceOut'](1.0 - t) )

funcData.add(['BOUNCEOUT'],[],'bounceOut','''
float bounceOut( float t )
{
    const static float n1 = 7.5625f;
    const static float d1 = 2.75f;

    if (t < 1 / d1) {
        return n1 * t * t;
    } else if (t < 2 / d1) {
        return n1 * (t -= 1.5f / d1) * t + 0.75f;
    } else if (t < 2.5 / d1) {
        return n1 * (t -= 2.25f / d1) * t + 0.9375f;
    } else {
        return n1 * (t -= 2.625f / d1) * t + 0.984375f;
    }
}''',
lambda t,d: 7.5625 * t * t if t < 1.0 / (d1 := 2.75) else 7.5625 * (t := t - 1.5 / d1) * t + 0.75 if t < 2.0 / d1 else 7.5625 * (t := t - 2.25 / d1) * t + 0.9375 if t < 2.5 / d1 else 7.5625 * (t := t - 2.625 / d1) * t + 0.984375 )

funcData.add(['BOUNCEINOUT'],['BOUNCEOUT'],'bounceInOut','''
float bounceInOut( float t )
{ 
    return t < 0.5f ? (1.0f - bounceOut(1.0f - 2.0f * t)) * 0.5f : (1.0f + bounceOut(2.0f * t - 1.0f)) * 0.5f;
}''',
lambda t,d: (1.0 - d['bounceOut'](1.0 - 2.0 * t)) * 0.5 if t < 0.5 else (1.0 + d['bounceOut'](2.0 * t - 1.0)) * 0.5 )

funcData.add(['LANTERN'],[],'lanternSignal','''
float lanternSignal( float t )
{
    float e1 = 3.0f;
    float e2 = 1.5f;
    float e3 = 1.125f;
    t *= 16.7552f;
    float temp = sin(t*e1)*cos(t*e2)*sin(t*e3)*0.6818268596145769f+0.5f;
    return temp < 0.0f ? 0.0f : temp > 1.0f ? 1.0f : temp;
}''',
lambda t,d: 0.0 if (temp := math.sin(t*50.2656)*math.cos(t*25.1328)*math.sin(t*118.8496)*0.6818268596145769+0.5) < 0.0 else 1.0 if temp > 1.0 else temp )

funcData.add(['HIGH'],['SCALE'],'high','''
float high( float t )
{
    return 1.0;
}''',
lambda t,d: 1.0 )

funcData.add(['LOW'],['SCALE'],'low','''
float low( float t )
{
    return 0.0;
}''',
lambda t,d: 0.0 )

def scale(minVal,maxVal,x):
    return minVal + x*(maxVal-minVal)

def randomSignal( rc, minVal, maxVal, freq, t, severity ):
    if (t-rc['cacheTime']) >= (1000 // freq):
        if not rc['isLevel']:
            rc['cacheTime'] = t
            rc['cache'] = random.randint(minVal,maxVal+1)
            if random.randint(999) > severity * 1000:
                rc['cacheTime'] = t
                rc['cache'] = maxVal
                rc['isLevel'] = True
        elif random.randint(999) < severity * 1000:
            rc['cacheTime'] = t
            rc['isLevel'] = false
        else:
            rc['cache'] = maxVal

    return rc['cache']

def is_triggered(prev,curr,trigger):
    if trigger == 'on_closed' or trigger == 'on_high':
        return curr != 1
    elif trigger == 'on_open' or trigger == 'on_low':
        return curr == 0
    elif trigger == 'on_open_to_closed' or trigger == 'on_low_to_high':
        return curr != 0 and prev == 0
    elif trigger == 'on_closed_to_open' or trigger == 'on_high_to_low':
        return curr == 0 and prev != 0

async def run_effect(cueData,effectData,startTime,inputObj,outputObj,vars,active_effects):
    global active_state

    # wait for offset interval
    await asyncio.sleep(effectData['offset'])

    prev_val = 0

    while cueData['trigger_state'] == 'ALWAYS' or active_state == cueData['trigger_state']:
        currTime = time.time()
        if (startTime+effectData['duration']) < currTime:
            if isinstance(inputObj,str):
                input_val = 1.0 if vars[inputObj] == 'HIGH' else 0.0
            else:
                input_val = inputObj.read()
            if not is_triggered(input_val):
                break

        function_lambda = funcData.get_lambda(effectData['type'])
        period = 1000.0 / effectData['freq']
        period_int = int(period)
        val = scale(int(effectData['min']),int(effectData['max']), function_lambda(float(currTime % period_int / period ), funcData.lambdas()))

        if isinstance(outputObj,str):
            vars[inputObj] = val
        else:
            outputObj.write(val)

        prev_val = val
        await asynco.sleep(1)

    if effectData['dormant'] != 'NONE':
        if effectData['pinType'] == 'DIGITAL':
            dormant_val = 1 if effectData['dormant'] == 'HIGH' else 0
        else:
            dormant_val = int(effectData['dormant'])
        if isinstance(outputObj,str):
            vars[inputObj] = 'HIGH' if dormant_val > 0 else 'LOW'
        else:
            outputObj.write(dormant_val)

    active_effects -= 1
    if active_effects <= 0 and cueData['exit_state'] != 'NONE' and active_state == cueData['trigger_state']:
        active_state = cueData['exit_state']

class SketchGen():
    stateRE = re.compile('^[A-Z]+$')
    intRE = re.compile('^[0-9]+$')
    floatRE = re.compile('^[0-9]*\.?[0-9]+$')
    variableRE = re.compile('^[A-Z_]+$')
    blankRE = re.compile('^\s*$')
    triggers = [ 'on_closed', 'on_open', 'on_open_to_closed', 'on_closed_to_open', 'on_high', 'on_low', 'on_low_to_high', 'on_high_to_low' ]
    digitalOutputTypes = ['DIGITAL','VARIABLE']
    analogOutputTypes = ['PWM','SERVO','VARIABLE']

    def __init__(self, filePath):
        global funcData

        self.effectMap = {}
        self.numCues = 0
        self.numCoroutines = 0
        self.signalTypes = set()
        self.servoCount = 0
        self.servoPins = {}
        self.variables = {}
        self.trigger_states = set()
        self.exit_states = set()

        self.outputs = set()
        self.inputs = set()

        with filePath.open() as f:
            # discard header
            f.readline()

            errorRaised = False

            rows = 1
            
            for line in f:
                attributes = line.split(',')
                if len(attributes) == 14 or len(attributes) == 16:
                    trigger_state = 'A'
                    exit_state = 'A'
                    if len(attributes) == 16:
                        cue,effect,inputPin,trigger,trigger_state,exit_state,output,outputType,offset,duration,signal,freq,minVal,maxVal,dormantVal,param1 = attributes
                    else: # 15:
                        cue,effect,inputPin,trigger,output,outputType,offset,duration,signal,freq,minVal,maxVal,dormantVal,param1 = attributes

                    param1 = param1.rstrip()
                    if dormantVal == '':
                        dormantVal = 'NONE'
                    if output == '':
                        output = 'NONE'
                    if inputPin == '':
                        inputPin = 'NONE'

                    trigger_state = trigger_state.upper()
                    exit_state = exit_state.upper()

                    # validate data
                    pinType = self.determinePinType(minVal,maxVal,dormantVal)
                    if not self.intRE.match(inputPin) and inputPin != "NONE" and not self.blankRE.match(inputPin) and not self.variableRE.match(inputPin):
                        print( "ERROR: row %d: input pin neither a integer, variable name, NONE, or blank. Skipping..." % rows)
                        errorRaised = True
                    elif trigger not in self.triggers:
                        print( "ERROR: row %d: input not a known trigger type. Skipping..." % rows)
                        errorRaised = True
                    elif not self.stateRE.match(trigger_state):
                        print( "ERROR: row %d: trigger state label must only use A-Z characters. Skipping..." % rows)
                        errorRaised = True
                    elif exit_state != "NONE" and not self.blankRE.match(exit_state) and not self.stateRE.match(exit_state):
                        print( "ERROR: row %d: exit state must be a lable using only A-Z characters, NONE, or blank. Skipping..." % rows)
                        errorRaised = True
                    elif trigger_state == 'ALWAYS' and (exit_state != "NONE" and not self.blankRE.match(exit_state)):
                        print( "ERROR: row %d: trigger state 'ALWAYS' conflicts with exit state. Exit state must be NONE or blank. Skipping..." % rows)
                    elif not self.intRE.match(output) and not self.variableRE.match(output):
                        print( "ERROR: row %d: output is not an integer or variable name. Skipping..." % rows)
                        errorRaised = True
                    elif self.variableRE.match(output) and outputType != 'VARIABLE':
                        print(exit_state)
                        print( "ERROR: row %d: output is non-numeric, but output type is not set to VARIABLE. Skipping..." % rows)
                        errorRaised = True
                    elif not self.variableRE.match(output) and outputType == 'VARIABLE':
                        print( "ERROR: row %d: output type is set to VARIBLE, but output is not a valid variable name. Skipping..." % rows)
                        errorRaised = True
                    elif outputType not in self.digitalOutputTypes and outputType not in self.analogOutputTypes:
                        print( "ERROR: row %d: unsupported output type given. Skipping..." % rows)
                        errorRaised = True
                    elif not self.intRE.match(offset):
                        print( "ERROR: row %d: offset value is not an integer. Skipping..." % rows)
                        errorRaised = True
                    elif not self.intRE.match(duration):
                        print( "ERROR: row %d: duration value is not an integer. Skipping..." % rows)
                        errorRaised = True
                    elif not funcData.is_known(signal):
                        print( "ERROR: row %d: unsupported signal type given. Skipping..." % rows)
                        errorRaised = True
                    elif not self.floatRE.match(freq):
                        print( "ERROR: row %d: frequency is not a positive decimal. Skipping..." % rows)
                        errorRaised = True
                    elif pinType == 'UNKNOWN':
                        print( "ERROR: row %d: unknown pin values given. Skipping..." % rows)
                        errorRaised = True
                    elif dormantVal != 'NONE' and ((pinType == 'DIGITAL' and (dormantVal != 'HIGH' and dormantVal != 'LOW')) or (pinType == 'ANALOG' and not self.intRE.match(dormantVal))):
                        print( "ERROR: row %d: Dormant value does not match the type of the min and max values. Skipping..." % rows)
                        errorRaised = True
                    elif (pinType == 'ANALOG' and int(minVal) > int(maxVal)) or (pinType == 'DIGITAL' and minVal == 'HIGH' and maxVal == 'LOW'):
                        print( "ERROR: row %d: min value (%s) is larger than max value (%s). Skipping..." % (rows,minVal,maxVal) )
                        errorRaised = True
                    elif outputType != 'VARIABLE' and ((outputType in self.digitalOutputTypes and pinType != 'DIGITAL') or (outputType in self.analogOutputTypes and pinType != 'ANALOG')):
                        print( "ERROR: row %d: output type does not match type of given pin values " % rows )
                        errorRaised = True
                    else:
                        self.signalTypes.add(signal)
                        if output != 'NONE':
                            self.outputs.add(output)
                        if inputPin != 'NONE':
                            self.inputs.add(inputPin)

                        servoID = -1
                        if outputType == 'SERVO':
                            outputPinInt = int(output)
                            if outputPinInt in self.servoPins:
                                servoID = self.servoPins[outputPinInt]
                            else:
                                servoID = self.servoCount
                                self.servoCount += 1
                                self.servoPins[outputPinInt] = servoID

                        entry = {'id' : self.numCoroutines, 'pin' : output, 'outputType' : outputType, 'offset' : int(offset), 'duration' : int(duration), 
                                 'effect' : effect, 'type' : signal, 'freq' : float(freq), 
                                 'min' : minVal, 'max' : maxVal, 'dormant' : dormantVal,
                                 'pinType' : pinType, 'param1' : param1, 'servoID' : servoID }

                        if trigger_state != 'ALWAYS':
                            self.trigger_states.add(trigger_state)
                        if exit_state != "NONE" and exit_state != 'ALWAYS' and not self.blankRE.match(exit_state):
                            self.exit_states.add(exit_state)
                        else:
                            exit_state = 'NONE'

                        if self.variableRE.match(output):
                            if output not in self.variables or self.variables[output] != "NONE":
                                if output in self.variables and self.variables[output] != entry['dormant']:
                                    print( f'WARNING: row {rows:d}: Variable \'{output:s}\' already set to conflicting dormant value by another signal. Assuming NONE...' )
                                    self.variables[output] = 'NONE'
                                else:
                                    self.variables[output] = entry['dormant']

                        self.numCoroutines += 1
                        if not cue in self.effectMap:
                            self.effectMap[cue] = { 'id' : self.numCues, 'input' : inputPin, 'trigger': trigger, 'trigger_state': trigger_state, 'exit_state': exit_state, 'signals' : [] }
                            self.numCues += 1
                        elif self.effectMap[cue]['input'] != inputPin:
                            print( "warning: differing input pin on row %d" % rows )

                        self.effectMap[cue]['signals'].append(entry)
                rows += 1

            if errorRaised:
                print('ABORTING...')
                sys.exit(-1)

            for o in self.outputs:
                if self.variableRE.match(o) and o not in self.inputs:
                    print(f'warning: output "{o:s}" never used as input')

            for p in self.inputs:
                if self.variableRE.match(p) and p not in self.outputs:
                    print(f'warning: input variable "{p:s}" never set in output')

            self.states = self.trigger_states.union(self.exit_states).union(set('A'))
            self.state_count = len(self.states)

            # warn on trigger_states that cannot be reached
            for state in self.trigger_states:
                if state != 'A' and state not in self.exit_states:
                    print(f'warning: trigger state "{state:s}" is never reached')

            # Fix conflicting dormant values
            for var_name,var_dormant in self.variables.items():
                if var_dormant == "NONE":
                    for cue,cue_data in self.effectMap.items():
                        for signal in cue_data['signals']:
                            if signal['pin'] == var_name:
                                signal['dormant'] = 'NONE'

            # get unique input pins
            self.input_pins = {}
            for cueName,cueData in self.effectMap.items():
                if self.intRE.match(cueData['input']):
                    int_pin = int(cueData['input'])
                    if int_pin in self.input_pins:
                        self.input_pins[int_pin].append(cueName)
                    else:
                        self.input_pins[int_pin] = [cueName]

            self.uniqueOutputs = {}
            for cueData in self.effectMap.values():
                for signal in cueData['signals']:

                    # build unique output dictionary
                    pin = signal['pin']
                    if pin in self.uniqueOutputs:
                        # warn on conflicting input data
                        if self.uniqueOutputs[pin]['effect'] != signal['effect']:
                            print( "warning: differing effect descriptions for output pin %s" % pin )
                        elif self.uniqueOutputs[pin]['type'] != signal['pinType']:
                            print( "warning: differing pin type detected for output pin %s" % pin )
                        elif self.uniqueOutputs[pin]['dormant'] != "NONE" and self.uniqueOutputs[pin]['dormant'] != signal['dormant']:
                            print( "warning: differing dormant state given for output pin %s" % pin )
                    else:
                        self.uniqueOutputs[pin] = {'effect' : signal['effect'], 'type' : signal['pinType'], 'outputType' : signal['outputType'], 'dormant' : signal['dormant']}

    def determinePinType(self,minVal,maxVal,dormantVal):
        pinType = 'UNKNOWN'

        values = [minVal,maxVal]
        if dormantVal != "" and dormantVal != "NONE":
            values.append(dormantVal)

        # check if digital output
        isAssumptionValid = True
        for val in values:
            if val.upper() not in ['HIGH','LOW']:
                isAssumptionValid = False
                break

        if isAssumptionValid:
            pinType = 'DIGITAL'
        else:
            # check if analog output
            isAssumptionValid = True
            for val in values:
                if not (self.intRE.match(val) and 0 <= int(val)):
                    isAssumptionValid = False
                    break
            if isAssumptionValid:
                pinType = 'ANALOG'

        return pinType

    def write_coroutine(self,cueName,cueData,effectData,hasInput):
        useState = self.state_count > 1
        crStr = '''
// Cue:    %s
// Effect: %s
void coroutineN%02d(COROUTINE_CONTEXT(coroutine))
{\n''' % (cueName, effectData['effect'], effectData['id'])

        crStr += "    COROUTINE_LOCAL(int, val);\n"
        crStr += "    COROUTINE_LOCAL(unsigned long, currTime);\n\n"
        crStr += "\n    COROUTINE_LOCAL(unsigned long, endTime);\n"

        crStr += "    BEGIN_COROUTINE;\n"

        if effectData['offset'] > 0:
            crStr += '\n    endTime = startTimes[%d]+%du;' % (cueData['id'],effectData['offset'])
            crStr += "\n    if( (long)(endTime-millis()) > 0 )\n    {"
            crStr += "\n        coroutine.wait(%d);\n        COROUTINE_YIELD;\n" % effectData['offset']
            crStr += "    }\n"

        crStr += '\n'

        pinType = effectData['pinType'].lower()

        crStr += '    endTime = millis()+%du;\n' % effectData['duration']
        if useState and cueData["trigger_state"] != 'ALWAYS':
            crStr += f'    while( curr_state == STATE_{cueData["trigger_state"]:s} && (long)(endTime-millis()) > 0 )\n    {{\n'
        else:
            crStr += "    while( (long)(endTime-millis()) > 0 )\n    {\n"

        crStr += "        currTime = millis()-startTimes[%d]-%du;\n" % (cueData['id'],effectData['offset'])

        if funcData.get_primary_name(effectData['type']) == 'RANDOM':
            severity = 1.0
            if effectData['param1'] != '' and intRE.match(effectData['param1']):
                severity = float(effectData['param1']) / 100.0
            crStr += "        val = randomSignal(&rc_cr%02d_out%02d, %s, %s, %ff, currTime, %ff );\n" % (cueData['id'], effectData['id'], effectData['min'],effectData['max'],effectData['freq'],severity)
        else:
            function_name = funcData.get_function_name(effectData['type'])
            period = 1000.0 / effectData["freq"]
            period_int = int(period)
            crStr += f'        val = scale({effectData["min"]:s},{effectData["max"]:s}, {function_name:s}(  (float)(currTime % {period_int:d}u / {period:f}f )));\n'

        if effectData['outputType'] == 'SERVO':
            crStr += "        servos[%d].writeMicroseconds(val);" % (self.servoPins[int(effectData['pin'])])
        elif effectData['outputType'] == 'VARIABLE' and pinType == 'digital':
            crStr += "        %s = val;" % effectData['pin']
        elif effectData['outputType'] == 'VARIABLE':
            crStr += "        %s = val > 0 ? HIGH : LOW;" % effectData['pin']
        else:
            crStr += "        %sWrite(%d, val);" % (pinType,int(effectData['pin']))

        crStr += "\n        coroutine.wait(1);\n        COROUTINE_YIELD;\n    }\n"

        if not hasInput and not useState:
            crStr += "\n    coroutine.loop();"
        else:
            if not hasInput and useState and cueData["exit_state"] != 'NONE': # omit loop
                triggerConditional = None
            else:
                triggerConditions = []
                if useState and cueData["trigger_state"] != 'ALWAYS':
                    triggerConditions.append(f'curr_state == STATE_{cueData["trigger_state"]:s}')
                if hasInput:
                    if cueData['input'] in self.variables:
                        input_str = cueData['input']
                    else:
                        input_str = 'digitalRead(%d)' % int(cueData['input'])
                    triggerConditional = ''
                    if cueData['trigger'] in ['on_open','on_low']:
                        triggerConditional = f'{input_str:s} == LOW'
                    elif cueData['trigger'] in ['on_closed','on_high']:
                        triggerConditional = f'{input_str:s} == HIGH'
                    elif cueData['trigger'] in ['on_open_to_closed','on_low_to_high']:
                        triggerConditional = f'({input_str:s} != prevValue[{cueData["id"]:d}] && {input_str:s} == HIGH)'
                    elif cueData['trigger'] in ['on_closed_to_open','on_high_to_low']:
                        triggerConditional = f'({input_str:s} != prevValue[{cueData["id"]:d}] && {input_str:s} == LOW)'
                    triggerConditions.append(triggerConditional)

                triggerConditional = ' && '.join([f'({c:s})' for c in triggerConditions])

            if effectData['dormant'] != 'NONE':
                if effectData['outputType'] == 'SERVO':
                    dormantWrite = "servos[%d].writeMicroseconds(%s);" % (self.servoPins[int(effectData['pin'])],effectData['dormant'])
                elif effectData['outputType'] == 'VARIABLE' and pinType == 'digital':
                    dormantWrite = "%s = %s;" % (effectData['pin'],effectData['dormant'])
                elif effectData['outputType'] == 'VARIABLE':
                    dormantWrite = "%s =  %s > 0 ? HIGH : LOW;" % (effectData['pin'],effectData['dormant'])
                else:
                    dormantWrite = '%sWrite(%d, %s);' % (pinType,int(effectData['pin']),effectData['dormant'])
            else:
                dormantWrite = ''

            if useState and cueData["exit_state"] != 'NONE' and cueData["trigger_state"] != cueData["exit_state"]:
                exitState = f'if( isActive[{cueData["id"]:d}] <= 0 && curr_state == STATE_{cueData["trigger_state"]:s} )\n        {{\n            curr_state = STATE_{cueData["exit_state"]:s};\n        }}\n'
            else:
                exitState = ''

            if triggerConditional is not None:
                crStr += f'''
    if( {triggerConditional:s} )
    {{
        coroutine.loop();
    }}
    else
    {{
        isActive[{cueData["id"]:d}]--;
        {exitState:s}
        {dormantWrite:s}
    }}'''
            else:
                crStr += f'''
    isActive[{cueData["id"]:d}]--;
    {exitState:s}
    {dormantWrite:s}'''

        crStr += "\n\n    END_COROUTINE;\n}\n"

        return crStr

    def write_sketch(self, sketchPath):
        global funcData
        print("Writing sketch %s..." % sketchPath.stem)
        with sketchPath.open('w') as f:
            f.write('\n// Sketch generated by gensketch.py by Lokno Decker\n\n')
            f.write('#include "Coroutines.h"\n')
            if self.servoCount > 0:
                f.write('#include <Servo.h>\n')

            # Force NOISE signal to top of signal functions
            signalTypeList = list(self.signalTypes)
            noisePrimaryName = funcData.get_primary_name('NOISE')
            noiseIndex = -1
            for i,func_name in enumerate(signalTypeList):
                if funcData.get_primary_name(func_name) == noisePrimaryName:
                    noiseIndex = i
                    break
            if noiseIndex >= 0:
                del signalTypeList[noiseIndex]
                signalTypeList.insert(0,noisePrimaryName)

            f.write('\n'.join(funcData.get_functions(signalTypeList))+'\n')

            f.write('\nint scale( int minVal, int maxVal, float x )\n{\n    return (int)(minVal + x * (maxVal-minVal));\n}\n')

            f.write('\nCoroutines<%d> coroutines;\n' % self.numCoroutines)

            f.write('\nint prevValue[%d] = {%s};\n' % (self.numCues, ','.join(['LOW'] * self.numCues)))
            f.write('\nint isActive[%d] = {%s};\n' % (self.numCues, ','.join(['0'] * self.numCues)))
            f.write('\nunsigned long startTimes[%d] = {%s};\n' % (self.numCues, ','.join(['0u'] * self.numCues)))

            # set up state enum
            if self.state_count > 1:
                f.write('\ntypedef enum\n{\n')
                f.write(',\n'.join([f'    STATE_{x:s}' for x in self.states]))
                f.write('\n} state_enum;\n')
                f.write('\nstate_enum curr_state = STATE_A;\n')

            f.write('\n')
            for var_name,var_dormant in self.variables.items():
                if var_dormant == 'NONE':
                    dormant = 'LOW'
                elif var_dormant == 'LOW' or var_dormant == 'HIGH':
                    dormant = var_dormant
                elif self.intRE.match(dormant):
                    dormant = 'LOW'
                    if int(var_dormant) > 0:
                        dormant = 'HIGH'
                else:
                    dormant = 'LOW'

                f.write(f'int {var_name:s} = {dormant};\n')

            if self.servoCount > 0:
                f.write('\nServo servos[%d];\n' % self.servoCount)

            globalDecs = "\n// global state\n"

            if self.servoCount > 0:
                servoData = []
                f.write('\n')
                for i in range(self.servoCount):
                    servoID = str(i).zfill(2)
                    servoBounds = ('SERVO_%s_MIN' % servoID, 'SERVO_%s_MAX' % servoID)
                    f.write('\n#define %s %d\n#define %s %d\n' % (servoBounds[0],defaultServoMin,servoBounds[1],defaultServoMax))
                    servoData.append(servoBounds)


            for cueData in self.effectMap.values():
                for signal in cueData['signals']:
                    # declare global state for output
                    if funcData.get_primary_name(signal['type'].upper()) == 'RANDOM':
                        globalDecs += "randCache rc_cr%02d_out%02d = { true, 0, 0u };\n" % (cueData['id'],signal['id'])

            f.write(globalDecs)

            for cueName,cueData in self.effectMap.items():
                hasInput = not self.blankRE.match(cueData['input']) and cueData['input'].upper() != "NONE"
                for signalData in cueData['signals']:
                    coroutineStr = self.write_coroutine(cueName,cueData,signalData,hasInput)
                    f.write(coroutineStr)

            setupBody  = ""
            loopBody   = "    int inputTemp;"

            setupBody += '    ' + '\n    '.join([ "pinMode( %2d, INPUT_PULLUP ); // %s" % (pin, ', '.join(cue_names)) for pin,cue_names in self.input_pins.items() ])
            setupBody += '\n\n    ' + '\n    '.join([ "pinMode( %2d, OUTPUT ); // %s" % (int(pin),outData['effect']) for pin,outData in self.uniqueOutputs.items() if outData['outputType'] != 'SERVO' and outData['outputType'] != 'VARIABLE' ])

            setupBody += '\n\n    ' + '\n    '.join([ "servos[%d].attach( %2d, %s, %s);" % (self.servoPins[int(pin)], int(pin), servoData[self.servoPins[int(pin)]][0], servoData[self.servoPins[int(pin)]][1]) for pin,outData in self.uniqueOutputs.items() if outData['outputType'] == 'SERVO' ])

            setupBody += "\n\n    // initial values"
            setupBody += '\n\n'

            servoID = 0
            for output,outData in self.uniqueOutputs.items():
                dormantVal = outData['dormant']
                if dormantVal == 'NONE':
                    if outData['type'] == 'DIGITAL':
                        dormantVal = 'LOW'
                    else:
                        dormantVal = '0'
                if outData['outputType'] == 'SERVO':
                    setupBody += '    servos[%d].writeMicroseconds(%s);\n' % (servoID,dormantVal)
                    servoID += 1
                elif output not in self.variables:
                    if outData['type'] == 'DIGITAL':
                        setupBody += '    digitalWrite'
                    else: #ANALOG
                        setupBody += '    analogWrite'
                    setupBody += "(%2d,%s);\n" % (int(output),dormantVal) 

            for cueName,cueData in self.effectMap.items():
                hasInput = not self.blankRE.match(cueData['input']) and cueData['input'].upper() != "NONE"
                useState = self.state_count > 1

                spaces = '    '

                triggerConditional = ''
                if cueData['trigger'] in ['on_open','on_low']:
                    triggerConditional = 'inputTemp == LOW'
                elif cueData['trigger'] in ['on_closed','on_high']:
                    triggerConditional = 'inputTemp == HIGH'
                elif cueData['trigger'] in ['on_open_to_closed','on_low_to_high']:
                    triggerConditional = f'(inputTemp != prevValue[{cueData["id"]:d}] && inputTemp == HIGH)'
                elif cueData['trigger']  in ['on_closed_to_open','on_high_to_low']:
                    triggerConditional = f'(inputTemp != prevValue[{cueData["id"]:d}] && inputTemp == LOW)'

                if useState or hasInput:
                    spaces += '    '

                    conditions = []
                    if useState:
                        conditions.append(f'curr_state == STATE_{cueData["trigger_state"]:s}')

                    if hasInput:
                        if cueData['input'] in self.variables:
                            loopBody += f'\n    inputTemp = {cueData["input"]:s};'
                        else:
                            loopBody += f'\n    inputTemp = digitalRead({cueData["input"]:s});'
                        conditions.append(triggerConditional)

                    conditions.append(f'isActive[{cueData["id"]:d}] <= 0')

                    condition_str = ' && '.join([f'({c:s})' for c in conditions])

                    loopBody += f'\n    if( {condition_str:s} )\n    {{\n'

                tempBody = spaces + "// Cue: %s\n" % cueName
                tempBody += spaces + "isActive[%d] = %d;\n" % (cueData['id'],len(cueData['signals']))
                tempBody += spaces + "startTimes[%d] = millis();\n" % cueData['id']
                    
                for signal in cueData['signals']:
                    tempBody += spaces + "coroutines.start(coroutineN%02d);\n" % signal['id']

                for signal in cueData['signals']:
                    if funcData.get_primary_name(signal['type']) == "RANDOM":
                        tempBody += spaces + "rc_cr%02d_out%02d.isLevel = true;\n" % (cueData['id'],signal['id'])
                        tempBody += spaces + "rc_cr%02d_out%02d.cacheTime = 0;\n" % (cueData['id'],signal['id'])

                if hasInput:
                    loopBody += tempBody
                    loopBody += "    }\n"
                    loopBody += "    prevValue[%d] = inputTemp;\n" % (cueData['id'])
                elif useState:
                    loopBody += tempBody
                    loopBody += "    }\n"
                else:
                    setupBody += '\n' + tempBody

            if 'RANDOM' in self.signalTypes:
                setupBody = "    randomSeed(analogRead(0));\n\n" + setupBody;

            f.write('''
void setup() {
%s
}

void loop() {
    coroutines.update();
%s
}
    ''' % (setupBody,loopBody))


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Translates a table of effects into an arduino sketch that performs the represented actions.')
    parser.add_argument('input', type=str, help='input file (csv)')
    parser.add_argument('output', type=str, help='output sketch (ino)')
    parser.add_argument('-n', help='no clobber on overwrite')

    args = parser.parse_args()

    filePath = Path( args.input )

    sketchPath = Path( args.output )

    if filePath.suffix == "":
        print( "Warning: No file extension given, assuming CSV...")
        filePath = Path( args.input + ".csv" )

    if filePath.suffix != ".csv":
        print("Error: File type %s not supported." % filePath.suffix)
        sys.exit(-1)

    if not filePath.exists():
        print("File %s not found" % (filePath))
        sys.exit(-1)

    if sketchPath.suffix == "":
        print( "Warning: No extension given for sketch name, assuming INO...")
        sketchPath = Path( args.output + ".ino" )

    if sketchPath.suffix != ".ino":
        print("Error: Sketch name must end in 'ino' suffix.")
        sys.exit(-1)

    if sketchPath.exists() and args.n:
        prompt = "Sketch %s already exists. Overwrite? (y/n): " % sketchPath.stem
        choice = input(prompt)
        while choice.lower() not in ['y','n']:
            print(random.choice(['Sorry?', 'Excuse me?', 'Come again?', 'I didn\'t understand that', 'What?']))
            choice = input(prompt)
        if choice.lower() == 'n':
            print("Aborting...")
            sys.exit(0)

    ed = SketchGen(filePath)
    ed.write_sketch(sketchPath)