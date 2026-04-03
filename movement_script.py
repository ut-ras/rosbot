#!/usr/bin/env python3
"""
WASD Rover Controller — Jetson
Wraps esp32_terminal.py logic with real-time keyboard input.
 
Controls:
  W / S     — forward / back
  A / D     — turn left / right
  W+D / W+A — curve forward-right / forward-left
  Space     — emergency stop
  +/-       — increase / decrease speed (step 0.1)
  Q         — quit (sends stop first)
 
Usage:
    python3 wasd_rover.py [port] [baud]
"""
 
import sys
import time
import termios
import tty
import threading
import serial
 
# ── Config ────────────────────────────────────────────────────────────
DEFAULT_PORT = "/dev/ttyTHS1"
DEFAULT_BAUD = 115200
DEFAULT_SPEED = 0.5   # 0.0 – 1.0
TURN_BLEND    = 0.6   # fraction of speed applied to turning component
SPEED_STEP    = 0.1
 
# ─────────────────────────────────────────────────────────────────────
 
def clamp(v, lo=-1.0, hi=1.0):
    return max(lo, min(hi, v))
 
def make_cmd(L, R):
    return '{{"T":1,"L":{:.2f},"R":{:.2f}}}'.format(L, R)
 
STOP_CMD = '{"T":1,"L":0,"R":0}'
 
def compute_lr(keys, speed):
    """Compute L/R motor values from the current held key set."""
    L = R = 0.0
    if "w" in keys:
        L += speed;  R += speed
    if "s" in keys:
        L -= speed;  R -= speed
    if "a" in keys:
        L -= speed * TURN_BLEND;  R += speed * TURN_BLEND
    if "d" in keys:
        L += speed * TURN_BLEND;  R -= speed * TURN_BLEND
    return clamp(L), clamp(R)
 
# ── Serial helpers ────────────────────────────────────────────────────
 
def send(ser, cmd):
    ser.write((cmd + "\n").encode("utf-8"))
 
def reader_thread(ser):
    """Print anything the ESP32 sends back."""
    while True:
        try:
            if ser.in_waiting:
                line = ser.readline().decode("utf-8", errors="replace").strip()
                if line:
                    print(f"\r  ← {line}")
        except Exception:
            break
        time.sleep(0.02)
 
# ── Terminal raw-mode helpers ─────────────────────────────────────────
 
def get_char():
    """Read a single raw character from stdin (blocking)."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch
 
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
 
    t = threading.Thread(target=reader_thread, args=(ser,), daemon=True)
    t.start()
 
    print("  Connected.")
    print("  W/A/S/D = move   Space = stop   +/- = speed   Q = quit\n")
    print(f"  Speed: {speed:.1f}\n")
 
    # Track which movement keys are currently held
    held = set()
    last_cmd = None
 
    def refresh():
        nonlocal last_cmd
        if held:
            L, R = compute_lr(held, speed)
            cmd = make_cmd(L, R)
        else:
            cmd = STOP_CMD
        if cmd != last_cmd:
            send(ser, cmd)
            last_cmd = cmd
            print(f"\r  → {cmd}   speed={speed:.1f}   keys={sorted(held) or ['none']}   \r", end="", flush=True)
 
    # --- key → held-set mapping -----------------------------------------
    # We run in raw mode: each keydown fires get_char().
    # To support held keys we'd need a proper event loop (e.g. pynput).
    # For a terminal we poll: each character press toggles/sends immediately.
    # Hold behaviour: re-sending the same command is idempotent on the rover.
 
    try:
        while True:
            ch = get_char().lower()
 
            if ch in ("q", "\x03"):        # Q or Ctrl-C
                send(ser, STOP_CMD)
                print("\n\n  Stopped. Bye.\n")
                break
 
            elif ch == " ":                # space — emergency stop
                held.clear()
                send(ser, STOP_CMD)
                last_cmd = STOP_CMD
                print(f"\r  → {STOP_CMD}  [STOP]            \r", end="", flush=True)
 
            elif ch in ("+", "="):
                speed = round(min(1.0, speed + SPEED_STEP), 2)
                print(f"\r  Speed: {speed:.1f}               \r", end="", flush=True)
                refresh()
 
            elif ch in ("-", "_"):
                speed = round(max(0.0, speed - SPEED_STEP), 2)
                print(f"\r  Speed: {speed:.1f}               \r", end="", flush=True)
                refresh()
 
            elif ch in ("w", "a", "s", "d"):
                # Toggle key in held set (press = add, same press = remove to stop)
                # Better UX: treat each keypress as "start moving that direction"
                # and send; releasing isn't detectable in basic raw mode,
                # so instead we re-send on every press, which keeps the rover moving.
                held.add(ch)
                refresh()
 
            # After any non-movement key, clear held and stop
            # (optional strict mode — comment out if you prefer latching)
 
    except KeyboardInterrupt:
        send(ser, STOP_CMD)
        print("\n\n  Interrupted — stop sent. Bye.\n")
 
    finally:
        ser.close()
 
 
if __name__ == "__main__":
    main()