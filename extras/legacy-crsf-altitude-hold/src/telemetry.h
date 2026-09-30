#pragma once

#include "altitude_controller.h"
#include "common.h"
#include "rangefinder.h"
#include <array>
#include <cstdint>
#include <string>

namespace crsfstack {

struct TelemetryState {
    std::array<uint64_t, 256> frame_counts{};
    std::array<uint64_t, 256> frame_last_ms{};

    uint64_t heartbeat_count() const { return frame_counts[0x0B]; }
    uint64_t battery_count() const { return frame_counts[0x08]; }
    uint64_t link_count() const { return frame_counts[0x14]; }
    uint64_t attitude_count() const { return frame_counts[0x1E]; }
    uint64_t flight_mode_count() const { return frame_counts[0x21]; }
    uint64_t baro_count() const { return frame_counts[0x09]; }

    uint64_t rc_frames = 0;
    uint64_t rc_bad_crc = 0;
    uint64_t fc_frames = 0;

    bool battery_valid = false;
    double battery_v = 0.0;
    double current_a = 0.0;
    int mah = 0;
    int battery_pct = -1;

    bool attitude_valid = false;
    double pitch_rad = 0.0;
    double roll_rad = 0.0;
    double yaw_rad = 0.0;

    bool flight_mode_valid = false;
    std::string flight_mode;

    bool link_valid = false;
    int uplink_rssi1 = 0;
    int uplink_rssi2 = 0;
    int uplink_lq = 0;
    int uplink_snr = 0;
    int downlink_rssi = 0;
    int downlink_lq = 0;
    int downlink_snr = 0;

    bool baro_alt_valid = false;
    double baro_alt_m = 0.0;

    uint64_t stats_last_emit_ms = 0;
};

class MonitorPublisher {
public:
    MonitorPublisher();
    ~MonitorPublisher();
    void publish(const std::string& line);
private:
    int fd_ = -1;
    bool enabled_ = false;
};

void decode_fc_telemetry(const uint8_t* frame, size_t frame_size, TelemetryState& telem, bool verbose);
void publish_status(MonitorPublisher& pub,
                    const SensorState& sensor,
                    const ControlSnapshot& ctrl,
                    const TelemetryState& telem);

}
