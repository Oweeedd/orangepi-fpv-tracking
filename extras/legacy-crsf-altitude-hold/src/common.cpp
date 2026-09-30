#include "common.h"

#include <cctype>
#include <fstream>
#include <sstream>
#include <unordered_map>

namespace crsfstack {

volatile sig_atomic_t g_stop = 0;
RuntimeConfig g_cfg{};

namespace {

std::string trim(const std::string& s) {
    size_t a = 0;
    while (a < s.size() && std::isspace(static_cast<unsigned char>(s[a]))) ++a;
    size_t b = s.size();
    while (b > a && std::isspace(static_cast<unsigned char>(s[b - 1]))) --b;
    return s.substr(a, b - a);
}

bool parse_bool(const std::string& s, bool& out) {
    if (s == "1" || s == "true" || s == "on" || s == "yes") { out = true; return true; }
    if (s == "0" || s == "false" || s == "off" || s == "no") { out = false; return true; }
    return false;
}

template <typename T>
bool parse_num(const std::string& s, T& out) {
    std::istringstream iss(s);
    iss >> out;
    return !iss.fail() && iss.eof();
}

} // namespace

bool load_runtime_config(const std::string& path, RuntimeConfig& cfg, std::string& err) {
    std::ifstream in(path);
    if (!in) {
        err = "open failed";
        return false;
    }

    std::string section;
    std::string line;
    int line_no = 0;
    while (std::getline(in, line)) {
        ++line_no;
        const auto hash = line.find('#');
        if (hash != std::string::npos) line.erase(hash);
        line = trim(line);
        if (line.empty()) continue;

        if (line.front() == '[' && line.back() == ']') {
            section = trim(line.substr(1, line.size() - 2));
            continue;
        }

        const auto eq = line.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = section.empty() ? trim(line.substr(0, eq)) : section + "." + trim(line.substr(0, eq));
        const std::string value = trim(line.substr(eq + 1));

        auto fail = [&](const std::string& why) {
            err = path + ":" + std::to_string(line_no) + ": " + why;
            return false;
        };

        if (key == "control.aux2_log_high_min") { if (!parse_num(value, cfg.aux2_log_high_min)) return fail("bad int for aux2_log_high_min"); }
        else if (key == "control.aux3_low_value") { if (!parse_num(value, cfg.aux3_low_value)) return fail("bad int for aux3_low_value"); }
        else if (key == "control.aux3_mid_value") { if (!parse_num(value, cfg.aux3_mid_value)) return fail("bad int for aux3_mid_value"); }
        else if (key == "control.aux3_high_value") { if (!parse_num(value, cfg.aux3_high_value)) return fail("bad int for aux3_high_value"); }
        else if (key == "control.throttle_min") { if (!parse_num(value, cfg.throttle_min)) return fail("bad int for throttle_min"); }
        else if (key == "control.throttle_max") { if (!parse_num(value, cfg.throttle_max)) return fail("bad int for throttle_max"); }
        else if (key == "control.max_throttle_correction") { if (!parse_num(value, cfg.max_throttle_correction)) return fail("bad int for max_throttle_correction"); }
        else if (key == "control.throttle_slew_up_per_sec") { if (!parse_num(value, cfg.throttle_slew_up_per_sec)) return fail("bad int for throttle_slew_up_per_sec"); }
        else if (key == "control.throttle_slew_down_per_sec") { if (!parse_num(value, cfg.throttle_slew_down_per_sec)) return fail("bad int for throttle_slew_down_per_sec"); }
        else if (key == "control.sensor_min_cm") { if (!parse_num(value, cfg.sensor_min_cm)) return fail("bad float for sensor_min_cm"); }
        else if (key == "control.sensor_max_cm") { if (!parse_num(value, cfg.sensor_max_cm)) return fail("bad float for sensor_max_cm"); }
        else if (key == "control.sensor_fresh_ms") { if (!parse_num(value, cfg.sensor_fresh_ms)) return fail("bad int for sensor_fresh_ms"); }
        else if (key == "control.hold_kp") { if (!parse_num(value, cfg.hold_kp)) return fail("bad float for hold_kp"); }
        else if (key == "control.hold_ki") { if (!parse_num(value, cfg.hold_ki)) return fail("bad float for hold_ki"); }
        else if (key == "control.hold_kd") { if (!parse_num(value, cfg.hold_kd)) return fail("bad float for hold_kd"); }
        else if (key == "control.vel_k") { if (!parse_num(value, cfg.vel_k)) return fail("bad float for vel_k"); }
        else if (key == "control.integral_limit") { if (!parse_num(value, cfg.integral_limit)) return fail("bad float for integral_limit"); }
        else if (key == "control.land_descent_rate_cm_per_sec") { if (!parse_num(value, cfg.land_descent_rate_cm_per_sec)) return fail("bad float for land_descent_rate_cm_per_sec"); }
        else if (key == "control.target_capture_min_cm") { if (!parse_num(value, cfg.target_capture_min_cm)) return fail("bad float for target_capture_min_cm"); }
        else if (key == "control.target_capture_max_cm") { if (!parse_num(value, cfg.target_capture_max_cm)) return fail("bad float for target_capture_max_cm"); }
        else if (key == "control.throttle_stick_deadband") { if (!parse_num(value, cfg.throttle_stick_deadband)) return fail("bad int for throttle_stick_deadband"); }
        else if (key == "control.throttle_stick_max_delta") { if (!parse_num(value, cfg.throttle_stick_max_delta)) return fail("bad int for throttle_stick_max_delta"); }
        else if (key == "control.hold_target_slew_cm_per_sec") { if (!parse_num(value, cfg.hold_target_slew_cm_per_sec)) return fail("bad float for hold_target_slew_cm_per_sec"); }
        else if (key == "control.near_ground_cm") { if (!parse_num(value, cfg.near_ground_cm)) return fail("bad float for near_ground_cm"); }
        else if (key == "control.near_ground_max_correction") { if (!parse_num(value, cfg.near_ground_max_correction)) return fail("bad int for near_ground_max_correction"); }
        else if (key == "control.force_off_on_stale_sensor") { if (!parse_bool(value, cfg.force_off_on_stale_sensor)) return fail("bad bool for force_off_on_stale_sensor"); }
        else if (key == "logging.enabled_by_default") { if (!parse_bool(value, cfg.logging_enabled_by_default)) return fail("bad bool for enabled_by_default"); }
        else if (key == "logging.log_dir") { cfg.log_dir = value; }
        else if (key == "logging.flush_every_rows") { if (!parse_num(value, cfg.log_flush_every_rows)) return fail("bad int for flush_every_rows"); }
    }

    return true;
}

}
