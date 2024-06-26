class LoknoButton {
public:
    LoknoButton(int pin, int debounce_time, bool pullup_enable, bool active_low)
        : pin(pin), debounce_time(debounce_time), pullup_enable(pullup_enable), active_low(active_low), pressed(false), changed(false), last_state(HIGH), last_debounce_time(0) {
    }

    void begin() {
        pinMode(this->pin, this->pullup_enable ? INPUT_PULLUP : INPUT);
        this->pressed = digitalRead(this->pin);
        if (this->active_low) this->pressed = !this->pressed;
        this->last_state = this->pressed;
        this->changed = false;
        this->last_debounce_time = millis();
    }

    void read() {
        bool curr_state = digitalRead(this->pin);

        if (this->active_low) curr_state = !curr_state;

        if (curr_state != last_state) this->last_debounce_time = millis();

        if ((millis() - this->last_debounce_time) > this->debounce_time) {
            if (curr_state != this->pressed) {
                this->pressed = curr_state;
                this->changed = true;
            } else {
                this->changed = false;
            }
        } else {
            this->changed = false;
        }

        this->last_state = curr_state;
    }

    bool isPressed() const { return this->pressed; }
    bool releasedFor(int ms) const {
        if (!this->pressed && (millis() - this->last_debounce_time) >= ms) {
            return true;
        }
        return false;
    }
    bool wasPressed() const { return this->changed && this->pressed; }
    bool wasReleased() const { return this->changed && !this->pressed; }

private:
    int pin;
    int debounce_time;
    bool active_low;
    bool pressed;
    bool changed;
    bool last_state;
    bool pullup_enable;
    unsigned long last_debounce_time;
};
