#include "motor_driver.h"

#include "config.h"

namespace MotorDriver {
namespace {

int16_t currentLeftSpeed = 0;
int16_t currentRightSpeed = 0;

bool directionReverses(int16_t oldSpeed, int16_t newSpeed) {
  return (oldSpeed > 0 && newSpeed < 0) ||
         (oldSpeed < 0 && newSpeed > 0);
}

void setRightDirection(int16_t speedValue) {
  if (speedValue > 0) {
    // Physical forward for the mirrored right motor.
    digitalWrite(RobotConfig::RIGHT_IN1, LOW);
    digitalWrite(RobotConfig::RIGHT_IN2, HIGH);
  } else if (speedValue < 0) {
    digitalWrite(RobotConfig::RIGHT_IN1, HIGH);
    digitalWrite(RobotConfig::RIGHT_IN2, LOW);
  } else {
    digitalWrite(RobotConfig::RIGHT_IN1, LOW);
    digitalWrite(RobotConfig::RIGHT_IN2, LOW);
  }
}

void setLeftDirection(int16_t speedValue) {
  if (speedValue > 0) {
    digitalWrite(RobotConfig::LEFT_IN1, HIGH);
    digitalWrite(RobotConfig::LEFT_IN2, LOW);
  } else if (speedValue < 0) {
    digitalWrite(RobotConfig::LEFT_IN1, LOW);
    digitalWrite(RobotConfig::LEFT_IN2, HIGH);
  } else {
    digitalWrite(RobotConfig::LEFT_IN1, LOW);
    digitalWrite(RobotConfig::LEFT_IN2, LOW);
  }
}

}  // namespace

void begin() {
  pinMode(RobotConfig::RIGHT_PWM, OUTPUT);
  pinMode(RobotConfig::RIGHT_IN1, OUTPUT);
  pinMode(RobotConfig::RIGHT_IN2, OUTPUT);

  pinMode(RobotConfig::LEFT_PWM, OUTPUT);
  pinMode(RobotConfig::LEFT_IN1, OUTPUT);
  pinMode(RobotConfig::LEFT_IN2, OUTPUT);

  pinMode(RobotConfig::SHIELD_EN, OUTPUT);
  stop();
}

void stop() {
  analogWrite(RobotConfig::LEFT_PWM, 0);
  analogWrite(RobotConfig::RIGHT_PWM, 0);
  digitalWrite(RobotConfig::SHIELD_EN, LOW);
  setLeftDirection(0);
  setRightDirection(0);
  currentLeftSpeed = 0;
  currentRightSpeed = 0;
}

void set(int16_t leftSpeed, int16_t rightSpeed) {
  leftSpeed = constrain(leftSpeed, -255, 255);
  rightSpeed = constrain(rightSpeed, -255, 255);

  const bool reversing =
    directionReverses(currentLeftSpeed, leftSpeed) ||
    directionReverses(currentRightSpeed, rightSpeed);

  if (reversing) {
    stop();
    delay(RobotConfig::REVERSE_STOP_DELAY_MS);
  }

  // Remove PWM before changing a direction input to zero.
  if (leftSpeed == 0) {
    analogWrite(RobotConfig::LEFT_PWM, 0);
  }
  if (rightSpeed == 0) {
    analogWrite(RobotConfig::RIGHT_PWM, 0);
  }

  if (leftSpeed == 0 && rightSpeed == 0) {
    stop();
    return;
  }

  setLeftDirection(leftSpeed);
  setRightDirection(rightSpeed);

  if (!isEnabled()) {
    digitalWrite(RobotConfig::SHIELD_EN, HIGH);
    delay(RobotConfig::ENABLE_SETTLE_DELAY_MS);
  }

  analogWrite(RobotConfig::LEFT_PWM, abs(leftSpeed));
  analogWrite(RobotConfig::RIGHT_PWM, abs(rightSpeed));
  currentLeftSpeed = leftSpeed;
  currentRightSpeed = rightSpeed;
}

int16_t leftCommand() {
  return currentLeftSpeed;
}

int16_t rightCommand() {
  return currentRightSpeed;
}

bool isMoving() {
  return currentLeftSpeed != 0 || currentRightSpeed != 0;
}

bool isEnabled() {
  return digitalRead(RobotConfig::SHIELD_EN) == HIGH;
}

}  // namespace MotorDriver
