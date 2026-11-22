#include "encoders.h"

#include <PinChangeInterrupt.h>

#include "config.h"

namespace Encoders {
namespace {

volatile int32_t rightTicksRaw = 0;
volatile int32_t leftTicksRaw = 0;

void rightEncoderISR() {
  if (digitalRead(RobotConfig::RIGHT_ENC_B) == HIGH) {
    rightTicksRaw++;
  } else {
    rightTicksRaw--;
  }
}

void leftEncoderISR() {
  if (digitalRead(RobotConfig::LEFT_ENC_B) == HIGH) {
    leftTicksRaw++;
  } else {
    leftTicksRaw--;
  }
}

}  // namespace

void begin() {
  pinMode(RobotConfig::RIGHT_ENC_A, INPUT_PULLUP);
  pinMode(RobotConfig::RIGHT_ENC_B, INPUT_PULLUP);
  pinMode(RobotConfig::LEFT_ENC_A, INPUT_PULLUP);
  pinMode(RobotConfig::LEFT_ENC_B, INPUT_PULLUP);

  attachInterrupt(
    digitalPinToInterrupt(RobotConfig::RIGHT_ENC_A),
    rightEncoderISR,
    RISING
  );

  attachPCINT(
    digitalPinToPCINT(RobotConfig::LEFT_ENC_A),
    leftEncoderISR,
    RISING
  );
}

Snapshot read() {
  noInterrupts();
  const int32_t leftRaw = leftTicksRaw;
  const int32_t rightRaw = rightTicksRaw;
  interrupts();

  Snapshot snapshot;
  snapshot.left = leftRaw * RobotConfig::LEFT_ENCODER_SIGN;
  snapshot.right = rightRaw * RobotConfig::RIGHT_ENCODER_SIGN;
  return snapshot;
}

void reset() {
  noInterrupts();
  leftTicksRaw = 0;
  rightTicksRaw = 0;
  interrupts();
}

}  // namespace Encoders
