#!/usr/bin/env python3
"""
WASD Rover Controller — Jetson (Game-style, evdev)

Features:
  - True differential steering (W/S + A/D blending)
  - Game-like WASD behavior (instant key down/up)
  - No OS key repeat dependency
  - Emergency stop with Space
  - Quit with Q or Esc

Usage:
    sudo python3 wasd_rover_evdev.py [keyboard_event] [serial_port] [baud]

Example:
    sudo python3 wasd_rover_evdev.py /dev/input/event4 /dev/ttyTHS1 115200
"""

import sys
import time
import threading
import serial
from evdev import InputDevice, categorize, ecodes, KeyEvent

# ── Config ────────────────────────────────────────────────────────────
DEFAULT_PORT = "/dev/ttyTHS1"
DEFAULT_BAUD = 115200
SPEED = 0.5
UPDATE_HZ = 50  # control update frequency

# ── Serial / Command Helpers ───────────────────────────────────────────
def make_cmd(L, R):
    return '{{"T":1,"L":{:.2f},"R":{:.2f}}}'.format(L, R)

STOP_CMD = '{"T":1,"L":0,"R":0}'

def send(ser, cmd):
    ser.write((cmd + "\n").encode("utf-8"))

# ── Differential Steering ─────────────────────────────────────────────
def compute_lr(keys):
    """Compute left/right wheel speeds from current key states"""
    fwd = (1 if keys['w'] else 0) - (1 if keys['s'] else 0)
    turn = (1 if keys['d'] else 0) - (1 if keys['a'] else 0)
    left = fwd + turn
    right = fwd - turn
    max_mag = max(1.0, abs(left), abs(right))
    return (left / max_mag) * SPEED, (right / max_mag) * SPEED

# ── Map evdev scancodes to WASD / Space ────────────────────────────────
EVDEV_KEY_MAP = {
    ecodes.KEY_W: 'w',
    ecodes.KEY_A: 'a',
    ecodes.KEY_S: 's',
    ecodes.KEY_D: 'd',
    ecodes.KEY_SPACE: 'space',
    ecodes.KEY_Q: 'q',
    ecodes.KEY_ESC: 'esc'
}

# ── Main ──────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("Usage: sudo python3 wasd_rover_evdev.py [keyboard_event] [serial_port] [baud]")
        sys.exit(1)

    kb_event = sys.argv[1]
    port = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PORT
    baud = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_BAUD

    print(f"\n  WASD Rover Controller (Game-style)")
    print(f"  Keyboard: {kb_event}")
    print(f"  Serial: {port} @ {baud} baud\n")

    try:
        ser = serial.Serial(port, baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"  [!] Could not open {port}: {e}")
        sys.exit(1)

    keys_state = { 'w': False, 'a': False, 's': False, 'd': False, 'space': False }

    # ── Keyboard reader thread ──────────────────────────────────────────
    def kb_thread():
        dev = InputDevice(kb_event)
        for event in dev.read_loop():
            if event.type == ecodes.EV_KEY:
                key_event = categorize(event)
                key_name = EVDEV_KEY_MAP.get(key_event.scancode)
                if key_name:
                    if key_event.keystate == KeyEvent.key_down:
                        keys_state[key_name] = True
                    elif key_event.keystate == KeyEvent.key_up:
                        keys_state[key_name] = False

    threading.Thread(target=kb_thread, daemon=True).start()

    # ── Main control loop ───────────────────────────────────────────────
    last_cmd = None
    try:
        while True:
            # Emergency stop
            if keys_state.get('space'):
                cmd = STOP_CMD
            else:
                # Compute differential wheel speeds
                L, R = compute_lr(keys_state)
                # Only move if any WASD key is pressed
                if any(keys_state[k] for k in ['w','a','s','d']):
                    cmd = make_cmd(L, R)
                else:
                    cmd = STOP_CMD

            if cmd != last_cmd:
                send(ser, cmd)
                last_cmd = cmd
                print(f"\r  → {cmd}   keys={ [k for k,v in keys_state.items() if v] }      ",
                      end="", flush=True)

            # Quit keys
            if keys_state.get('q') or keys_state.get('esc'):
                send(ser, STOP_CMD)
                print("\n\n  Stopped. Bye.\n")
                break

            time.sleep(1 / UPDATE_HZ)

    except KeyboardInterrupt:
        send(ser, STOP_CMD)
        print("\n\n  Interrupted — stop sent. Bye.\n")

    finally:
        ser.close()

if __name__ == "__main__":
    main()