#pragma once

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <csignal>
#include <string>

namespace crsfstack {

inline uint64_t millis_now() {
    using namespace std::chrono;
    return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

inline uint64_t micros_now() {
    using namespace std::chrono;
    return duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count();
}

template <typename T>
inline T clamp(T v, T lo, T hi) {
    return std::max(lo, std::min(v, hi));
}

extern volatile sig_atomic_t g_stop;

struct Config {
    static constexpr uint8_t CRSF_ADDRESS = 0xC8;
    static constexpr uint8_t CRSF_FRAME_RC_CHANNELS = 0x16;
    static constexpr int CRSF_BAUD = 416666;
    static constexpr size_t MAX_FRAME_BUF = 64;

    static constexpr int THROTTLE_IDX = 2;
    static constexpr int AUX2_IDX = 5;
    static constexpr int AUX3_IDX = 6;

    static constexpr int AUX_SWITCH_LOW_VALUE = 172;
    static constexpr int AUX_SWITCH_MID_VALUE = 992;
    static constexpr int AUX_SWITCH_HIGH_VALUE = 1811;

    static constexpr int THROTTLE_MIN = 172;
    static constexpr int THROTTLE_MAX = 1811;

    static constexpr const char* GPIO_CHIPNAME = "/dev/gpiochip1";
    static constexpr unsigned int TRIG_LINE = 3;
    static constexpr unsigned int ECHO_LINE = 4;

    static constexpr int SENSOR_SAMPLES_PER_CYCLE = 3;
    static constexpr int SENSOR_INTER_SAMPLE_DELAY_MS = 20;
    static constexpr int SENSOR_CYCLE_DELAY_MS = 50;

    static constexpr const char* MONITOR_SOCKET_PATH = "/tmp/crsf_stack_monitor.sock";
    static constexpr const char* DEFAULT_CONFIG_PATH = "/etc/crsf-stack.conf";
    static constexpr const char* FALLBACK_CONFIG_PATH = "./crsf-stack.conf";
};

struct RuntimeConfig {
    int aux2_log_high_min = 1400;

    int aux3_low_value = Config::AUX_SWITCH_LOW_VALUE;
    int aux3_mid_value = Config::AUX_SWITCH_MID_VALUE;
    int aux3_high_value = Config::AUX_SWITCH_HIGH_VALUE;

    int throttle_min = Config::THROTTLE_MIN;
    int throttle_max = Config::THROTTLE_MAX;
    int max_throttle_correction = 100;
    int throttle_slew_up_per_sec = 160;
    int throttle_slew_down_per_sec = 70;

    double sensor_min_cm = 2.0;
    double sensor_max_cm = 120.0;
    uint64_t sensor_fresh_ms = 250;

    double hold_kp = 5.0;
    double hold_ki = 0.6;
    double hold_kd = 2.5;
    double vel_k = 1.8;
    double integral_limit = 20.0;

    double land_descent_rate_cm_per_sec = 0.25;
    double target_capture_min_cm = 3.0;
    double target_capture_max_cm = 110.0;

    int throttle_stick_deadband = 25;
    int throttle_stick_max_delta = 250;
    double hold_target_slew_cm_per_sec = 5.0;

    double near_ground_cm = 18.0;
    int near_ground_max_correction = 45;

    bool force_off_on_stale_sensor = true;

    bool logging_enabled_by_default = false;
    std::string log_dir = "/home/orangepi/crsf_logs";
    int log_flush_every_rows = 10;
};

extern RuntimeConfig g_cfg;

bool load_runtime_config(const std::string& path, RuntimeConfig& cfg, std::string& err);

}
