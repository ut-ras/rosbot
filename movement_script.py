#!/usr/bin/env python3
"""
WASD Rover Controller — Jetson (Refactored)

Features:
  - True differential steering (W/S + A/D blending)
  - Deadman switch (keys expire if not refreshed)
  - Robust multi-key handling (no OS repeat dependency)

Controls:
  W / S     — forward / back
  A / D     — turn left / right
  Space     — emergency stop
  Q / Esc   — quit (sends stop first)

Usage:
    python3 wasd_rover.py [port] [baud]
"""

import sys
import os
import time
import termios
import tty
import select
import threading
import serial

# ── Config ────────────────────────────────────────────────────────────
DEFAULT_PORT = "/dev/ttyTHS1"
DEFAULT_BAUD = 115200

SPEED = 0.5

# Deadman timeout (seconds)
KEY_TIMEOUT = 0.10

# ─────────────────────────────────────────────────────────────────────

def make_cmd(L, R):
    return '{{"T":1,"L":{:.2f},"R":{:.2f}}}'.format(L, R)

STOP_CMD = '{"T":1,"L":0,"R":0}'

# ── Differential Drive ────────────────────────────────────────────────

def compute_lr(keys):
    forward = 0.0
    if "w" in keys:
        forward += 1.0
    if "s" in keys:
        forward -= 1.0

    turn = 0.0
    if "d" in keys:
        turn += 1.0
    if "a" in keys:
        turn -= 1.0

    left  = forward + turn
    right = forward - turn

    # Normalize to preserve ratios
    max_mag = max(1.0, abs(left), abs(right))
    left  /= max_mag
    right /= max_mag

    return left * SPEED, right * SPEED

# ── Serial helpers ────────────────────────────────────────────────────

def send(ser, cmd):
    ser.write((cmd + "\n").encode("utf-8"))

def reader_thread(ser):
    while True:
        try:
            if ser.in_waiting:
                line = ser.readline().decode("utf-8", errors="replace").strip()
                if line:
                    print(f"\r  ← {line}")
        except Exception:
            break
        time.sleep(0.02)

# ── Raw stdin helpers ─────────────────────────────────────────────────

def set_raw(fd):
    old = termios.tcgetattr(fd)
    tty.setraw(fd)
    return old

def restore(fd, old):
    termios.tcsetattr(fd, termios.TCSADRAIN, old)

def read_char_nonblocking(fd, timeout=0.02):
    r, _, _ = select.select([fd], [], [], timeout)
    if r:
        return os.read(fd, 1).decode("utf-8", errors="ignore")
    return None

# ── Main ──────────────────────────────────────────────────────────────

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PORT
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BAUD

    print(f"\n  WASD Rover Controller (Refactored)")
    print(f"  Connecting to {port} @ {baud} baud…\n")

    try:
        ser = serial.Serial(port, baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"  [!] Could not open {port}: {e}")
        sys.exit(1)

    time.sleep(2)
    ser.reset_input_buffer()
    threading.Thread(target=reader_thread, args=(ser,), daemon=True).start()

    print("  Connected.")
    print(f"  Speed: {SPEED}")
    print(f"  Deadman timeout: {KEY_TIMEOUT}s")
    print("  W/A/S/D = move   Space = stop   Q = quit\n")

    fd       = sys.stdin.fileno()
    old_term = set_raw(fd)

    MOVE_KEYS = {"w", "a", "s", "d"}

    active_keys = {}   # key -> last_seen timestamp
    last_cmd = None

    def refresh():
        nonlocal last_cmd
        keys = set(active_keys.keys())

        cmd = make_cmd(*compute_lr(keys)) if keys else STOP_CMD

        if cmd != last_cmd:
            send(ser, cmd)
            last_cmd = cmd
            print(f"\r  → {cmd}   keys={sorted(keys) or ['none']}      ",
                  end="", flush=True)

    def clear_all():
        nonlocal last_cmd
        active_keys.clear()
        send(ser, STOP_CMD)
        last_cmd = STOP_CMD

    try:
        while True:
            now = time.monotonic()

            # ── Deadman: expire stale keys ─────────────────────
            expired = [k for k, t in active_keys.items()
                       if now - t > KEY_TIMEOUT]

            for k in expired:
                del active_keys[k]

            if expired:
                refresh()

            # ── Read input ─────────────────────────────────────
            ch = read_char_nonblocking(fd, timeout=0.02)
            if ch is None:
                continue

            ch = ch.lower()

            if ch in ("q", "\x03", "\x1b"):
                send(ser, STOP_CMD)
                print("\n\n  Stopped. Bye.\n")
                break

            elif ch == " ":
                clear_all()
                print(f"\r  → {STOP_CMD}  [STOP]                            ",
                      end="", flush=True)

            elif ch in MOVE_KEYS:
                active_keys[ch] = now
                refresh()

    except KeyboardInterrupt:
        send(ser, STOP_CMD)
        print("\n\n  Interrupted — stop sent. Bye.\n")

    finally:
        restore(fd, old_term)
        ser.close()


if __name__ == "__main__":
    main()