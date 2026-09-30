#pragma once

#include "common.h"
#include <atomic>

struct gpiod_line;

namespace crsfstack {

struct SensorState {
    std::atomic<double> distance_cm{-1.0};
    std::atomic<int> valid{0};
    std::atomic<uint64_t> stamp_ms{0};
    std::atomic<uint64_t> cycles{0};
    std::atomic<uint64_t> good_cycles{0};
    std::atomic<uint64_t> timeouts{0};
};

struct MeasureResult {
    bool ok = false;
    bool timeout = false;
    double distance_cm = 0.0;
};

MeasureResult measure_once(gpiod_line* trig, gpiod_line* echo);
void sensor_worker(SensorState* state, bool verbose);

}
