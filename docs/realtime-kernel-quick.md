# RT.md — сборка и упаковка PREEMPT_RT ядра для Orange Pi 5 Ultra (RK3588)

## Цель

Получить:

* RT-ядро (`PREEMPT_RT`)
* deploy-папку
* `.deb` пакеты (как у Armbian / Debian)
* возможность установки:

  * вручную
  * через `.deb`
  * через скрипт

---

# 1. Подготовка окружения (на ПК)

```bash
sudo apt update
sudo apt install -y \
  git build-essential bc bison flex libssl-dev libelf-dev \
  crossbuild-essential-arm64 \
  u-boot-tools \
  fakeroot dpkg-dev
```

---

# 2. Исходники ядра

```bash
mkdir -p ~/opi5rt/src
cd ~/opi5rt/src

git clone https://github.com/orangepi-xunlong/linux-orangepi.git -b orange-pi-6.1-rk35xx linux-orangepi-6.1
cp -r linux-orangepi-6.1 linux-orangepi-6.1-rtwork
cd linux-orangepi-6.1-rtwork
```

```
https://drive.google.com/drive/folders/1Lc5alivSsOrAj59ZzfuGNWs-w7V0VxD0

https://mirrors.edge.kernel.org/pub/linux/kernel/projects/

https://mirror.ihost.md/?dir=kernel/projects/rt/6.1/older
```


---

# 3. Применение RT patch

```bash
patch -p1 < ~/opi5rt/patch-6.1.99-rt36.patch
```

Проверка:

```bash
find . -name '*.rej'
```

если есть `.rej` — править руками

---

# 4. Конфигурация ядра

Базовый конфиг:

```bash
cp ~/opi5rt/config-6.1.43-rockchip-rk3588 .config
```

Обновление:

```bash
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
```

---

## ВАЖНО 

При первом `make` система может спросить кучу опций, это нормально.

### КРИТИЧНО:

* выбрать:

```
PREEMPT_RT = YES
NO_HZ_IDLE = YES
HIGH_RES_TIMERS = YES
```

---

## Проверка конфига

```bash
grep -E 'CONFIG_PREEMPT_RT|CONFIG_PREEMPT|CONFIG_HIGH_RES_TIMERS|CONFIG_HZ=' .config
```

Должно быть:

```text
CONFIG_PREEMPT_RT=y
CONFIG_HIGH_RES_TIMERS=y
CONFIG_HZ=300
```

---

# 5. Сборка ядра

```bash
make -j$(nproc) ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- Image modules dtbs
```

---

# 6. Проверка результата

```bash
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- kernelrelease
```

ожидаем:

```
6.1.99-rt36
```

---

# 7. Подготовка deploy-папки

```bash
mkdir -p ~/opi5rt/deploy/kernel-6.1.99-rt36/{boot,modules}

cp arch/arm64/boot/Image ~/opi5rt/deploy/kernel-6.1.99-rt36/boot/
cp arch/arm64/boot/dts/rockchip/rk3588-orangepi-5-ultra.dtb ~/opi5rt/deploy/kernel-6.1.99-rt36/boot/
cp System.map ~/opi5rt/deploy/kernel-6.1.99-rt36/boot/System.map-6.1.99-rt36
cp .config ~/opi5rt/deploy/kernel-6.1.99-rt36/boot/config-6.1.99-rt36
```

Модули:

```bash
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- INSTALL_MOD_PATH=~/opi5rt/deploy/kernel-6.1.99-rt36/modules modules_install
```

---

# 8. Установка на Orange Pi (ручная)

```bash
scp -r kernel-6.1.99-rt36 orangepi@board:~
```

На плате:

```bash
cd ~/kernel-6.1.99-rt36

sudo cp boot/Image /boot/vmlinuz-6.1.99-rt36
sudo cp boot/System.map-6.1.99-rt36 /boot/
sudo cp boot/config-6.1.99-rt36 /boot/
sudo cp boot/rk3588-orangepi-5-ultra.dtb /boot/dtb/rockchip/

sudo cp -r modules/6.1.99-rt36 /lib/modules/
sudo depmod -a
```

initramfs:

```bash
sudo update-initramfs -c -k 6.1.99-rt36
sudo mkimage -A arm64 -T ramdisk -C none \
  -d /boot/initrd.img-6.1.99-rt36 \
  /boot/uInitrd-6.1.99-rt36
```

---

# 9. Проверка RT

```bash
uname -r
cat /sys/kernel/realtime
```

должно быть:

```
1
```

---

# 10. Создание .deb пакетов

## Структура:

```bash
mkdir -p ~/opi5rt/pkgbuild/linux-image/DEBIAN
mkdir -p ~/opi5rt/pkgbuild/linux-image/boot
mkdir -p ~/opi5rt/pkgbuild/linux-image/lib/modules
```

---

## Копируем файлы:

```bash
cp deploy/kernel-6.1.99-rt36/boot/* ~/opi5rt/pkgbuild/linux-image/boot/
cp -r deploy/kernel-6.1.99-rt36/modules/6.1.99-rt36 ~/opi5rt/pkgbuild/linux-image/lib/modules/
```

---

## control файл

```bash
nano ~/opi5rt/pkgbuild/linux-image/DEBIAN/control
```

```text
Package: linux-image-6.1.99-rt36-opi5u
Version: 1.0
Section: kernel
Priority: optional
Architecture: arm64
Maintainer: you <local@rt>
Depends: initramfs-tools, u-boot-tools
Description: RT kernel for Orange Pi 5 Ultra
```

---

## postinst (ВАЖНО)

```bash
nano ~/opi5rt/pkgbuild/linux-image/DEBIAN/postinst
chmod +x ...
```

```bash
#!/bin/sh
set -e

depmod -a 6.1.99-rt36
update-initramfs -c -k 6.1.99-rt36

mkimage -A arm64 -T ramdisk -C none \
 -d /boot/initrd.img-6.1.99-rt36 \
 /boot/uInitrd-6.1.99-rt36

echo "RT kernel installed"
```

---

## Сборка пакета

```bash
dpkg-deb --build ~/opi5rt/pkgbuild/linux-image
```

---

# 11. Установка .deb

```bash
sudo dpkg -i linux-image-6.1.99-rt36-opi5u.deb
```

---

# 12. Итог 

собралось RT ядро
деплой вручную
install-скрипт
делать .deb пакеты (как в Armbian)

---

# Важные моменты

### 1. menuconfig не открылся

причина: маленький терминал
✔ решение:

```bash
export TERM=xterm
resize
```

---

### 2. make kernelrelease запустил конфиг

это нормально (oldconfig)

---

### 3. x86 опции в ARM

игнорируем, если не ломает сборку

---

### 4. RT активен только если:

```bash
cat /sys/kernel/realtime = 1
```

---
