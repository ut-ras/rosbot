#!/usr/bin/env python3
"""
WASD Rover Controller — Jetson
Real-time WASD control over serial to ESP32/rover.

Key-release detection strategy:
  - On first press, the key is added to `held` and marked as "pending repeat".
  - Once OS key-repeat starts firing (~500 ms after press), the key is marked
    "repeating" and the timeout logic activates.
  - Only repeating keys are expired by timeout, so the initial repeat-delay
    gap never triggers a false release.

Controls:
  W / S     — forward / back
  A / D     — turn left / right
  W+D / W+A — curve forward-right / forward-left
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

# All movement commands use this speed. Must be high enough for the
# motors to overcome static friction and actually move.
SPEED       = 0.5

# Turning blends this fraction of SPEED into the opposite wheel.
TURN_BLEND  = 0.6

# How long (seconds) without receiving a key before treating it as released.
# Linux key-repeat fires at ~30 ms intervals, so 80 ms is a safe threshold.
KEY_TIMEOUT = 0.08

# ─────────────────────────────────────────────────────────────────────

def clamp(v, lo=-SPEED, hi=SPEED):
    return max(lo, min(hi, v))

def make_cmd(L, R):
    return '{{"T":1,"L":{:.2f},"R":{:.2f}}}'.format(L, R)

STOP_CMD = '{"T":1,"L":0,"R":0}'

def compute_lr(keys):
    fwd  = "w" in keys and "s" not in keys
    back = "s" in keys and "w" not in keys
    rgt  = "d" in keys and "a" not in keys
    lft  = "a" in keys and "d" not in keys

    drive    = SPEED if fwd else (-SPEED if back else 0.0)
    turn_mag = abs(drive) if drive != 0.0 else SPEED * TURN_BLEND
    turn     = turn_mag if rgt else (-turn_mag if lft else 0.0)

    return clamp(drive + turn), clamp(drive - turn)

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

    print(f"\n  WASD Rover Controller")
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
    print(f"  Speed: {SPEED}  (fixed)")
    print("  W/A/S/D = move   Space = stop   Q = quit\n")

    fd       = sys.stdin.fileno()
    old_term = set_raw(fd)

    MOVE_KEYS = {"w", "a", "s", "d"}

    held      = set()
    repeating = set()
    last_seen = {}
    last_cmd  = None

    def refresh():
        nonlocal last_cmd
        cmd = make_cmd(*compute_lr(held)) if held else STOP_CMD
        if cmd != last_cmd:
            send(ser, cmd)
            last_cmd = cmd
            print(f"\r  → {cmd}   keys={sorted(held) or ['none']}      ",
                  end="", flush=True)

    def clear_all():
        nonlocal last_cmd
        held.clear()
        repeating.clear()
        last_seen.clear()
        send(ser, STOP_CMD)
        last_cmd = STOP_CMD

    try:
        while True:
            now = time.monotonic()

            # ── Expire released keys (only once repeat has started) ───
            released = [k for k in repeating if now - last_seen[k] > KEY_TIMEOUT]
            for k in released:
                repeating.discard(k)
                last_seen.pop(k, None)
                held.discard(k)
            if released:
                refresh()

            # ── Read next character ───────────────────────────────────
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
                if ch not in held:
                    held.add(ch)
                    refresh()
                else:
                    repeating.add(ch)
                    last_seen[ch] = now

    except KeyboardInterrupt:
        send(ser, STOP_CMD)
        print("\n\n  Interrupted — stop sent. Bye.\n")

    finally:
        restore(fd, old_term)
        ser.close()


if __name__ == "__main__":
    main()