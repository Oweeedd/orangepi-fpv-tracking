# Киборг убийца

## Порты подключения
### Полётный контроллер
uart2 - tx-8 rx-10
### Приемник expresslrs-crsf
uart6 - tx-11 rx-13

## Изменнеия в конфигурации orangepi 5 ultra

# Существующие интерфейсы
```
orangepi@orangepi5ultra:~$ gpio readall
 +------+-----+----------+--------+---+OPI5-ULTRA+---+--------+----------+-----+------+
 | GPIO | wPi |   Name   |  Mode  | V | Physical | V |  Mode  | Name     | wPi | GPIO |
 +------+-----+----------+--------+---+----++----+---+--------+----------+-----+------+
 |      |     |     3.3V |        |   |  1 || 2  |   |        | 5V       |     |      |
 |   16 |   0 |    SDA.2 |     IN | 1 |  3 || 4  |   |        | 5V       |     |      |
 |   15 |   1 |    SCL.2 |     IN | 1 |  5 || 6  |   |        | GND      |     |      |
 |   39 |   2 |     PWM3 |     IN | 1 |  7 || 8  | 1 | ALT10  | TXD.2    | 3   | 13   |
 |      |     |      GND |        |   |  9 || 10 | 1 | ALT10  | RXD.2    | 4   | 14   |
 |   32 |   5 |    RXD.6 |  ALT10 | 0 | 11 || 12 | 0 | IN     | GPIO4_A6 | 6   | 134  |
 |   33 |   7 |    TXD.6 |  ALT10 | 1 | 13 || 14 |   |        | GND      |     |      |
 |   34 |   8 | GPIO1_A2 |     IN | 0 | 15 || 16 | 0 | IN     | GPIO1_A3 | 9   | 35   |
 |      |     |     3.3V |        |   | 17 || 18 | 0 | IN     | GPIO1_A4 | 10  | 36   |
 |   42 |  11 | SPI0_TXD |     IN | 0 | 19 || 20 |   |        | GND      |     |      |
 |   41 |  12 | SPI0_RXD |     IN | 0 | 21 || 22 | 1 | IN     | GPIO1_B0 | 13  | 40   |
 |   43 |  14 | SPI0_CLK |     IN | 0 | 23 || 24 | 1 | IN     | SPI0_CS0 | 15  | 44   |
 |      |     |      GND |        |   | 25 || 26 | 1 | IN     | SPI0_CS1 | 16  | 45   |
 |  145 |  17 |    SDA.8 |   ALT5 | 1 | 27 || 28 | 1 | ALT5   | SCL.8    | 18  | 144  |
 |  113 |  19 | GPIO3_C1 |     IN | 1 | 29 || 30 |   |        | GND      |     |      |
 |  109 |  20 |  CAN1_RX |     IN | 1 | 31 || 32 | 1 | IN     | GPIO4_B3 | 21  | 139  |
 |  110 |  22 |  CAN1_TX |     IN | 1 | 33 || 34 |   |        | GND      |     |      |
 |  114 |  23 | GPIO3_C2 |     IN | 1 | 35 || 36 | 1 | ALT5   | GPIO4_B7 | 24  | 143  |
 |  135 |  25 | GPIO4_A7 |     IN | 0 | 37 || 38 | 1 | IN     | GPIO3_C0 | 26  | 112  |
 |      |     |      GND |        |   | 39 || 40 | 1 | IN     | GPIO3_B7 | 27  | 111  |
 +------+-----+----------+--------+---+----++----+---+--------+----------+-----+------+
 | GPIO | wPi |   Name   |  Mode  | V | Physical | V |  Mode  | Name     | wPi | GPIO |
 +------+-----+----------+--------+---+OPI5-ULTRA+---+--------+----------+-----+------+

```
# Отключение службы

```
orangepi@orangepi5ultra:~$ systemctl status serial-getty@ttyS2.service
○ serial-getty@ttyS2.service - Serial Getty on ttyS2
     Loaded: loaded (/lib/systemd/system/serial-getty@.service; disabled; preset: enabled)
    Drop-In: /usr/lib/systemd/system/serial-getty@.service.d
             └─10-term.conf, override.conf
     Active: inactive (dead)
       Docs: man:agetty(8)
             man:systemd-getty-generator(8)
             https://0pointer.de/blog/projects/serial-console.html

```

# Проверка uart

```
orangepi@orangepi5ultra:~$ dmesg | grep -i tty
[    2.747371] Kernel command line: root=UUID=<ROOT_UUID> rootwait rootfstype=ext4 splash plymouth.ignore-serial-consoles console=tty1 consoleblank=0 loglevel=1 ubootpart= usb-storage.quirks= cma=128M  cgroup_enable=cpuset cgroup_memory=1 cgroup_enable=memory swapaccount=1
[    3.115010] printk: console [tty1] enabled
[    3.117560] printk: console [tty1] printing thread started
[    3.152756] Registered FIQ tty driver
[    3.853572] feb50000.serial: ttyS2 at MMIO 0xfeb50000 (irq = 40, base_baud = 1500000) is a 16550A
[    3.853999] feb90000.serial: ttyS6 at MMIO 0xfeb90000 (irq = 41, base_baud = 1500000) is a 16550A
[    3.854336] feba0000.serial: ttyS7 at MMIO 0xfeba0000 (irq = 42, base_baud = 1500000) is a 16550A
[    5.963050] systemd[1]: Created slice system-getty.slice - Slice /system/getty.
[    5.967721] systemd[1]: Created slice system-serial\x2dgetty.slice - Slice /system/serial-getty.
[    5.972519] systemd[1]: Expecting device dev-ttyFIQ0.device - /dev/ttyFIQ0...
[    7.257363] systemd[1]: Starting brltty.service - Braille Device Support...
[    7.830244] systemd[1]: Started brltty.service - Braille Device Support.
[    7.831787] input: BRLTTY 6.5 Linux Screen Driver Keyboard as /devices/virtual/input/input19
orangepi@orangepi5ultra:~$ cat /proc/cmdline
root=UUID=<ROOT_UUID> rootwait rootfstype=ext4 splash plymouth.ignore-serial-consoles console=tty1 consoleblank=0 loglevel=1 ubootpart= usb-storage.quirks= cma=128M  cgroup_enable=cpuset cgroup_memory=1 cgroup_enable=memory swapaccount=1

```

# Примерно так должен выглядеть orangepiEnv.txt с включенными uart и свободным от логов uart 2

```
orangepi@orangepi5ultra:/boot$ cat orangepiEnv.txt
verbosity=1
bootlogo=true
extraargs=cma=128M
overlay_prefix=rk3588
fdtfile=rockchip/rk3588-orangepi-5-ultra.dtb
rootdev=UUID=<ROOT_UUID>
rootfstype=ext4
console=display
overlays=uart2-m0 uart6-m1

```

#

```
cat /proc/cmdline
dmesg | grep -i tty
gpio readall
systemctl status serial-getty@ttyS2.service
```

UART2
pin 8 = TXD.2
pin 10 = RXD.2

UART6
pin 11 = RXD.6
pin 13 = TXD.6

Подключение крест-накрест:

RX устройства ← TX Orange Pi
TX устройства → RX Orange Pi
GND общий

приёмник CRSF/ELRS → ttyS6
полётный контроллер → ttyS2

сборка проекта

```
g++ -O2 -std=c++17 crsf_bridge_alt_hold.cpp -lgpiod -lpthread -o crsf_bridge_alt_hold
```
запуск - указывать tty
```
sudo ./crsf_bridge_alt_hold /dev/ttyS6 /dev/ttyS2 --verbose
```
