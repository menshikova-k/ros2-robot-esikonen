#pragma once

#include <Arduino.h>

namespace MotorDriver {

void begin();

// Positive values move the corresponding track physically forward.
// Valid range is -255..255; values outside it are constrained.
void set(int16_t leftSpeed, int16_t rightSpeed);

// PWM=0, EN=LOW and all direction inputs LOW.
void stop();

int16_t leftCommand();
int16_t rightCommand();
bool isMoving();
bool isEnabled();

}  // namespace MotorDriver
