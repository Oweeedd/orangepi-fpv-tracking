#include "altitude_controller.h"
#include "common.h"
#include "crsf_protocol.h"
#include "logger.h"
#include "rangefinder.h"
#include "telemetry.h"
#include "uart.h"

#include <chrono>
#include <csignal>
#include <cstring>
#include <iostream>
#include <thread>
#include <unistd.h>

namespace crsfstack {

void on_signal(int) {
    g_stop = 1;
}

bool process_elrs_to_fc(int elrs_fd,
                        int fc_fd,
                        FrameParser& parser,
                        AltitudeController& alt,
                        const SensorState& sensor,
                        TelemetryState& telem,
                        ControlSnapshot& last_ctrl,
                        bool verbose) {
    uint8_t bytes[256];
    const ssize_t n = ::read(elrs_fd, bytes, sizeof(bytes));
    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) return true;
        std::perror("read(elrs)");
        return false;
    }
    if (n == 0) return true;

    uint8_t frame[Config::MAX_FRAME_BUF];
    size_t frame_size = 0;

    for (ssize_t i = 0; i < n; ++i) {
        if (!parser.feed(bytes[i], frame, frame_size)) continue;

        if (frame_size >= 26 && frame[2] == Config::CRSF_FRAME_RC_CHANNELS && frame[1] == 24) {
            telem.rc_frames++;
            if (!validate_crc(frame, frame_size)) {
                telem.rc_bad_crc++;
                if (verbose) std::cerr << "[WARN] bad RC CRC, drop\n";
                continue;
            }

            uint16_t channels[8]{};
            unpack_channels_8(&frame[3], channels);
            last_ctrl = alt.apply(channels, sensor, verbose);

            uint8_t payload[22];
            pack_channels_8(channels, payload);
            uint8_t out[26];
            out[0] = Config::CRSF_ADDRESS;
            out[1] = 24;
            out[2] = Config::CRSF_FRAME_RC_CHANNELS;
            std::memcpy(&out[3], payload, 22);
            out[25] = crc8_d5(&out[2], 23);

            if (verbose) {
                std::cerr << "RC:";
                for (int c : channels) std::cerr << ' ' << c;
                std::cerr << '\n';
            }

            if (!write_full(fc_fd, out, sizeof(out))) return false;
        } else {
            if (!write_full(fc_fd, frame, frame_size)) return false;
        }
    }

    return true;
}

bool process_fc_to_elrs(int fc_fd,
                        int elrs_fd,
                        FrameParser& parser,
                        TelemetryState& telem,
                        bool verbose) {
    uint8_t bytes[256];
    const ssize_t n = ::read(fc_fd, bytes, sizeof(bytes));
    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) return true;
        std::perror("read(fc)");
        return false;
    }
    if (n == 0) return true;

    uint8_t frame[Config::MAX_FRAME_BUF];
    size_t frame_size = 0;

    for (ssize_t i = 0; i < n; ++i) {
        if (!parser.feed(bytes[i], frame, frame_size)) continue;
        decode_fc_telemetry(frame, frame_size, telem, verbose);
        if (!write_full(elrs_fd, frame, frame_size)) return false;
    }
    return true;
}

void usage(const char* prog) {
    std::cerr
        << "Usage: " << prog << " <elrs_uart> <fc_uart> [--verbose] [--config <path>]\n"
        << "Example: " << prog << " /dev/ttyS6 /dev/ttyS2 --verbose --config /etc/crsf-stack.conf\n";
}

}

int main(int argc, char** argv) {
    using namespace crsfstack;

    if (argc < 3) {
        usage(argv[0]);
        return 1;
    }

    const std::string elrs_dev = argv[1];
    const std::string fc_dev = argv[2];
    bool verbose = false;
    std::string config_path = Config::DEFAULT_CONFIG_PATH;

    for (int i = 3; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--verbose") {
            verbose = true;
        } else if (arg == "--config" && i + 1 < argc) {
            config_path = argv[++i];
        } else {
            std::cerr << "Unknown arg: " << arg << "\n";
            usage(argv[0]);
            return 1;
        }
    }

    std::string cfg_err;
    if (!load_runtime_config(config_path, g_cfg, cfg_err)) {
        const std::string fallback = Config::FALLBACK_CONFIG_PATH;
        if (config_path != fallback && load_runtime_config(fallback, g_cfg, cfg_err)) {
            config_path = fallback;
        } else {
            std::cerr << "[CFG] using defaults, could not load config from " << config_path << ": " << cfg_err << "\n";
            config_path = "<defaults>";
        }
    }

    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);

    const int elrs_fd = open_uart(elrs_dev);
    if (elrs_fd < 0) return 1;
    const int fc_fd = open_uart(fc_dev);
    if (fc_fd < 0) {
        ::close(elrs_fd);
        return 1;
    }

    std::cerr << "[crsf_stack] started\n"
              << "  ELRS -> " << elrs_dev << "\n"
              << "  FC   -> " << fc_dev << "\n"
              << "  baud = " << Config::CRSF_BAUD << "\n"
              << "  config = " << config_path << "\n"
              << "  log dir = " << g_cfg.log_dir << "\n"
              << "  monitor socket = " << Config::MONITOR_SOCKET_PATH << "\n";

    SensorState sensor;
    TelemetryState telem;
    ControlSnapshot last_ctrl;
    MonitorPublisher pub;
    CsvLogger logger;

    std::thread sensor_thread(sensor_worker, &sensor, verbose);

    FrameParser elrs_parser;
    FrameParser fc_parser;
    AltitudeController alt;

    uint64_t last_status_ms = 0;
    bool log_active = false;

    while (!g_stop) {
        const bool ok1 = process_elrs_to_fc(elrs_fd, fc_fd, elrs_parser, alt, sensor, telem, last_ctrl, verbose);
        const bool ok2 = process_fc_to_elrs(fc_fd, elrs_fd, fc_parser, telem, verbose);
        if (!ok1 || !ok2) break;

        std::string log_err;
        const bool want_log = g_cfg.logging_enabled_by_default || last_ctrl.logging_enabled;
        if (want_log != log_active) {
            if (!logger.update_enable(want_log, g_cfg.log_dir, log_err)) {
                std::cerr << "[LOG] " << log_err << "\n";
            } else {
                log_active = logger.enabled();
            }
        }

        const uint64_t now = millis_now();
        if (now - last_status_ms >= 100) {
            publish_status(pub, sensor, last_ctrl, telem);
            if (logger.enabled()) logger.log_row(sensor, last_ctrl, telem);
            last_status_ms = now;
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    std::string log_err;
    logger.update_enable(false, g_cfg.log_dir, log_err);
    g_stop = 1;
    if (sensor_thread.joinable()) sensor_thread.join();
    ::close(elrs_fd);
    ::close(fc_fd);
    std::cerr << "[crsf_stack] stopped\n";
    return 0;
}
