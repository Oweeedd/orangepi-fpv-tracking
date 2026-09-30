#include "crsf_protocol.h"

#include <cstring>

namespace crsfstack {

uint8_t crc8_d5(const uint8_t* data, uint8_t len) {
    uint8_t crc = 0;
    for (uint8_t i = 0; i < len; ++i) {
        crc ^= data[i];
        for (uint8_t j = 0; j < 8; ++j) {
            crc = (crc & 0x80) ? static_cast<uint8_t>((crc << 1) ^ 0xD5)
                               : static_cast<uint8_t>(crc << 1);
        }
    }
    return crc;
}

bool validate_crc(const uint8_t* frame, size_t size) {
    if (size < 4) return false;
    return crc8_d5(&frame[2], static_cast<uint8_t>(size - 3)) == frame[size - 1];
}

void unpack_channels_8(const uint8_t* payload, uint16_t* channels) {
    for (int i = 0; i < 8; ++i) {
        const int bitpos = 11 * i;
        const int byte_idx = bitpos >> 3;
        const int shift = bitpos & 7;
        const uint32_t raw = payload[byte_idx]
                           | (static_cast<uint32_t>(payload[byte_idx + 1]) << 8)
                           | (static_cast<uint32_t>(payload[byte_idx + 2]) << 16);
        channels[i] = static_cast<uint16_t>((raw >> shift) & 0x7FF);
    }
}

void pack_channels_8(const uint16_t* channels, uint8_t* payload) {
    std::memset(payload, 0, 22);
    for (int i = 0; i < 8; ++i) {
        const uint32_t v = static_cast<uint32_t>(channels[i] & 0x7FF);
        const int bitpos = 11 * i;
        const int byte_idx = bitpos >> 3;
        const int shift = bitpos & 7;
        payload[byte_idx] |= (v << shift) & 0xFF;
        payload[byte_idx + 1] |= (v >> (8 - shift)) & 0xFF;
        if (shift > 5) payload[byte_idx + 2] |= (v >> (16 - shift)) & 0xFF;
    }
}

bool FrameParser::feed(uint8_t b, uint8_t* out_frame, size_t& out_size) {
    if (!sync && b == Config::CRSF_ADDRESS) {
        idx = 0;
        sync = true;
    }
    if (!sync) return false;

    if (idx < buf.size()) {
        buf[idx++] = b;
    } else {
        sync = false;
        idx = 0;
        return false;
    }

    if (idx == 2) {
        len = buf[1];
        if (len > 62) {
            sync = false;
            idx = 0;
            return false;
        }
    }

    if (sync && idx >= static_cast<uint8_t>(len + 2)) {
        out_size = idx;
        std::memcpy(out_frame, buf.data(), out_size);
        sync = false;
        idx = 0;
        return true;
    }

    return false;
}

std::string frame_type_name(uint8_t type) {
    switch (type) {
        case 0x02: return "GPS";
        case 0x07: return "VARIO";
        case 0x08: return "BATTERY";
        case 0x09: return "BARO_ALT";
        case 0x0B: return "HEARTBEAT";
        case 0x0C: return "RPM";
        case 0x0D: return "TEMP";
        case 0x0E: return "VOLTAGES";
        case 0x10: return "VTX";
        case 0x11: return "BAROMETER";
        case 0x12: return "MAG";
        case 0x13: return "ACC_GYRO";
        case 0x14: return "LINK_STATS";
        case 0x16: return "RC_CHANNELS";
        case 0x1E: return "ATTITUDE";
        case 0x21: return "FLIGHT_MODE";
        default: {
            char buf[16];
            std::snprintf(buf, sizeof(buf), "TYPE_0x%02X", type);
            return std::string(buf);
        }
    }
}

}
