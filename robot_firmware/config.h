#pragma once

#include <Arduino.h>

namespace RobotConfig {

// Seeed 4A Motor Shield V1.0 / MC33932.
constexpr uint8_t RIGHT_PWM = 9;
constexpr uint8_t RIGHT_IN1 = 5;
constexpr uint8_t RIGHT_IN2 = 6;

constexpr uint8_t LEFT_PWM = 10;
constexpr uint8_t LEFT_IN1 = 7;
constexpr uint8_t LEFT_IN2 = 8;

constexpr uint8_t SHIELD_EN = 4;
constexpr uint8_t SHIELD_FT = 3;

// Encoders.
constexpr uint8_t RIGHT_ENC_A = 2;
constexpr uint8_t RIGHT_ENC_B = A2;
constexpr uint8_t LEFT_ENC_A = 11;
constexpr uint8_t LEFT_ENC_B = A3;

constexpr int8_t RIGHT_ENCODER_SIGN = 1;
constexpr int8_t LEFT_ENCODER_SIGN = -1;

// Serial protocol and safety.
constexpr uint32_t SERIAL_BAUD = 115200;
constexpr uint32_t DEFAULT_WATCHDOG_TIMEOUT_MS = 5000;
constexpr uint8_t COMMAND_BUFFER_SIZE = 48;

// Short blocking pauses are used only for safe H-bridge switching.
constexpr uint16_t REVERSE_STOP_DELAY_MS = 50;
constexpr uint16_t ENABLE_SETTLE_DELAY_MS = 20;

}  // namespace RobotConfig
