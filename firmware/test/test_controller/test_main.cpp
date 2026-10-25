#include <Arduino.h>
#include <unity.h>
#include "controller.h"

void hysteresis() {
  Tank::Controller c;
  c.mode = Tank::Mode::Auto;
  c.sample(10000, 20, true, true, false);
  c.sample(10500, 20, true, true, false);
  TEST_ASSERT_FALSE(c.pump);
  c.sample(11000, 20, true, true, false);
  TEST_ASSERT_TRUE(c.pump);
  c.sample(11500, 70, true, true, false);
  TEST_ASSERT_TRUE(c.pump);
  c.sample(12000, 90, true, true, false);
  TEST_ASSERT_FALSE(c.pump);
}
void faults_latch() {
  Tank::Controller c;
  c.mode = Tank::Mode::Auto;
  c.sample(10000, NAN, true, true, false);
  for (int i = 0; i < 3; ++i) c.sample(11000 + i * 500, 10, true, true, false);
  TEST_ASSERT_FALSE(c.pump);
  TEST_ASSERT_EQUAL_INT(int(Tank::Fault::SensorInvalid), int(c.fault));
  c.sample(13000, 10, true, true, true);
  TEST_ASSERT_TRUE(c.pump);
  c.sample(13500, 10, true, false, true);
  TEST_ASSERT_FALSE(c.pump);
  TEST_ASSERT_EQUAL_INT(int(Tank::Fault::HighFloat), int(c.fault));
}
void rollover() {
  Tank::Controller c;
  c.mode = Tank::Mode::Auto;
  c.lastOff = UINT32_MAX - 5000;
  c.sample(1000, 20, true, true, false);
  c.sample(1500, 20, true, true, false);
  c.sample(2000, 20, true, true, false);
  TEST_ASSERT_FALSE(c.pump);
  c.sample(6000, 20, true, true, false);
  TEST_ASSERT_TRUE(c.pump);
}
void all_protection_causes() {
  for (int scenario = 0; scenario < 4; ++scenario) {
    Tank::Controller c;
    c.mode = Tank::Mode::Auto;
    for (uint32_t now = 10000; now <= 11000; now += 500) c.sample(now, 20, true, true, false);
    TEST_ASSERT_TRUE(c.pump);
    if (scenario == 0) c.sample(12000, NAN, true, true, true);
    if (scenario == 1) c.sample(12000, 95, true, true, true);
    if (scenario == 2) c.sample(12000, 20, false, true, true);
    if (scenario == 3) c.sample(c.runStarted + Tank::MAX_RUN_MS, 20, true, true, false);
    TEST_ASSERT_FALSE(c.pump);
    TEST_ASSERT_NOT_EQUAL(int(Tank::Fault::None), int(c.fault));
    c.sample(1000000, 20, true, true, false);
    TEST_ASSERT_FALSE(c.pump);
  }
}
void minimum_off_and_off_mode() {
  Tank::Controller c;
  c.mode = Tank::Mode::Auto;
  for (uint32_t now = 10000; now <= 11000; now += 500) c.sample(now, 20, true, true, false);
  c.sample(12000, 90, true, true, false);
  c.sample(21999, 20, true, true, false);
  TEST_ASSERT_FALSE(c.pump);
  c.sample(22000, 20, true, true, false);
  TEST_ASSERT_TRUE(c.pump);
  c.mode = Tank::Mode::Off;
  c.sample(22500, 20, true, true, false);
  TEST_ASSERT_FALSE(c.pump);
}
void setup() {
  delay(2000);
  UNITY_BEGIN();
  RUN_TEST(hysteresis);
  RUN_TEST(faults_latch);
  RUN_TEST(rollover);
  RUN_TEST(all_protection_causes);
  RUN_TEST(minimum_off_and_off_mode);
  UNITY_END();
}
void loop() {}
