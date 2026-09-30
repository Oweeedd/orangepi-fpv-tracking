#pragma once

#include "common.h"
#include "rangefinder.h"
#include <cstdint>
#include <string>

namespace crsfstack {

enum class FlightMode {
    Off,
    Hold,
    Land
};

struct ControlSnapshot {
    FlightMode mode = FlightMode::Off;
    bool target_valid = false;
    bool sensor_fresh = false;
    bool logging_enabled = false;
    double measured_cm = -1.0;
    double vertical_speed_cms = 0.0;
    double target_cm = 0.0;
    uint16_t aux2_raw = 0;
    uint16_t aux3_raw = 0;
    uint16_t live_thr = 0;
    uint16_t output_thr = 0;
    uint16_t base_thr = 0;
    int correction = 0;
};

FlightMode decode_mode(uint16_t aux3);
std::string mode_name(FlightMode mode);

struct AltitudeController {
    FlightMode mode = FlightMode::Off;
    FlightMode prev_mode = FlightMode::Off;

    bool target_valid = false;
    double target_cm = 0.0;

    uint16_t hold_base_thr = 0;
    uint16_t hold_stick_ref = 0;
    uint16_t last_output_thr = 0;
    bool output_initialized = false;

    double integral = 0.0;
    double prev_error = 0.0;
    double vertical_speed_cms = 0.0;
    double last_measured_cm = 0.0;
    bool last_measured_valid = false;
    uint64_t last_measure_ms = 0;
    uint64_t last_ctrl_ms = 0;
    uint64_t last_log_ms = 0;

    void reset_pid();
    bool sensor_fresh(const SensorState& sensor) const;
    void update_vertical_speed(double measured_cm);
    void capture_target_if_possible(const SensorState& sensor);
    double throttle_stick_to_target_rate(uint16_t thr) const;
    int compute_pid_correction(double measured_cm);
    int apply_throttle_slew(int desired_thr, double dt_sec);
    ControlSnapshot apply(uint16_t* channels, const SensorState& sensor, bool verbose);
};

}
