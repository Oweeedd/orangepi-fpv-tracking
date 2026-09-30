#!/usr/bin/env python3
import sys
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt


def main():
    if len(sys.argv) < 2:
        print("usage: plot_log.py <csv_log>")
        return 1
    path = Path(sys.argv[1])
    df = pd.read_csv(path)
    if df.empty:
        print("empty log")
        return 1

    t0 = df["time_ms"].iloc[0]
    ts = (df["time_ms"] - t0) / 1000.0

    plt.figure(figsize=(12, 6))
    plt.plot(ts, df["sensor_cm"], label="sensor_cm")
    plt.plot(ts, df["target_cm"], label="target_cm")
    plt.xlabel("time, s")
    plt.ylabel("height, cm")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    plt.figure(figsize=(12, 6))
    plt.plot(ts, df["live_thr"], label="live_thr")
    plt.plot(ts, df["out_thr"], label="out_thr")
    plt.plot(ts, df["corr"], label="corr")
    plt.xlabel("time, s")
    plt.ylabel("throttle / correction")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    plt.figure(figsize=(12, 6))
    plt.plot(ts, df["vertical_speed_cms"], label="vertical_speed_cms")
    if "battery_v" in df.columns:
        plt.plot(ts, df["battery_v"], label="battery_v")
    plt.xlabel("time, s")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
