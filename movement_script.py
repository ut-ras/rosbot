#!/usr/bin/env python3
"""
WASD Rover Controller — Jetson
Real-time WASD control over serial to ESP32/rover.

Key-release is detected by timeout: the OS repeats a held key at ~30 Hz;
if a key hasn't been seen for KEY_TIMEOUT seconds it's treated as released.

Controls:
  W / S     — forward / back
  A / D     — turn left / right
  W+D / W+A — curve forward-right / forward-left
  Space     — emergency stop
  +/-       — increase / decrease speed (step 0.05)
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
DEFAULT_SPEED = 0.25   # 0.0 – 0.5
TURN_BLEND    = 0.6    # fraction of speed used for turning component
SPEED_STEP    = 0.05
MAX_SPEED     = 0.5

# How long (seconds) without receiving a key before treating it as released.
# Linux key-repeat fires at ~30 ms intervals, so 80 ms is a safe threshold.
KEY_TIMEOUT   = 0.08

# ─────────────────────────────────────────────────────────────────────

def clamp(v, lo=-MAX_SPEED, hi=MAX_SPEED):
    return max(lo, min(hi, v))

def make_cmd(L, R):
    return '{{"T":1,"L":{:.2f},"R":{:.2f}}}'.format(L, R)

STOP_CMD = '{"T":1,"L":0,"R":0}'

def compute_lr(keys, speed):
    """Compute L/R motor values from the current held key set."""
    fwd  = "w" in keys and "s" not in keys
    back = "s" in keys and "w" not in keys
    rgt  = "d" in keys and "a" not in keys
    lft  = "a" in keys and "d" not in keys

    drive    = speed if fwd else (-speed if back else 0.0)
    turn_mag = abs(drive) if drive != 0.0 else speed * TURN_BLEND
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
    """Return a character from stdin if one arrives within `timeout` seconds,
    otherwise return None."""
    r, _, _ = select.select([fd], [], [], timeout)
    if r:
        return os.read(fd, 1).decode("utf-8", errors="ignore")
    return None

# ── Main ──────────────────────────────────────────────────────────────

def main():
    port  = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PORT
    baud  = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BAUD
    speed = DEFAULT_SPEED

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
    print("  W/A/S/D = move   Space = stop   +/- = speed   Q = quit\n")
    print(f"  Speed: {speed:.2f}\n")

    fd       = sys.stdin.fileno()
    old_term = set_raw(fd)

    # last_seen[key] = timestamp of most recent keypress event
    MOVE_KEYS = {"w", "a", "s", "d"}
    last_seen = {}   # key → float (time.monotonic)
    held      = set()
    last_cmd  = None

    def refresh():
        nonlocal last_cmd
        cmd = make_cmd(*compute_lr(held, speed)) if held else STOP_CMD
        if cmd != last_cmd:
            send(ser, cmd)
            last_cmd = cmd
            print(f"\r  → {cmd}   speed={speed:.2f}   keys={sorted(held) or ['none']}      ",
                  end="", flush=True)

    try:
        while True:
            now = time.monotonic()

            # ── Expire released keys ──────────────────────────────────
            released = [k for k, t in last_seen.items() if now - t > KEY_TIMEOUT]
            for k in released:
                del last_seen[k]
                held.discard(k)
            if released:
                refresh()

            # ── Read next character (non-blocking, short timeout) ─────
            ch = read_char_nonblocking(fd, timeout=0.02)
            if ch is None:
                continue

            ch = ch.lower()

            # ── Quit ──────────────────────────────────────────────────
            if ch in ("q", "\x03", "\x1b"):   # q, Ctrl-C, Esc
                send(ser, STOP_CMD)
                print("\n\n  Stopped. Bye.\n")
                break

            # ── Emergency stop ────────────────────────────────────────
            elif ch == " ":
                last_seen.clear()
                held.clear()
                send(ser, STOP_CMD)
                last_cmd = STOP_CMD
                print(f"\r  → {STOP_CMD}  [STOP]                            ",
                      end="", flush=True)

            # ── Speed adjust ──────────────────────────────────────────
            elif ch in ("+", "="):
                speed = round(min(MAX_SPEED, speed + SPEED_STEP), 2)
                print(f"\r  Speed: {speed:.2f}                              ",
                      end="", flush=True)
                refresh()

            elif ch in ("-", "_"):
                speed = round(max(0.0, speed - SPEED_STEP), 2)
                print(f"\r  Speed: {speed:.2f}                              ",
                      end="", flush=True)
                refresh()

            # ── Movement keys ─────────────────────────────────────────
            elif ch in MOVE_KEYS:
                last_seen[ch] = now
                if ch not in held:
                    held.add(ch)
                    refresh()
                else:
                    # Key is repeating — just refresh the timestamp, no resend needed
                    pass

    except KeyboardInterrupt:
        send(ser, STOP_CMD)
        print("\n\n  Interrupted — stop sent. Bye.\n")

    finally:
        restore(fd, old_term)
        ser.close()


if __name__ == "__main__":
    main()