**PREEMPT_RT ядро 6.1.99-rt36** на **Orange Pi 5 Ultra**

# Полная инструкция RT-ядро для Orange Pi 5 Ultra

## Исходные условия

Базовая рабочая система:

* плата: **Orange Pi 5 Ultra**
* официальный образ:
  **`Orangepi5ultra_1.0.0_debian_bookworm_desktop_xfce_linux6.1.43.img`**
* установленное штатное ядро:
  **`6.1.43-rockchip-rk3588`**


```
https://drive.google.com/drive/folders/1Lc5alivSsOrAj59ZzfuGNWs-w7V0VxD0

https://mirrors.edge.kernel.org/pub/linux/kernel/projects/

https://mirror.ihost.md/?dir=kernel/projects/rt/6.1/older
```

Проверка базовой системы:

```
uname -a
uname -r
cat /etc/os-release
lsblk
df -h
ip a
dmesg | grep -i -E "tty|uart|serial"
ls /dev/ttyS* /dev/ttyAMA* /dev/ttyFIQ* 2>/dev/null
v4l2-ctl --list-devices
```

Ожидаемо должно быть видно:

* ядро `6.1.43-rockchip-rk3588`
* загрузка с NVMe/SSD
* Ethernet работает
* есть UART-устройства
* система в целом стабильна

Проверка, что штатное ядро **не RT**:

```bash
cat /sys/kernel/realtime 2>/dev/null || echo "no /sys/kernel/realtime"
grep PREEMPT /boot/config-$(uname -r)
zgrep PREEMPT /proc/config.gz 2>/dev/null
```

У нас получилось:

* `/sys/kernel/realtime` отсутствует
* `CONFIG_PREEMPT_VOLUNTARY=y`
* `CONFIG_PREEMPT_RT` отсутствует

---

# 1. Снять baseline и зафиксировать рабочее состояние

```bash
mkdir -p ~/baseline

uname -a > ~/baseline/uname.txt
uname -r > ~/baseline/uname-r.txt
cat /etc/os-release > ~/baseline/os-release.txt
lsblk > ~/baseline/lsblk.txt
df -h > ~/baseline/df-h.txt
ip a > ~/baseline/ip-a.txt
lsmod > ~/baseline/lsmod.txt
dmesg -T > ~/baseline/dmesg.txt

ls /dev/ttyS* /dev/ttyAMA* /dev/ttyFIQ* 2>/dev/null > ~/baseline/tty.txt
v4l2-ctl --list-devices > ~/baseline/v4l2.txt 2>&1

ls -lah /boot > ~/baseline/boot-ls.txt
find /boot -maxdepth 3 -type f | sort > ~/baseline/boot-tree.txt
cat /proc/cmdline > ~/baseline/proc-cmdline.txt
```

---

# 2. Проверить схему загрузки

если загрузка идёт не через `extlinux`, а через `boot.scr`.

Проверка:

```bash
find /boot -maxdepth 3 -type f | grep -E 'extlinux|boot.scr|orangepiEnv|armbianEnv|grub'
cat /boot/boot.cmd
cat /boot/orangepiEnv.txt
```

Фактически было так:

* `/boot/boot.scr`
* `/boot/orangepiEnv.txt`

И в `boot.cmd` жёстко использовались:

* `/boot/Image`
* `/boot/uInitrd`
* `/boot/dtb/${fdtfile}`

Это важно: для RT пришлось **подменять именно эти файлы**, а не добавлять отдельный пункт меню.

---

# 3. Установить зависимости для сборки и тестов

```bash
sudo apt update
sudo apt install -y \
  git bc bison flex build-essential make gcc g++ \
  libssl-dev libncurses-dev libelf-dev dwarves pahole \
  rsync cpio kmod u-boot-tools device-tree-compiler \
  fakeroot python3 python3-pip \
  usbutils pciutils i2c-tools screen tmux htop curl wget \
  rt-tests stress-ng ethtool
```

---

# 4. Скачать исходники Orange Pi и build-репозиторий


* RT-ветка 5.10 — как запасной вариант
* `orangepi-build`
* потом нужная 6.1 ветка

Команды:

```bash
cd ~

git clone --depth=1 --branch=orange-pi-5.10-rk35xx-rt https://github.com/orangepi-xunlong/linux-orangepi.git
git clone --depth=1 --branch=next https://github.com/orangepi-xunlong/orangepi-build.git
git clone --depth=1 --branch=orange-pi-6.1-rk35xx https://github.com/orangepi-xunlong/linux-orangepi.git linux-orangepi-6.1
```

Проверка:

```bash
cd ~/linux-orangepi-6.1
git rev-parse --abbrev-ref HEAD
make kernelversion
```

У нас получилось:

* ветка: `orange-pi-6.1-rk35xx`
* версия дерева: `6.1.99`

---

# 5. Подготовить RT-патч

Были два патча:

* `patch-6.1.43-rt14.patch`
* `patch-6.1.99-rt36.patch`

Проверка показала:

```bash
cd ~/linux-orangepi-6.1
git apply --check ~/patch-6.1.99-rt36.patch
git apply --check ~/patch-6.1.43-rt14.patch
```

Результат:

* `6.1.43-rt14` оказался повреждён: `corrupt patch`
* `6.1.99-rt36` почти подошёл, но с несколькими конфликтами

Именно поэтому был выбран путь:

**Orange Pi 6.1 BSP (`orange-pi-6.1-rk35xx`) + RT patch `patch-6.1.99-rt36.patch`**

---

# 6. Создать рабочую копию дерева и наложить патч с reject

Чтобы не испортить чистое дерево:

```bash
cd ~
cp -a linux-orangepi-6.1 linux-orangepi-6.1-rtwork
cd ~/linux-orangepi-6.1-rtwork
```

Наложение патча:

```bash
git apply --reject --whitespace=fix ~/patch-6.1.99-rt36.patch 2>&1 | tee ~/rt-apply-reject.log
find . -name '*.rej' -o -name '*.orig'
```

Почти всё применилось автоматически, осталось 3 reject-файла:

* `kernel/watchdog.c.rej`
* `drivers/tty/serial/8250/8250.h.rej`
* `drivers/tty/serial/8250/8250_port.c.rej`

---

# 7. Внести ручные правки

## 7.1 Правка `drivers/tty/serial/8250/8250.h`

Открыть файл:

```bash
nano drivers/tty/serial/8250/8250.h
```

После блока:

```c
static inline void serial_dl_write(struct uart_8250_port *up, int value)
{
	up->dl_write(up, value);
}
```

добавить:

```c
static inline int serial8250_in_IER(struct uart_8250_port *up)
{
	struct uart_port *port = &up->port;
	unsigned long flags;
	bool is_console;
	int ier;

	is_console = uart_console(port);

	if (is_console)
		printk_cpu_sync_get_irqsave(flags);

	ier = serial_in(up, UART_IER);

	if (is_console)
		printk_cpu_sync_put_irqrestore(flags);

	return ier;
}

static inline void serial8250_set_IER(struct uart_8250_port *up, int ier)
{
	struct uart_port *port = &up->port;
	unsigned long flags;
	bool is_console;

	is_console = uart_console(port);

	if (is_console)
		printk_cpu_sync_get_irqsave(flags);

	serial_out(up, UART_IER, ier);

	if (is_console)
		printk_cpu_sync_put_irqrestore(flags);
}
```

Далее заменить в двух местах:

```c
serial_out(up, UART_IER, up->ier);
```

на:

```c
serial8250_set_IER(up, up->ier);
```

Важно: rockchip-специфические строки с `UART_IER_PTIME` не трогать.

---

## 7.2 Правка `drivers/tty/serial/8250/8250_port.c`

Открыть:

```bash
nano drivers/tty/serial/8250/8250_port.c
```

### Первая замена

В `serial8250_do_startup()` заменить:

```c
if (uart_console(port))
```

на:

```c
if (is_console)
```


```c
#ifdef CONFIG_ARCH_ROCKCHIP
	msg = "failed to request DMA, use interrupt mode";
#else
	msg = "failed to request DMA";
#endif
```

Итоговый блок должен остаться логически целым:

```c
if (up->dma) {
	const char *msg = NULL;

	if (is_console)
		msg = "forbid DMA for kernel console";
	else if (serial8250_request_dma(up))
#ifdef CONFIG_ARCH_ROCKCHIP
		msg = "failed to request DMA, use interrupt mode";
#else
		msg = "failed to request DMA";
#endif

	if (msg) {
		dev_warn_ratelimited(port->dev, "%s\n", msg);
		up->dma = NULL;
	}
}
```

### Вторая замена

В `serial8250_do_set_termios()` заменить:

```c
serial_port_out(port, UART_IER, up->ier);
```

на:

```c
serial8250_set_IER(up, up->ier);
```

---

## 7.3 Правка `kernel/watchdog.c`

Открыть:

```bash
nano kernel/watchdog.c
```

В `watchdog_timer_fn()` найти блок:

```c
add_taint(TAINT_SOFTLOCKUP, LOCKDEP_STILL_OK);
if (softlockup_panic)
	panic("softlockup: hung tasks");
```

И добавить после него:

```c
printk_prefer_direct_exit();
```

---

# 8. Удалить `.rej` и проверить, что ручные правки на месте

```bash
rm -f drivers/tty/serial/8250/8250.h.rej
rm -f drivers/tty/serial/8250/8250_port.c.rej
rm -f kernel/watchdog.c.rej
find . -name '*.rej'
```

Проверки:

```bash
grep -R "printk_prefer_direct_exit" -n kernel/watchdog.c
grep -R "serial8250_set_IER" -n drivers/tty/serial/8250/8250.h drivers/tty/serial/8250/8250_port.c
ls -l localversion-rt
```

Убедиться, что:

* `.rej` больше нет
* `printk_prefer_direct_exit` есть
* `serial8250_set_IER` используется
* `localversion-rt` присутствует

---

# 9. Взять конфиг от штатного ядра и включить RT

Использовать конфиг текущего рабочего ядра:

```bash
cp /boot/config-6.1.43-rockchip-rk3588 .config
make olddefconfig
make menuconfig
```

В `menuconfig` включить:

* `General setup`
* `Preemption Model`
* выбрать **Fully Preemptible Kernel (Real-Time)**

Проверка:

```bash
grep -E 'CONFIG_PREEMPT_RT|CONFIG_PREEMPT|CONFIG_HIGH_RES_TIMERS|CONFIG_HZ=' .config
grep -E 'CONFIG_NET_VENDOR_MOTORCOMM|CONFIG_FUXI' .config
```

У нас получилось:

* `CONFIG_PREEMPT_RT=y`
* `CONFIG_HIGH_RES_TIMERS=y`

`CONFIG_FUXI` не включали, потому что Ethernet использовал не этот драйвер.

---

# 10. Проверить драйвер Ethernet перед окончательной сборкой

Проверка:

```bash
sudo ethtool -i enP3p49s0
```

Результат у нас был:

* драйвер: `r8169`

Значит:

* `CONFIG_FUXI` не нужен
* пересобирать ради него не надо

---

# 11. Собрать ядро

Сборка:

```bash
cd ~/linux-orangepi-6.1-rtwork
make -j$(nproc) Image modules dtbs 2>&1 | tee ~/rt-kernel-build.log
```

Проверки успешной сборки:

```bash
make kernelrelease
ls -lh arch/arm64/boot/Image
ls -lh arch/arm64/boot/dts/rockchip/rk3588-orangepi-5-ultra.dtb
tail -n 30 ~/rt-kernel-build.log
```

У нас получилось:

* `make kernelrelease` → `6.1.99-rt36`
* `Image` существует
* `rk3588-orangepi-5-ultra.dtb` существует
* в конце лога нет `Error`

Warnings по DTS и Realtek Wi-Fi были, но сборку они не ломали.

---

# 12. Установить модули нового ядра

```bash
sudo make modules_install
```

Проверка:

```bash
ls /lib/modules | grep 6.1.99-rt36
```

Каталог нового ядра должен появиться.

---

# 13. Подготовить boot-файлы нового ядра

Скопировать служебные файлы:

```bash
sudo cp -v .config /boot/config-6.1.99-rt36
sudo cp -v System.map /boot/System.map-6.1.99-rt36
sudo cp -v arch/arm64/boot/Image /boot/vmlinuz-6.1.99-rt36
```

Создать initramfs:

```bash
sudo update-initramfs -c -k 6.1.99-rt36
ls -lh /boot/initrd.img-6.1.99-rt36
```

Создать `uInitrd` для U-Boot:

```bash
sudo mkimage -A arm64 -O linux -T ramdisk -C none \
  -a 0 -e 0 \
  -n "initramfs-6.1.99-rt36" \
  -d /boot/initrd.img-6.1.99-rt36 \
  /boot/uInitrd-6.1.99-rt36
```

Проверка:

```bash
ls -lh /boot/uInitrd-6.1.99-rt36
```

---

# 14. Сделать резервные копии перед переключением

Полный бэкап `/boot`:

```bash
sudo mkdir -p /boot/backup-stock
sudo cp -av /boot/Image /boot/backup-stock/
sudo cp -av /boot/uInitrd /boot/backup-stock/
sudo cp -av /boot/initrd.img-$(uname -r) /boot/backup-stock/
sudo cp -av /boot/vmlinuz-$(uname -r) /boot/backup-stock/
sudo cp -av /boot/config-$(uname -r) /boot/backup-stock/
sudo cp -av /boot/System.map-$(uname -r) /boot/backup-stock/
sudo cp -av /boot/boot.scr /boot/backup-stock/
sudo cp -av /boot/boot.cmd /boot/backup-stock/
sudo cp -av /boot/orangepiEnv.txt /boot/backup-stock/
sudo cp -av /boot/dtb /boot/backup-stock/ 2>/dev/null || true
```

И отдельно именованные копии:

```bash
sudo cp -av /boot/Image /boot/Image-stock
sudo cp -av /boot/uInitrd /boot/uInitrd-stock
sudo cp -av /boot/dtb/rockchip/rk3588-orangepi-5-ultra.dtb /boot/dtb/rockchip/rk3588-orangepi-5-ultra.dtb-stock
```

эти файлы потом позволяют быстро откатиться.

---

# 15. Подменить загрузочные файлы на RT

Так как `boot.cmd` жёстко грузит `Image` и `uInitrd`, пришлось заменить именно их.

Подмена:

```bash
sudo cp -v ~/linux-orangepi-6.1-rtwork/arch/arm64/boot/Image /boot/Image
sudo cp -v /boot/uInitrd-6.1.99-rt36 /boot/uInitrd
sudo cp -v ~/linux-orangepi-6.1-rtwork/arch/arm64/boot/dts/rockchip/rk3588-orangepi-5-ultra.dtb /boot/dtb/rockchip/rk3588-orangepi-5-ultra.dtb
sync
```

После этого:

```bash
sudo reboot
```

---

# 16. Проверить, что RT-ядро реально загрузилось

После ребута:

```bash
uname -r
uname -a
cat /sys/kernel/realtime 2>/dev/null || echo "no realtime flag"
ip a
sudo ethtool -i enP3p49s0
ls /dev/ttyS* /dev/ttyAMA* /dev/ttyFIQ* 2>/dev/null
dmesg -T | tail -n 100
```

Успешный результат:

* `uname -r` → `6.1.99-rt36`
* `uname -a` содержит `PREEMPT_RT`
* `/sys/kernel/realtime` → `1`
* Ethernet жив
* `r8169` работает уже на RT-ядре
* UART-устройства есть

После успеха можно дополнительно сохранить рабочие RT boot-файлы:

```bash
sudo cp -av /boot/Image /boot/Image-rt-working
sudo cp -av /boot/uInitrd /boot/uInitrd-rt-working
```

---

# 17. Исправить права/лимиты для запуска RT-тестов

После первой загрузки RT оказалось, что даже root не мог выполнить `chrt` и `cyclictest`, потому что:

* capabilities были нормальные
* но `RLIMIT_RTPRIO=0`

Проверка:

```bash
su
ulimit -r
ulimit -l
grep -E 'Cap(Prm|Eff|Bnd)' /proc/self/status
```

Исправление: создать файл limits:

```bash
cat >/etc/security/limits.d/99-realtime.conf <<'EOF'
* soft rtprio 99
* hard rtprio 99
* soft memlock unlimited
* hard memlock unlimited
* soft nice -20
* hard nice -20
root soft rtprio 99
root hard rtprio 99
root soft memlock unlimited
root hard memlock unlimited
root soft nice -20
root hard nice -20
EOF
```

Проверить PAM:

```bash
grep pam_limits /etc/pam.d/common-session /etc/pam.d/common-session-noninteractive /etc/pam.d/su /etc/pam.d/sshd
```

После этого нужно было **полностью переподключиться по SSH**, чтобы лимиты применились.

Проверка:

```bash
ulimit -r
ulimit -l
sudo -i
ulimit -r
ulimit -l
```

---

# 18. Прогнать `cyclictest`

Установить пакет:

```bash
sudo apt update
sudo apt install -y rt-tests stress-ng
```

Запуск без нагрузки:

```bash
cyclictest -m -S -p95 -i1000 -q
```

Запуск под нагрузкой:

```bash
stress-ng --cpu 8 --io 4 --vm 2 --vm-bytes 512M --timeout 60s &
cyclictest -m -S -p95 -i1000 -q
```

результаты:

Без нагрузки:

* `Avg` примерно 6–15 мкс
* `Max` примерно 59–196 мкс

Под нагрузкой:

* `Avg` примерно 3–8 мкс
* `Max` примерно 18–126 мкс

Это хороший результат для PREEMPT_RT на этой платформе.

---

# Как понять, что всё успешно

Набор проверок:

```bash
uname -r
uname -a
cat /sys/kernel/realtime
sudo ethtool -i enP3p49s0
ls /dev/ttyS* /dev/ttyAMA* /dev/ttyFIQ* 2>/dev/null
cyclictest -m -S -p95 -i1000 -q
```

Успех — это когда:

* ядро `6.1.99-rt36`
* есть `PREEMPT_RT`
* `/sys/kernel/realtime = 1`
* сеть жива
* UART жив
* `cyclictest` работает и не даёт миллисекундных провалов

---

# Как откатиться на старое ядро

Если новое ядро не загрузилось, сломалась сеть, не стартует система или просто нужен возврат на штатное ядро, откат делается заменой boot-файлов обратно.

## Вариант отката из рабочей системы

Если система ещё грузится:

```bash
sudo cp -av /boot/Image-stock /boot/Image
sudo cp -av /boot/uInitrd-stock /boot/uInitrd
sudo cp -av /boot/dtb/rockchip/rk3588-orangepi-5-ultra.dtb-stock /boot/dtb/rockchip/rk3588-orangepi-5-ultra.dtb
sync
sudo reboot
```

## Вариант отката с другого Linux/через rescue

Если плата не грузится вообще:

1. подключить SSD к другому Linux
2. смонтировать `/boot`
3. вернуть файлы:

```bash
/boot/Image-stock -> /boot/Image
/boot/uInitrd-stock -> /boot/uInitrd
/boot/dtb/rockchip/rk3588-orangepi-5-ultra.dtb-stock -> /boot/dtb/rockchip/rk3588-orangepi-5-ultra.dtb
```

4. безопасно размонтировать и загрузить плату снова

## Дополнительный вариант отката из backup-каталога

Если именованные `*-stock` отсутствуют, можно брать из `/boot/backup-stock/`.

---

# Что в итоге получилось

Финальное рабочее состояние:

* базовая система: Orange Pi Bookworm
* RT-ядро: **`6.1.99-rt36`**
* статус RT:

  * `PREEMPT_RT`
  * `/sys/kernel/realtime = 1`
* Ethernet:

  * драйвер `r8169`
  * работает на RT-ядре
* UART:

  * устройства на месте
* RT latency:

  * успешные тесты `cyclictest`

---

# Что полезно сохранить отдельно

Рекомендую сохранить в отдельную папку или репозиторий:

* `~/linux-orangepi-6.1-rtwork`
* `~/patch-6.1.99-rt36.patch`
* итоговый `.config`
* список ручных правок
* текущие файлы:

  * `/boot/Image`
  * `/boot/uInitrd`
  * `/boot/config-6.1.99-rt36`
  * `/boot/initrd.img-6.1.99-rt36`

---

# Короткий итог


* поднял официальный Orange Pi Debian образ
* проверил базовое ядро и периферию
* взял правильную Orange Pi BSP ветку `orange-pi-6.1-rk35xx`
* наложил `patch-6.1.99-rt36`
* вручную исправил 3 конфликтующих места
* собрал `6.1.99-rt36`
* установил модули и boot-файлы
* сделал безопасный бэкап
* загрузился в PREEMPT_RT
* подтвердил это через `uname`, `/sys/kernel/realtime` и `cyclictest`


