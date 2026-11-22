#pragma once

#include <Arduino.h>

namespace Safety {

void begin();
void update();

bool faultActive();
bool motionAllowed();

// Call after each valid motion command. Passing false disarms watchdog.
void noteMotionCommand(bool moving);
void disarmWatchdog();

// Zero disables watchdog and is accepted only while motors are stopped.
bool setWatchdogTimeout(uint32_t timeoutMs);
uint32_t watchdogTimeoutMs();
bool watchdogArmed();

}  // namespace Safety
