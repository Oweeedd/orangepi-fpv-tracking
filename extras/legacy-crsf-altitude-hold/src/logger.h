#pragma once

#include "altitude_controller.h"
#include "common.h"
#include "rangefinder.h"
#include "telemetry.h"

#include <fstream>
#include <string>

namespace crsfstack {

class CsvLogger {
public:
    CsvLogger() = default;
    ~CsvLogger();

    bool update_enable(bool enabled, const std::string& log_dir, std::string& err);
    void log_row(const SensorState& sensor, const ControlSnapshot& ctrl, const TelemetryState& telem);
    const std::string& current_path() const { return path_; }
    bool enabled() const { return enabled_; }

private:
    bool open_new_file(const std::string& log_dir, std::string& err);
    void close_file();

    bool enabled_ = false;
    std::ofstream out_;
    std::string path_;
    int rows_since_flush_ = 0;
};

}
