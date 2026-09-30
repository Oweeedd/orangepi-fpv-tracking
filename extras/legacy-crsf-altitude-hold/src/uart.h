#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace crsfstack {

int open_uart(const std::string& dev);
bool write_full(int fd, const uint8_t* data, size_t len);

}
