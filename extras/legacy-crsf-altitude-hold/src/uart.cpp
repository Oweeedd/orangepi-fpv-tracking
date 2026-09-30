#include "uart.h"
#include "common.h"

#include <asm/ioctls.h>
#include <asm/termbits.h>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <sys/ioctl.h>
#include <unistd.h>

namespace crsfstack {

bool write_full(int fd, const uint8_t* data, size_t len) {
    size_t sent = 0;
    while (sent < len) {
        const ssize_t n = ::write(fd, data + sent, len - sent);
        if (n < 0) {
            if (errno == EINTR) continue;
            std::perror("write");
            return false;
        }
        sent += static_cast<size_t>(n);
    }
    return true;
}

int open_uart(const std::string& dev) {
    const int fd = ::open(dev.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0) {
        std::perror(("open " + dev).c_str());
        return -1;
    }

    struct termios2 tio {};
    if (ioctl(fd, TCGETS2, &tio) != 0) {
        std::perror("ioctl(TCGETS2)");
        ::close(fd);
        return -1;
    }

    tio.c_cflag &= ~CBAUD;
    tio.c_cflag |= BOTHER | CS8 | CLOCAL | CREAD;
    tio.c_cflag &= ~PARENB;
    tio.c_cflag &= ~CSTOPB;
    tio.c_cflag &= ~CRTSCTS;
    tio.c_iflag = 0;
    tio.c_oflag = 0;
    tio.c_lflag = 0;
    tio.c_line = 0;
    std::memset(tio.c_cc, 0, sizeof(tio.c_cc));
    tio.c_cc[VMIN] = 0;
    tio.c_cc[VTIME] = 0;
    tio.c_ispeed = Config::CRSF_BAUD;
    tio.c_ospeed = Config::CRSF_BAUD;

    if (ioctl(fd, TCSETS2, &tio) != 0) {
        std::perror("ioctl(TCSETS2)");
        ::close(fd);
        return -1;
    }

    if (ioctl(fd, TCFLSH, 2) != 0) {
        std::perror("ioctl(TCFLSH)");
    }

    return fd;
}

}
