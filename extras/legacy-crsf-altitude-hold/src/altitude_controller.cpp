#include "altitude_controller.h"

#include <cmath>
#include <iostream>

namespace crsfstack {

FlightMode decode_mode(uint16_t aux3) {
    const int d_low = std::abs(static_cast<int>(aux3) - g_cfg.aux3_low_value);
    const int d_mid = std::abs(static_cast<int>(aux3) - g_cfg.aux3_mid_value);
    const int d_high = std::abs(static_cast<int>(aux3) - g_cfg.aux3_high_value);

    const int best = std::min({d_low, d_mid, d_high});
    if (best == d_mid) return FlightMode::Hold;
    if (best == d_high) return FlightMode::Land;
    return FlightMode::Off;
}

std::string mode_name(FlightMode mode) {
    switch (mode) {
        case FlightMode::Off: return "OFF";
        case FlightMode::Hold: return "HOLD";
        case FlightMode::Land: return "LAND";
    }
    return "?";
}

void AltitudeController::reset_pid() {
    integral = 0.0;
    prev_error = 0.0;
    last_ctrl_ms = millis_now();
}

bool AltitudeController::sensor_fresh(const SensorState& sensor) const {
    if (!sensor.valid.load(std::memory_order_relaxed)) return false;
    const uint64_t age = millis_now() - sensor.stamp_ms.load(std::memory_order_relaxed);
    return age < g_cfg.sensor_fresh_ms;
}

void AltitudeController::update_vertical_speed(double measured_cm) {
    const uint64_t now = millis_now();
    if (!last_measured_valid || last_measure_ms == 0) {
        last_measured_valid = true;
        last_measured_cm = measured_cm;
        last_measure_ms = now;
        vertical_speed_cms = 0.0;
        return;
    }

    double dt = static_cast<double>(now - last_measure_ms) / 1000.0;
    dt = clamp(dt, 0.001, 0.25);
    const double raw_vel = (measured_cm - last_measured_cm) / dt;
    vertical_speed_cms = 0.75 * vertical_speed_cms + 0.25 * raw_vel;
    last_measured_cm = measured_cm;
    last_measure_ms = now;
}

void AltitudeController::capture_target_if_possible(const SensorState& sensor) {
    if (!sensor_fresh(sensor)) return;
    const double d = sensor.distance_cm.load(std::memory_order_relaxed);
    if (d >= g_cfg.target_capture_min_cm && d <= g_cfg.target_capture_max_cm) {
        target_cm = d;
        target_valid = true;
    }
}

double AltitudeController::throttle_stick_to_target_rate(uint16_t thr) const {
    int delta = static_cast<int>(thr) - static_cast<int>(hold_stick_ref);
    delta = clamp(delta, -g_cfg.throttle_stick_max_delta, g_cfg.throttle_stick_max_delta);
    if (std::abs(delta) <= g_cfg.throttle_stick_deadband) return 0.0;

    const int sign = (delta > 0) ? 1 : -1;
    const int effective = std::abs(delta) - g_cfg.throttle_stick_deadband;
    double norm = static_cast<double>(effective) /
                  static_cast<double>(g_cfg.throttle_stick_max_delta - g_cfg.throttle_stick_deadband);
    norm = clamp(norm, 0.0, 1.0);
    return sign * norm * g_cfg.hold_target_slew_cm_per_sec;
}

int AltitudeController::compute_pid_correction(double measured_cm) {
    const uint64_t now = millis_now();
    double dt = (last_ctrl_ms == 0) ? 0.02 : static_cast<double>(now - last_ctrl_ms) / 1000.0;
    last_ctrl_ms = now;
    dt = clamp(dt, 0.001, 0.2);

    const double error = target_cm - measured_cm;
    integral += error * dt;
    integral = clamp(integral, -g_cfg.integral_limit, g_cfg.integral_limit);

    const double derivative = (error - prev_error) / dt;
    prev_error = error;

    double out = g_cfg.hold_kp * error
               + g_cfg.hold_ki * integral
               + g_cfg.hold_kd * derivative
               - g_cfg.vel_k * vertical_speed_cms;

    int corr_limit = g_cfg.max_throttle_correction;
    if (measured_cm > 0.0 && measured_cm < g_cfg.near_ground_cm) {
        corr_limit = std::min(corr_limit, g_cfg.near_ground_max_correction);
    }

    out = clamp(out, static_cast<double>(-corr_limit), static_cast<double>(corr_limit));
    return static_cast<int>(std::lround(out));
}

int AltitudeController::apply_throttle_slew(int desired_thr, double dt_sec) {
    desired_thr = clamp(desired_thr, g_cfg.throttle_min, g_cfg.throttle_max);
    if (!output_initialized) {
        output_initialized = true;
        last_output_thr = static_cast<uint16_t>(desired_thr);
        return desired_thr;
    }

    const int delta = desired_thr - static_cast<int>(last_output_thr);
    const int slew_per_sec = (delta >= 0)
        ? g_cfg.throttle_slew_up_per_sec
        : g_cfg.throttle_slew_down_per_sec;
    const int max_step = std::max(1, static_cast<int>(std::lround(slew_per_sec * dt_sec)));
    const int applied = clamp(delta, -max_step, max_step);
    last_output_thr = static_cast<uint16_t>(clamp(static_cast<int>(last_output_thr) + applied,
                                                  g_cfg.throttle_min,
                                                  g_cfg.throttle_max));
    return static_cast<int>(last_output_thr);
}

ControlSnapshot AltitudeController::apply(uint16_t* channels, const SensorState& sensor, bool verbose) {
    ControlSnapshot snap;
    snap.aux2_raw = channels[Config::AUX2_IDX];
    snap.aux3_raw = channels[Config::AUX3_IDX];
    snap.live_thr = channels[Config::THROTTLE_IDX];
    snap.logging_enabled = snap.aux2_raw >= g_cfg.aux2_log_high_min;
    mode = decode_mode(snap.aux3_raw);
    snap.mode = mode;

    if (mode != prev_mode) {
        if (mode == FlightMode::Off) {
            target_valid = false;
            output_initialized = false;
            reset_pid();
            std::cerr << "[ALT] mode=OFF aux3=" << snap.aux3_raw << "\n";
        } else if (mode == FlightMode::Hold) {
            capture_target_if_possible(sensor);
            hold_base_thr = snap.live_thr;
            hold_stick_ref = snap.live_thr;
            last_output_thr = snap.live_thr;
            output_initialized = true;
            reset_pid();
            std::cerr << "[ALT] mode=HOLD target="
                      << (target_valid ? std::to_string(target_cm) : std::string("NaN"))
                      << " cm base_thr=" << hold_base_thr
                      << " stick_ref=" << hold_stick_ref << " aux3=" << snap.aux3_raw << "\n";
        } else if (mode == FlightMode::Land) {
            capture_target_if_possible(sensor);
            last_output_thr = snap.live_thr;
            output_initialized = true;
            reset_pid();
            std::cerr << "[ALT] mode=LAND start_target="
                      << (target_valid ? std::to_string(target_cm) : std::string("NaN"))
                      << " cm aux3=" << snap.aux3_raw << "\n";
        }
        prev_mode = mode;
    }

    snap.sensor_fresh = sensor_fresh(sensor);
    if (snap.sensor_fresh) {
        snap.measured_cm = sensor.distance_cm.load(std::memory_order_relaxed);
        update_vertical_speed(snap.measured_cm);
        snap.vertical_speed_cms = vertical_speed_cms;
    } else {
        vertical_speed_cms = 0.0;
        snap.vertical_speed_cms = 0.0;
    }

    if (mode == FlightMode::Off || (g_cfg.force_off_on_stale_sensor && !snap.sensor_fresh)) {
        snap.target_valid = target_valid;
        snap.target_cm = target_cm;
        snap.base_thr = hold_base_thr;
        snap.output_thr = snap.live_thr;
        return snap;
    }

    if (!target_valid) {
        capture_target_if_possible(sensor);
        if (target_valid && mode == FlightMode::Hold) {
            hold_base_thr = snap.live_thr;
            hold_stick_ref = snap.live_thr;
        }
        reset_pid();
        if (!target_valid) {
            snap.target_valid = false;
            snap.output_thr = snap.live_thr;
            snap.base_thr = hold_base_thr;
            return snap;
        }
    }

    const uint64_t now = millis_now();
    double dt = (last_ctrl_ms == 0) ? 0.02 : static_cast<double>(now - last_ctrl_ms) / 1000.0;
    dt = clamp(dt, 0.001, 0.2);

    if (mode == FlightMode::Land) {
        target_cm -= g_cfg.land_descent_rate_cm_per_sec * dt;
        target_cm = std::max(target_cm, g_cfg.target_capture_min_cm);
    } else if (mode == FlightMode::Hold) {
        const double target_rate = throttle_stick_to_target_rate(snap.live_thr);
        target_cm += target_rate * dt;
        target_cm = clamp(target_cm, g_cfg.target_capture_min_cm, g_cfg.target_capture_max_cm);
    }

    const int correction = compute_pid_correction(snap.measured_cm);
    const int desired_thr = (mode == FlightMode::Hold)
        ? clamp(static_cast<int>(hold_base_thr) + correction, g_cfg.throttle_min, g_cfg.throttle_max)
        : clamp(static_cast<int>(snap.live_thr) + correction, g_cfg.throttle_min, g_cfg.throttle_max);

    const int mixed_thr = apply_throttle_slew(desired_thr, dt);
    channels[Config::THROTTLE_IDX] = static_cast<uint16_t>(mixed_thr);

    snap.target_valid = target_valid;
    snap.target_cm = target_cm;
    snap.base_thr = hold_base_thr;
    snap.correction = correction;
    snap.output_thr = static_cast<uint16_t>(mixed_thr);

    if (verbose && (now - last_log_ms > 200)) {
        last_log_ms = now;
        std::cerr << "[ALT] mode=" << mode_name(mode)
                  << " d=" << snap.measured_cm
                  << " vz=" << snap.vertical_speed_cms
                  << " target=" << target_cm
                  << " thr_live=" << snap.live_thr
                  << " base_thr=" << hold_base_thr
                  << " corr=" << correction
                  << " thr_out=" << mixed_thr
                  << " aux2=" << snap.aux2_raw
                  << " aux3=" << snap.aux3_raw << "\n";
    }

    return snap;
}

}
