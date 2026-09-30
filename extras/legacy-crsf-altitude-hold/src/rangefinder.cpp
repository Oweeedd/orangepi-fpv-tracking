#include "rangefinder.h"

#include <gpiod.h>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <iostream>
#include <thread>
#include <vector>
#include <algorithm>

namespace crsfstack {

static double median(std::vector<double> v) {
    if (v.empty()) return -1.0;
    std::sort(v.begin(), v.end());
    const size_t n = v.size();
    return (n % 2 == 0) ? (v[n / 2 - 1] + v[n / 2]) / 2.0 : v[n / 2];
}

MeasureResult measure_once(gpiod_line* trig, gpiod_line* echo) {
    MeasureResult r;

    gpiod_line_set_value(trig, 0);
    std::this_thread::sleep_for(std::chrono::microseconds(5));
    gpiod_line_set_value(trig, 1);
    std::this_thread::sleep_for(std::chrono::microseconds(10));
    gpiod_line_set_value(trig, 0);

    uint64_t wait_start = micros_now();
    while (!g_stop && gpiod_line_get_value(echo) == 0) {
        if (micros_now() - wait_start > 30000) {
            r.timeout = true;
            return r;
        }
    }
    if (g_stop) return r;

    uint64_t echo_start = micros_now();
    while (!g_stop && gpiod_line_get_value(echo) == 1) {
        if (micros_now() - echo_start > 30000) {
            r.timeout = true;
            return r;
        }
    }
    if (g_stop) return r;

    const uint64_t echo_end = micros_now();
    const double pulse_us = static_cast<double>(echo_end - echo_start);
    const double distance_cm = pulse_us / 58.0;

    if (distance_cm >= g_cfg.sensor_min_cm && distance_cm <= g_cfg.sensor_max_cm) {
        r.ok = true;
        r.distance_cm = distance_cm;
    }
    return r;
}

void sensor_worker(SensorState* state, bool verbose) {
    gpiod_chip* chip = gpiod_chip_open(Config::GPIO_CHIPNAME);
    if (!chip) {
        std::cerr << "[Sensor] open " << Config::GPIO_CHIPNAME << " failed: " << std::strerror(errno) << "\n";
        return;
    }

    gpiod_line* trig = gpiod_chip_get_line(chip, Config::TRIG_LINE);
    gpiod_line* echo = gpiod_chip_get_line(chip, Config::ECHO_LINE);
    if (!trig || !echo) {
        std::cerr << "[Sensor] get_line failed\n";
        gpiod_chip_close(chip);
        return;
    }

    if (gpiod_line_request_output(trig, "hc_sr04_trig", 0) < 0) {
        std::cerr << "[Sensor] request_output failed: " << std::strerror(errno) << "\n";
        gpiod_chip_close(chip);
        return;
    }

    if (gpiod_line_request_input(echo, "hc_sr04_echo") < 0) {
        std::cerr << "[Sensor] request_input failed: " << std::strerror(errno) << "\n";
        gpiod_line_release(trig);
        gpiod_chip_close(chip);
        return;
    }

    std::cerr << "[Sensor] started chip=" << Config::GPIO_CHIPNAME
              << " trig=" << Config::TRIG_LINE
              << " echo=" << Config::ECHO_LINE << "\n";

    while (!g_stop) {
        state->cycles.fetch_add(1, std::memory_order_relaxed);
        std::vector<double> valid;

        for (int i = 0; i < Config::SENSOR_SAMPLES_PER_CYCLE && !g_stop; ++i) {
            MeasureResult r = measure_once(trig, echo);
            if (r.ok) valid.push_back(r.distance_cm);
            if (r.timeout) state->timeouts.fetch_add(1, std::memory_order_relaxed);
            std::this_thread::sleep_for(std::chrono::milliseconds(Config::SENSOR_INTER_SAMPLE_DELAY_MS));
        }

        if (!valid.empty()) {
            state->good_cycles.fetch_add(1, std::memory_order_relaxed);
            const double d = median(valid);
            state->distance_cm.store(d, std::memory_order_relaxed);
            state->valid.store(1, std::memory_order_relaxed);
            state->stamp_ms.store(millis_now(), std::memory_order_relaxed);
            if (verbose) {
                std::cerr << "[Sensor] d=" << d << " cm (" << valid.size() << "/" << Config::SENSOR_SAMPLES_PER_CYCLE << ")\n";
            }
        } else {
            state->valid.store(0, std::memory_order_relaxed);
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(Config::SENSOR_CYCLE_DELAY_MS));
    }

    gpiod_line_release(echo);
    gpiod_line_release(trig);
    gpiod_chip_close(chip);
    std::cerr << "[Sensor] stopped\n";
}

}
