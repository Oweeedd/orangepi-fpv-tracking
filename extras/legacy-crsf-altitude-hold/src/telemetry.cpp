#include "telemetry.h"
#include "crsf_protocol.h"

#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <cstring>
#include <iostream>
#include <sstream>

namespace crsfstack {

namespace {

static int16_t be16(const uint8_t* p) {
    return static_cast<int16_t>((static_cast<uint16_t>(p[0]) << 8) | p[1]);
}

std::string sanitize_token(std::string s) {
    for (char& ch : s) {
        const unsigned char u = static_cast<unsigned char>(ch);
        if (u < 32 || u > 126 || ch == ' ') ch = '_';
    }
    if (s.empty()) s = "-";
    return s;
}

} // namespace

MonitorPublisher::MonitorPublisher() {
    fd_ = ::socket(AF_UNIX, SOCK_DGRAM, 0);
    enabled_ = fd_ >= 0;
}

MonitorPublisher::~MonitorPublisher() {
    if (fd_ >= 0) ::close(fd_);
}

void MonitorPublisher::publish(const std::string& line) {
    if (!enabled_) return;

    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    std::snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", Config::MONITOR_SOCKET_PATH);
    ::sendto(fd_, line.c_str(), line.size(), MSG_DONTWAIT,
             reinterpret_cast<const sockaddr*>(&addr), sizeof(addr));
}

void decode_fc_telemetry(const uint8_t* frame, size_t frame_size, TelemetryState& telem, bool verbose) {
    if (frame_size < 4 || !validate_crc(frame, frame_size)) return;

    telem.fc_frames++;

    const uint8_t type = frame[2];
    const uint8_t* p = &frame[3];
    const uint8_t payload_len = static_cast<uint8_t>(frame_size - 4);

    telem.frame_counts[type]++;
    telem.frame_last_ms[type] = millis_now();

    switch (type) {
        case 0x08: // battery
            if (payload_len >= 8) {
                telem.battery_valid = true;
                telem.battery_v = static_cast<double>(be16(p)) / 10.0;
                telem.current_a = static_cast<double>(be16(p + 2)) / 10.0;
                telem.mah = (static_cast<int>(p[4]) << 16) | (static_cast<int>(p[5]) << 8) | p[6];
                telem.battery_pct = p[7];
            }
            break;
        case 0x09: // baro alt
            if (payload_len >= 2) {
                telem.baro_alt_valid = true;
                telem.baro_alt_m = static_cast<double>(be16(p)) / 10.0;
            }
            break;
        case 0x14: // link stats
            if (payload_len >= 10) {
                telem.link_valid = true;
                telem.uplink_rssi1 = -static_cast<int>(p[0]);
                telem.uplink_rssi2 = -static_cast<int>(p[1]);
                telem.uplink_lq = p[2];
                telem.uplink_snr = static_cast<int8_t>(p[3]);
                telem.downlink_rssi = -static_cast<int>(p[7]);
                telem.downlink_lq = p[8];
                telem.downlink_snr = static_cast<int8_t>(p[9]);
            }
            break;
        case 0x1E: // attitude
            if (payload_len >= 6) {
                telem.attitude_valid = true;
                telem.pitch_rad = static_cast<double>(be16(p)) / 10000.0;
                telem.roll_rad = static_cast<double>(be16(p + 2)) / 10000.0;
                telem.yaw_rad = static_cast<double>(be16(p + 4)) / 10000.0;
            }
            break;
        case 0x21: // flight mode string
            if (payload_len > 0) {
                telem.flight_mode_valid = true;
                telem.flight_mode.assign(reinterpret_cast<const char*>(p),
                                         reinterpret_cast<const char*>(p + payload_len));
                while (!telem.flight_mode.empty() && telem.flight_mode.back() == '\0') {
                    telem.flight_mode.pop_back();
                }
                telem.flight_mode = sanitize_token(telem.flight_mode);
            }
            break;
        default:
            break;
    }

    if (verbose && type != Config::CRSF_FRAME_RC_CHANNELS) {
        std::cerr << "[TEL] type=" << frame_type_name(type)
                  << " size=" << static_cast<int>(payload_len)
                  << " count=" << telem.frame_counts[type] << "\n";
    }
}

void publish_status(MonitorPublisher& pub,
                    const SensorState& sensor,
                    const ControlSnapshot& ctrl,
                    const TelemetryState& telem) {
    std::ostringstream ss;
    const uint64_t now = millis_now();
    const uint64_t age_ms = sensor.stamp_ms.load(std::memory_order_relaxed) == 0
        ? 0
        : now - sensor.stamp_ms.load(std::memory_order_relaxed);

    ss << "STATUS"
       << " mode=" << mode_name(ctrl.mode)
       << " sensor_valid=" << sensor.valid.load(std::memory_order_relaxed)
       << " sensor_cm=" << sensor.distance_cm.load(std::memory_order_relaxed)
       << " sensor_age_ms=" << age_ms
       << " sensor_cycles=" << sensor.cycles.load(std::memory_order_relaxed)
       << " sensor_good=" << sensor.good_cycles.load(std::memory_order_relaxed)
       << " sensor_timeouts=" << sensor.timeouts.load(std::memory_order_relaxed)
       << " target_valid=" << static_cast<int>(ctrl.target_valid)
       << " target_cm=" << ctrl.target_cm
       << " measured_cm=" << ctrl.measured_cm
       << " vertical_speed_cms=" << ctrl.vertical_speed_cms
       << " sensor_fresh=" << static_cast<int>(ctrl.sensor_fresh)
       << " logging_enabled=" << static_cast<int>(ctrl.logging_enabled)
       << " aux2_raw=" << ctrl.aux2_raw
       << " aux3_raw=" << ctrl.aux3_raw
       << " live_thr=" << ctrl.live_thr
       << " base_thr=" << ctrl.base_thr
       << " out_thr=" << ctrl.output_thr
       << " corr=" << ctrl.correction
       << " rc_frames=" << telem.rc_frames
       << " rc_bad_crc=" << telem.rc_bad_crc
       << " fc_frames=" << telem.fc_frames
       << " hb_count=" << telem.heartbeat_count()
       << " batt_count=" << telem.battery_count()
       << " link_count=" << telem.link_count()
       << " att_count=" << telem.attitude_count()
       << " fm_count=" << telem.flight_mode_count()
       << " baro_count=" << telem.baro_count()
       << " battery_valid=" << telem.battery_valid
       << " battery_v=" << telem.battery_v
       << " current_a=" << telem.current_a
       << " mah=" << telem.mah
       << " battery_pct=" << telem.battery_pct
       << " link_valid=" << telem.link_valid
       << " uplink_lq=" << telem.uplink_lq
       << " uplink_rssi1=" << telem.uplink_rssi1
       << " uplink_rssi2=" << telem.uplink_rssi2
       << " uplink_snr=" << telem.uplink_snr
       << " downlink_lq=" << telem.downlink_lq
       << " downlink_rssi=" << telem.downlink_rssi
       << " downlink_snr=" << telem.downlink_snr
       << " attitude_valid=" << telem.attitude_valid
       << " pitch_rad=" << telem.pitch_rad
       << " roll_rad=" << telem.roll_rad
       << " yaw_rad=" << telem.yaw_rad
       << " flight_mode_valid=" << telem.flight_mode_valid
       << " flight_mode=" << sanitize_token(telem.flight_mode.empty() ? "-" : telem.flight_mode)
       << " baro_alt_valid=" << telem.baro_alt_valid
       << " baro_alt_m=" << telem.baro_alt_m
       << " hb_age_ms=" << (telem.frame_last_ms[0x0B] ? now - telem.frame_last_ms[0x0B] : 0)
       << " batt_age_ms=" << (telem.frame_last_ms[0x08] ? now - telem.frame_last_ms[0x08] : 0)
       << " link_age_ms=" << (telem.frame_last_ms[0x14] ? now - telem.frame_last_ms[0x14] : 0)
       << " att_age_ms=" << (telem.frame_last_ms[0x1E] ? now - telem.frame_last_ms[0x1E] : 0)
       << " fm_age_ms=" << (telem.frame_last_ms[0x21] ? now - telem.frame_last_ms[0x21] : 0)
       << " baro_age_ms=" << (telem.frame_last_ms[0x09] ? now - telem.frame_last_ms[0x09] : 0);

    pub.publish(ss.str());
}

}
