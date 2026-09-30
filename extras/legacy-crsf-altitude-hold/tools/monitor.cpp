#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

namespace {

std::map<std::string, std::string> parse_kv(const std::string& line) {
    std::map<std::string, std::string> out;
    std::istringstream iss(line);
    std::string token;
    iss >> token;
    while (iss >> token) {
        auto pos = token.find('=');
        if (pos == std::string::npos) continue;
        out[token.substr(0, pos)] = token.substr(pos + 1);
    }
    return out;
}

std::string get(const std::map<std::string, std::string>& m, const std::string& k, const std::string& d = "-") {
    auto it = m.find(k);
    return it == m.end() ? d : it->second;
}

void clear_screen() {
    std::cout << "\033[2J\033[H";
}

void render(const std::map<std::string, std::string>& s) {
    clear_screen();
    std::cout << "CRSF Stack Monitor\n";
    std::cout << "==================\n\n";

    std::cout << "Mode       : " << get(s, "mode") << "\n";
    std::cout << "AUX        : aux2=" << get(s, "aux2_raw")
              << " aux3=" << get(s, "aux3_raw")
              << " logging=" << get(s, "logging_enabled") << "\n";
    std::cout << "Sensor cm  : " << get(s, "sensor_cm") << "\n";
    std::cout << "Measured   : " << get(s, "measured_cm") << " cm\n";
    std::cout << "Vel z      : " << get(s, "vertical_speed_cms") << " cm/s\n";
    std::cout << "Sensor age : " << get(s, "sensor_age_ms") << " ms fresh=" << get(s, "sensor_fresh") << "\n";
    std::cout << "Target cm  : " << get(s, "target_cm") << " (valid=" << get(s, "target_valid") << ")\n";
    std::cout << "Throttle   : live=" << get(s, "live_thr")
              << " base=" << get(s, "base_thr")
              << " out=" << get(s, "out_thr")
              << " corr=" << get(s, "corr") << "\n\n";

    std::cout << "Sensor stats\n";
    std::cout << "  cycles    : " << get(s, "sensor_cycles") << "\n";
    std::cout << "  good      : " << get(s, "sensor_good") << "\n";
    std::cout << "  timeouts  : " << get(s, "sensor_timeouts") << "\n\n";

    std::cout << "Link / CRSF\n";
    std::cout << "  rc frames : " << get(s, "rc_frames") << "\n";
    std::cout << "  bad crc   : " << get(s, "rc_bad_crc") << "\n";
    std::cout << "  fc frames : " << get(s, "fc_frames") << "\n";
    std::cout << "  counts    : hb=" << get(s, "hb_count")
              << " att=" << get(s, "att_count")
              << " batt=" << get(s, "batt_count")
              << " link=" << get(s, "link_count")
              << " fm=" << get(s, "fm_count")
              << " baro=" << get(s, "baro_count") << "\n";
    std::cout << "  uplink    : LQ=" << get(s, "uplink_lq")
              << " RSSI1=" << get(s, "uplink_rssi1")
              << " RSSI2=" << get(s, "uplink_rssi2")
              << " SNR=" << get(s, "uplink_snr") << "\n";
    std::cout << "  downlink  : LQ=" << get(s, "downlink_lq")
              << " RSSI=" << get(s, "downlink_rssi")
              << " SNR=" << get(s, "downlink_snr") << "\n\n";

    std::cout << "FC telemetry\n";
    std::cout << "  ages ms   : hb=" << get(s, "hb_age_ms")
              << " att=" << get(s, "att_age_ms")
              << " batt=" << get(s, "batt_age_ms")
              << " link=" << get(s, "link_age_ms")
              << " fm=" << get(s, "fm_age_ms")
              << " baro=" << get(s, "baro_age_ms") << "\n";
    std::cout << "  battery   : valid=" << get(s, "battery_valid")
              << " V=" << get(s, "battery_v")
              << " A=" << get(s, "current_a")
              << " mAh=" << get(s, "mah")
              << " %=" << get(s, "battery_pct") << "\n";
    std::cout << "  attitude  : valid=" << get(s, "attitude_valid")
              << " pitch=" << get(s, "pitch_rad")
              << " roll=" << get(s, "roll_rad")
              << " yaw=" << get(s, "yaw_rad") << "\n";
    std::cout << "  flightmode: valid=" << get(s, "flight_mode_valid")
              << " value=" << get(s, "flight_mode") << "\n";
    std::cout << "  baro alt  : valid=" << get(s, "baro_alt_valid")
              << " value=" << get(s, "baro_alt_m") << " m\n\n";

    std::cout << "Socket      : /tmp/crsf_stack_monitor.sock\n";
    std::cout << "Quit        : Ctrl+C\n" << std::flush;
}

} // namespace

int main() {
    const char* path = "/tmp/crsf_stack_monitor.sock";
    ::unlink(path);

    const int fd = ::socket(AF_UNIX, SOCK_DGRAM, 0);
    if (fd < 0) {
        std::perror("socket");
        return 1;
    }

    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    std::snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", path);

    if (::bind(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
        std::perror("bind");
        ::close(fd);
        return 1;
    }

    std::map<std::string, std::string> state;
    char buf[4096];

    while (true) {
        const ssize_t n = ::recv(fd, buf, sizeof(buf) - 1, 0);
        if (n < 0) {
            if (errno == EINTR) continue;
            std::perror("recv");
            break;
        }
        buf[n] = '\0';
        state = parse_kv(std::string(buf, static_cast<size_t>(n)));
        render(state);
    }

    ::close(fd);
    ::unlink(path);
    return 0;
}
