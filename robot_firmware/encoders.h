#pragma once

#include <Arduino.h>

namespace Encoders {

struct Snapshot {
  int32_t left;
  int32_t right;
};

void begin();
Snapshot read();
void reset();

}  // namespace Encoders
