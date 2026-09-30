#include "logger.h"

#include <filesystem>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <time.h>

namespace fs = std::filesystem;

namespace crsfstack {

CsvLogger::~CsvLogger() {
    close_file();
}

bool CsvLogger::open_new_file(const std::string& log_dir, std::string& err) {
    try {
        fs::create_directories(log_dir);
    } catch (const std::exception& e) {
        err = std::string("create_directories failed: ") + e.what();
        return false;
    }

    const auto t = std::time(nullptr);
    std::tm tm{};
    localtime_r(&t, &tm);
    std::ostringstream name;
    name << log_dir << "/crsf_log_"
         << std::put_time(&tm, "%Y%m%d_%H%M%S") << ".csv";
    path_ = name.str();

    out_.open(path_);
    if (!out_) {
        err = "failed to open log file: " + path_;
        path_.clear();
        return false;
    }

    out_ << "time_ms,mode,logging_enabled,aux2_raw,aux3_raw,sensor_valid,sensor_cm,sensor_age_ms,sensor_cycles,sensor_good,sensor_timeouts,sensor_fresh,measured_cm,vertical_speed_cms,target_valid,target_cm,live_thr,base_thr,out_thr,corr,rc_frames,rc_bad_crc,fc_frames,battery_valid,battery_v,current_a,mah,battery_pct,link_valid,uplink_lq,uplink_rssi1,uplink_rssi2,uplink_snr,downlink_lq,downlink_rssi,downlink_snr,attitude_valid,pitch_rad,roll_rad,yaw_rad,flight_mode_valid,flight_mode,baro_alt_valid,baro_alt_m\n";
    out_.flush();
    rows_since_flush_ = 0;
    std::cerr << "[LOG] started " << path_ << "\n";
    return true;
}

void CsvLogger::close_file() {
    if (out_) {
        out_.flush();
        out_.close();
    }
    if (!path_.empty()) {
        std::cerr << "[LOG] stopped " << path_ << "\n";
    }
    path_.clear();
    enabled_ = false;
    rows_since_flush_ = 0;
}

bool CsvLogger::update_enable(bool enabled, const std::string& log_dir, std::string& err) {
    if (enabled == enabled_) return true;
    if (!enabled) {
        close_file();
        return true;
    }
    if (!open_new_file(log_dir, err)) return false;
    enabled_ = true;
    return true;
}

void CsvLogger::log_row(const SensorState& sensor, const ControlSnapshot& ctrl, const TelemetryState& telem) {
    if (!enabled_ || !out_) return;

    const uint64_t now = millis_now();
    const uint64_t sensor_stamp = sensor.stamp_ms.load(std::memory_order_relaxed);
    const uint64_t sensor_age = sensor_stamp == 0 ? 0 : now - sensor_stamp;

    out_ << now << ','
         << mode_name(ctrl.mode) << ','
         << static_cast<int>(ctrl.logging_enabled) << ','
         << ctrl.aux2_raw << ','
         << ctrl.aux3_raw << ','
         << sensor.valid.load(std::memory_order_relaxed) << ','
         << sensor.distance_cm.load(std::memory_order_relaxed) << ','
         << sensor_age << ','
         << sensor.cycles.load(std::memory_order_relaxed) << ','
         << sensor.good_cycles.load(std::memory_order_relaxed) << ','
         << sensor.timeouts.load(std::memory_order_relaxed) << ','
         << static_cast<int>(ctrl.sensor_fresh) << ','
         << ctrl.measured_cm << ','
         << ctrl.vertical_speed_cms << ','
         << static_cast<int>(ctrl.target_valid) << ','
         << ctrl.target_cm << ','
         << ctrl.live_thr << ','
         << ctrl.base_thr << ','
         << ctrl.output_thr << ','
         << ctrl.correction << ','
         << telem.rc_frames << ','
         << telem.rc_bad_crc << ','
         << telem.fc_frames << ','
         << telem.battery_valid << ','
         << telem.battery_v << ','
         << telem.current_a << ','
         << telem.mah << ','
         << telem.battery_pct << ','
         << telem.link_valid << ','
         << telem.uplink_lq << ','
         << telem.uplink_rssi1 << ','
         << telem.uplink_rssi2 << ','
         << telem.uplink_snr << ','
         << telem.downlink_lq << ','
         << telem.downlink_rssi << ','
         << telem.downlink_snr << ','
         << telem.attitude_valid << ','
         << telem.pitch_rad << ','
         << telem.roll_rad << ','
         << telem.yaw_rad << ','
         << telem.flight_mode_valid << ','
         << '"' << telem.flight_mode << '"' << ','
         << telem.baro_alt_valid << ','
         << telem.baro_alt_m << '\n';

    if (++rows_since_flush_ >= std::max(1, g_cfg.log_flush_every_rows)) {
        out_.flush();
        rows_since_flush_ = 0;
    }
}

}
