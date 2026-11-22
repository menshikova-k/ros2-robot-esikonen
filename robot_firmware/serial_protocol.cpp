#include "serial_protocol.h"

#include <Arduino.h>
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

#include "config.h"
#include "encoders.h"
#include "motor_driver.h"
#include "safety.h"

namespace SerialProtocol {
namespace {

char commandBuffer[RobotConfig::COMMAND_BUFFER_SIZE];
uint8_t commandLength = 0;
bool commandOverflow = false;

bool parseInteger(
  const char *token,
  int minimum,
  int maximum,
  int &value
) {
  if (token == nullptr || *token == '\0') {
    return false;
  }

  char *end = nullptr;
  const long parsed = strtol(token, &end, 10);
  if (*end != '\0' || parsed < minimum || parsed > maximum) {
    return false;
  }

  value = static_cast<int>(parsed);
  return true;
}

void printEncoders() {
  const Encoders::Snapshot ticks = Encoders::read();
  Serial.print(F("ENC LEFT="));
  Serial.print(ticks.left);
  Serial.print(F(" RIGHT="));
  Serial.println(ticks.right);
}

void printStatus() {
  const Encoders::Snapshot ticks = Encoders::read();

  Serial.print(F("STATUS FT="));
  Serial.print(Safety::faultActive() ? 0 : 1);
  Serial.print(F(" EN="));
  Serial.print(MotorDriver::isEnabled() ? 1 : 0);
  Serial.print(F(" LEFT_PWM="));
  Serial.print(MotorDriver::leftCommand());
  Serial.print(F(" RIGHT_PWM="));
  Serial.print(MotorDriver::rightCommand());
  Serial.print(F(" LEFT_TICKS="));
  Serial.print(ticks.left);
  Serial.print(F(" RIGHT_TICKS="));
  Serial.print(ticks.right);
  Serial.print(F(" WATCHDOG="));

  if (Safety::watchdogTimeoutMs() == 0) {
    Serial.print(F("OFF"));
  } else {
    Serial.print(Safety::watchdogArmed() ? F("ARMED") : F("IDLE"));
  }

  Serial.print(F(" TIMEOUT_MS="));
  Serial.println(Safety::watchdogTimeoutMs());
}

void printHelp() {
  Serial.println(F("COMMANDS:"));
  Serial.println(F("  F <0..255>       forward"));
  Serial.println(F("  B <0..255>       backward"));
  Serial.println(F("  L <0..255>       turn left in place"));
  Serial.println(F("  R <0..255>       turn right in place"));
  Serial.println(F("  M <-255..255> <-255..255>  left/right"));
  Serial.println(F("  T <0|100..10000>  watchdog timeout ms; 0=off"));
  Serial.println(F("  S                stop"));
  Serial.println(F("  E                print encoders"));
  Serial.println(F("  RESET_E          reset encoders"));
  Serial.println(F("  STATUS           print state"));
  Serial.println(F("  HELP             print commands"));
  Serial.println(F("Default watchdog is 5000 ms; use T 500 for Orange Pi."));
}

void acceptMotion(int leftSpeed, int rightSpeed) {
  if (!Safety::motionAllowed()) {
    MotorDriver::stop();
    Safety::disarmWatchdog();
    Serial.println(F("ERR FAULT FT=LOW"));
    return;
  }

  MotorDriver::set(leftSpeed, rightSpeed);
  Safety::noteMotionCommand(MotorDriver::isMoving());

  Serial.print(F("OK M LEFT="));
  Serial.print(leftSpeed);
  Serial.print(F(" RIGHT="));
  Serial.println(rightSpeed);
}

void printCommandError() {
  Serial.println(F("ERR COMMAND; use HELP"));
}

void handleCommand(char *line) {
  char *command = strtok(line, " \t");
  if (command == nullptr) {
    return;
  }

  for (char *cursor = command; *cursor != '\0'; cursor++) {
    *cursor = static_cast<char>(toupper(static_cast<unsigned char>(*cursor)));
  }

  char *first = strtok(nullptr, " \t");
  char *second = strtok(nullptr, " \t");
  char *extra = strtok(nullptr, " \t");
  int speed = 0;
  int leftSpeed = 0;
  int rightSpeed = 0;
  int timeoutValue = 0;

  if (strcmp(command, "F") == 0 &&
      parseInteger(first, 0, 255, speed) && second == nullptr) {
    acceptMotion(speed, speed);
  } else if (strcmp(command, "B") == 0 &&
             parseInteger(first, 0, 255, speed) && second == nullptr) {
    acceptMotion(-speed, -speed);
  } else if (strcmp(command, "L") == 0 &&
             parseInteger(first, 0, 255, speed) && second == nullptr) {
    acceptMotion(-speed, speed);
  } else if (strcmp(command, "R") == 0 &&
             parseInteger(first, 0, 255, speed) && second == nullptr) {
    acceptMotion(speed, -speed);
  } else if (strcmp(command, "M") == 0 &&
             parseInteger(first, -255, 255, leftSpeed) &&
             parseInteger(second, -255, 255, rightSpeed) &&
             extra == nullptr) {
    acceptMotion(leftSpeed, rightSpeed);
  } else if (strcmp(command, "T") == 0 &&
             parseInteger(first, 0, 10000, timeoutValue) &&
             second == nullptr) {
    if (timeoutValue > 0 && timeoutValue < 100) {
      Serial.println(F("ERR TIMEOUT; use 0 or 100..10000"));
    } else if (!Safety::setWatchdogTimeout(timeoutValue)) {
      Serial.println(F("ERR STOP FIRST; then use T 0"));
    } else {
      Serial.print(F("OK TIMEOUT_MS="));
      Serial.println(Safety::watchdogTimeoutMs());
    }
  } else if (strcmp(command, "S") == 0 && first == nullptr) {
    MotorDriver::stop();
    Safety::disarmWatchdog();
    Serial.println(F("OK STOP"));
  } else if (strcmp(command, "E") == 0 && first == nullptr) {
    printEncoders();
  } else if (strcmp(command, "RESET_E") == 0 && first == nullptr) {
    Encoders::reset();
    Serial.println(F("OK ENCODERS_RESET"));
  } else if (strcmp(command, "STATUS") == 0 && first == nullptr) {
    printStatus();
  } else if (strcmp(command, "HELP") == 0 && first == nullptr) {
    printHelp();
  } else {
    printCommandError();
  }
}

}  // namespace

void begin() {
  commandLength = 0;
  commandOverflow = false;
  Serial.println(F("ROBOT READY 115200"));
  printHelp();
}

void update() {
  while (Serial.available() > 0) {
    const char incoming = static_cast<char>(Serial.read());

    if (incoming == '\r' || incoming == '\n') {
      if (commandOverflow) {
        Serial.println(F("ERR COMMAND_TOO_LONG"));
      } else if (commandLength > 0) {
        commandBuffer[commandLength] = '\0';
        handleCommand(commandBuffer);
      }

      commandLength = 0;
      commandOverflow = false;
      continue;
    }

    if (incoming < 32 || incoming > 126) {
      continue;
    }

    if (commandLength < RobotConfig::COMMAND_BUFFER_SIZE - 1) {
      commandBuffer[commandLength++] = incoming;
    } else {
      commandOverflow = true;
    }
  }
}

}  // namespace SerialProtocol
