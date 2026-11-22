#include "config.h"
#include "encoders.h"
#include "motor_driver.h"
#include "safety.h"
#include "serial_protocol.h"

void setup() {
  Serial.begin(RobotConfig::SERIAL_BAUD);

  MotorDriver::begin();
  Encoders::begin();
  Safety::begin();

  delay(100);
  SerialProtocol::begin();
}

void loop() {
  Safety::update();
  SerialProtocol::update();
}
