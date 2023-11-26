
typedef struct {
    int ypos;
    int xpos;
    int zpos;
} CompressionInfo;

unsigned char next_value( unsigned char* values, unsigned short* zeroes, CompressionInfo* info )
{
    signed char ret = 0;
    if( values[info->ypos] == 0 ) // in zero sequence
    {
        info->xpos++;
        if( info->xpos == zeroes[info->zpos] )
        {
            info->xpos = 0;
            info->ypos++;
            info->zpos++;
        }
    }
    else
    {
        ret = values[info->ypos];
        info->ypos++;
    }

    return ret;
}

// Initial Values
const unsigned char initLED = 0;

// Accumulated Values
unsigned char accumLED;

// Position Info
CompressionInfo infoLED;

// Compressed Deltas
const signed char valLED[3] = {0,255,0};

const unsigned int zeroLED[2] = {30,29};

unsigned int frame = 0;
unsigned int frame_count = 60;
unsigned long last_frame;
unsigned long target_delta = 33;

void setup() {
    pinMode(6, OUTPUT);
    accumLED = initLED;
    infoLED.xpos = infoLED.ypos = infoLED.zpos = 0;

    last_frame = millis();
}

void loop() {

    if( (millis()-last_frame) > target_delta)
    {
        last_frame = millis();

        accumLED += next_value(valLED,zeroLED,&infoLED);
        analogWrite(6, accumLED);

        frame++;
        if( frame >= frame_count )
        {
            frame = 0;
            accumLED = initLED;
            infoLED.xpos = infoLED.ypos = infoLED.zpos = 0;
        }
    }
}
