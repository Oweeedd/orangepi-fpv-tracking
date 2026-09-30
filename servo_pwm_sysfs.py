from dataclasses import dataclass
from pathlib import Path


@dataclass
class SysfsServoConfig:
    enabled: bool = False

    pwmchip: str = "/sys/class/pwm/pwmchip1"
    channel: int = 0

    period_ns: int = 20_000_000

    min_us: int = 700
    max_us: int = 2300

    down_angle: float = 0.0
    mid_angle: float = 45.0
    front_angle: float = 90.0

    min_angle: float = 0.0
    max_angle: float = 180.0

    invert: bool = False


class SysfsServo:
    def __init__(self, cfg: SysfsServoConfig):
        self.cfg = cfg
        self.enabled = bool(cfg.enabled)

        self.pwmchip = Path(cfg.pwmchip)
        self.channel = int(cfg.channel)
        self.pwm_path = self.pwmchip / f"pwm{self.channel}"

        self.current_angle = None
        self.current_name = "UNKNOWN"

        if not self.enabled:
            print("[SERVO-PWM] disabled")
            return

        print(f"[SERVO-PWM] pwmchip={self.pwmchip}, channel={self.channel}")

        self._check_ready()

        self.polarity = self._read_text("polarity")
        self.period_ns = int(self._read_text("period"))

        print(f"[SERVO-PWM] polarity={self.polarity}, period={self.period_ns}")
        print("[SERVO-PWM] initialized")

    def _read_text(self, name: str) -> str:
        return (self.pwm_path / name).read_text().strip()

    def _write(self, name: str, value: str):
        path = self.pwm_path / name

        try:
            path.write_text(value)
        except PermissionError:
            raise PermissionError(
                f"Нет прав на {path}. "
                f"Выполни: sudo ./scripts/prepare_servo_pwm.sh"
            )

    def _check_ready(self):
        if not self.pwm_path.exists():
            raise RuntimeError(
                f"{self.pwm_path} не существует. "
                f"Сначала выполни sudo ./scripts/prepare_servo_pwm.sh"
            )

        try:
            period = int(self._read_text("period"))
            enable = int(self._read_text("enable"))
            polarity = self._read_text("polarity")
        except Exception as e:
            raise RuntimeError(f"Не удалось прочитать PWM: {e}")

        if period != int(self.cfg.period_ns):
            raise RuntimeError(
                f"PWM period={period}, а нужно {self.cfg.period_ns}. "
                f"Выполни sudo ./scripts/prepare_servo_pwm.sh"
            )

        if enable != 1:
            raise RuntimeError(
                "PWM выключен. Выполни sudo ./scripts/prepare_servo_pwm.sh"
            )

        if polarity not in ("normal", "inversed"):
            raise RuntimeError(f"Неизвестная polarity: {polarity}")

    @staticmethod
    def clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    def angle_to_us(self, angle: float) -> int:
        angle = self.clamp(angle, self.cfg.min_angle, self.cfg.max_angle)

        if self.cfg.invert:
            angle = self.cfg.max_angle - (angle - self.cfg.min_angle)

        span_angle = self.cfg.max_angle - self.cfg.min_angle
        span_us = self.cfg.max_us - self.cfg.min_us

        ratio = (angle - self.cfg.min_angle) / span_angle
        pulse_us = self.cfg.min_us + ratio * span_us

        return int(round(pulse_us))

    def pulse_us_to_duty_ns(self, pulse_us: int) -> int:
        pulse_ns = int(pulse_us) * 1000

        if self.polarity == "inversed":
            return int(self.period_ns - pulse_ns)

        return pulse_ns

    def set_angle(self, angle: float, name: str = ""):
        if not self.enabled:
            return

        angle = self.clamp(angle, self.cfg.min_angle, self.cfg.max_angle)

        pulse_us = self.angle_to_us(angle)
        duty_ns = self.pulse_us_to_duty_ns(pulse_us)

        self._write("duty_cycle", str(duty_ns))

        self.current_angle = angle
        if name:
            self.current_name = name

    def set_aux3_position(self, aux3_us: int):
        if not self.enabled:
            return

        if aux3_us < 1300:
            angle = self.cfg.down_angle
            name = "DOWN"
        elif aux3_us < 1700:
            angle = self.cfg.mid_angle
            name = "MID"
        else:
            angle = self.cfg.front_angle
            name = "FRONT"

        if self.current_angle != angle:
            print(f"[SERVO-PWM] AUX3={aux3_us} -> {name} angle={angle}")

        self.set_angle(angle, name=name)

    def manual_position(self, pos: int):
        if pos == 0:
            self.set_angle(self.cfg.down_angle, name="DOWN")
        elif pos == 1:
            self.set_angle(self.cfg.mid_angle, name="MID")
        elif pos == 2:
            self.set_angle(self.cfg.front_angle, name="FRONT")

    def disable(self):
        if not self.enabled:
            return

        try:
            self._write("enable", "0")
        except Exception:
            pass
