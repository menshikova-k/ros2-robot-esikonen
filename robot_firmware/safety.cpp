#include "safety.h"

#include "config.h"
#include "motor_driver.h"

namespace Safety {
namespace {

uint32_t currentWatchdogTimeoutMs =
  RobotConfig::DEFAULT_WATCHDOG_TIMEOUT_MS;
uint32_t lastMotionCommandMs = 0;
bool isWatchdogArmed = false;
bool isFaultReported = false;

}  // namespace

void begin() {
  pinMode(RobotConfig::SHIELD_FT, INPUT_PULLUP);
  currentWatchdogTimeoutMs = RobotConfig::DEFAULT_WATCHDOG_TIMEOUT_MS;
  lastMotionCommandMs = millis();
  isWatchdogArmed = false;
  isFaultReported = false;
}

bool faultActive() {
  return digitalRead(RobotConfig::SHIELD_FT) == LOW;
}

bool motionAllowed() {
  return !faultActive();
}

void noteMotionCommand(bool moving) {
  lastMotionCommandMs = millis();
  isWatchdogArmed = currentWatchdogTimeoutMs > 0 && moving;
}

void disarmWatchdog() {
  isWatchdogArmed = false;
}

bool setWatchdogTimeout(uint32_t timeoutMs) {
  if (timeoutMs == 0 && MotorDriver::isMoving()) {
    return false;
  }

  currentWatchdogTimeoutMs = timeoutMs;
  lastMotionCommandMs = millis();
  isWatchdogArmed = timeoutMs > 0 && MotorDriver::isMoving();
  return true;
}

uint32_t watchdogTimeoutMs() {
  return currentWatchdogTimeoutMs;
}

bool watchdogArmed() {
  return isWatchdogArmed;
}

void update() {
  if (faultActive()) {
    if (MotorDriver::isMoving() || MotorDriver::isEnabled()) {
      MotorDriver::stop();
    }
    disarmWatchdog();

    if (!isFaultReported) {
      isFaultReported = true;
      Serial.println(F("FAULT FT=LOW; MOTORS_STOPPED"));
    }
    return;
  }

  if (isFaultReported) {
    isFaultReported = false;
    Serial.println(F("FAULT_CLEARED FT=HIGH"));
  }

  if (isWatchdogArmed &&
      millis() - lastMotionCommandMs >= currentWatchdogTimeoutMs) {
    MotorDriver::stop();
    disarmWatchdog();
    Serial.println(F("WATCHDOG STOP"));
  }
}

}  // namespace Safety
