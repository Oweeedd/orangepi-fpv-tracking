#pragma once

#include "common.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>

namespace crsfstack {

uint8_t crc8_d5(const uint8_t* data, uint8_t len);
bool validate_crc(const uint8_t* frame, size_t size);
void unpack_channels_8(const uint8_t* payload, uint16_t* channels);
void pack_channels_8(const uint16_t* channels, uint8_t* payload);
std::string frame_type_name(uint8_t type);

struct FrameParser {
    std::array<uint8_t, Config::MAX_FRAME_BUF> buf{};
    uint8_t idx = 0;
    uint8_t len = 0;
    bool sync = false;

    bool feed(uint8_t b, uint8_t* out_frame, size_t& out_size);
};

}
