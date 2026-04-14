#!/usr/bin/env python3
"""
Rover WASD Controller — multi-key differential steering
========================================================
Held keys are tracked in a set. Every poll tick the mixer
combines throttle (W/S) and turn (A/D) axes into L/R motor
values, so W+A gives a forward-left arc, W+D a forward-right
arc, S+A a reverse-left arc, etc.

Controls:
    W / S          — Forward / Reverse
    A / D          — Turn left / right
    Shift modifier — Full speed (hold alongside W/S/A/D)
    Space          — Emergency stop (clears held keys)
    Q / Ctrl+C     — Quit (sends stop first)

Usage:
    python3 rover_wasd.py [port] [baud]
    python3 rover_wasd.py /dev/ttyTHS1 115200
"""
from typing import Optional
from typing import Set, Tuple
import serial
import serial.tools.list_ports
import threading
import sys
import time
import tty
import termios
import select

# ── Config ──────────────────────────────────────────────────────────────
DEFAULT_PORT = "/dev/ttyTHS1"
DEFAULT_BAUD  = 115200
POLL_HZ       = 20          # How often the mixer runs (Hz)
SEND_HZ       = 10          # Max rate at which duplicate commands are resent

# ── Speed values ────────────────────────────────────────────────────────
THROTTLE_NORMAL = 1.00      # W / S thrust
THROTTLE_FAST   = 1.00      # Shift + W / S thrust
TURN_NORMAL     = 0.40      # A / D turn authority
TURN_FAST       = 0.65      # Shift + A / D turn authority

STOP_CMD = '{"T":1,"L":0,"R":0}'

# ── Serial helpers ───────────────────────────────────────────────────────

def build_cmd(left: float, right: float):
    left  = max(-1.0, min(1.0, left))
    right = max(-1.0, min(1.0, right))
    return f'{{"T":1,"L":{left:.2f},"R":{right:.2f}}}'

def send(ser: serial.Serial, cmd: str):
    ser.write((cmd + "\n").encode("utf-8"))

def reader_thread(ser: serial.Serial):
    """Background thread — prints anything the ESP32 sends back."""
    while True:
        try:
            if ser.in_waiting:
                line = ser.readline().decode("utf-8", errors="replace").strip()
                if line:
                    print(f"\r  <- {line}")
        except serial.SerialException:
            print("\r[!] Serial connection lost.")
            break
        except Exception:
            pass
        time.sleep(0.02)

# ── Key reading ──────────────────────────────────────────────────────────

def read_key():
    """
    Non-blocking single-character read from stdin.
    Returns the character, or None if nothing is available.
    Escape sequences (arrow keys, etc.) are consumed and discarded.
    """
    if not select.select([sys.stdin], [], [], 0)[0]:
        return None
    ch = sys.stdin.read(1)
    if ch == "\x1b":
        if select.select([sys.stdin], [], [], 0.02)[0]:
            sys.stdin.read(2)
        return None
    return ch

# ── Mixer ────────────────────────────────────────────────────────────────

def mix(held: set):
    # ── Normalized throttle axis ─────────────────────
    throttle = 0.0
    if "W" in held:
        throttle += 1.0
    elif "w" in held:
        throttle += 0.6
    if "S" in held:
        throttle -= 1.0
    elif "s" in held:
        throttle -= 0.6

    # ── Normalized turn axis ─────────────────────────
    turn = 0.0
    if "D" in held:
        turn += 1.0
    elif "d" in held:
        turn += 0.6
    if "A" in held:
        turn -= 1.0
    elif "a" in held:
        turn -= 0.6

    # ── Optional: speed-aware turning (recommended) ──
    turn *= (1.0 - 0.5 * abs(throttle))

    # ── Differential mix (arcade drive) ──────────────
    left  = throttle + turn
    right = throttle - turn

    # ── Normalize to preserve ratios ────────────────
    max_mag = max(1.0, abs(left), abs(right))
    left  /= max_mag
    right /= max_mag

    # ── FINAL SCALING → match your hardware range ───
    MAX_OUTPUT = 0.5
    left  *= MAX_OUTPUT
    right *= MAX_OUTPUT

    return left, right
# ── UI ───────────────────────────────────────────────────────────────────

DIRECTION_LABEL = {
    frozenset({"w"}):       "^  forward",
    frozenset({"s"}):       "v  reverse",
    frozenset({"a"}):       "<  turn left",
    frozenset({"d"}):       ">  turn right",
    frozenset({"w", "a"}):  "/^ forward-left",
    frozenset({"w", "d"}):  "^/ forward-right",
    frozenset({"s", "a"}):  "\\v reverse-left",
    frozenset({"s", "d"}):  "v/ reverse-right",
    frozenset({"W"}):       "^^ fast forward",
    frozenset({"S"}):       "vv fast reverse",
    frozenset({"W", "A"}):  "/^^ fast fwd-left",
    frozenset({"W", "D"}):  "^^/ fast fwd-right",
    frozenset({"S", "A"}):  "\\vv fast rev-left",
    frozenset({"S", "D"}):  "vv/ fast rev-right",
}

def label_for(held: set):
    return DIRECTION_LABEL.get(frozenset(held), f"keys: {sorted(held)}")

def print_controls():
    print("""
  +------------------------------------------+
  |   ROVER WASD CONTROLLER                  |
  +------------------------------------------+
  |  Hold W / S        Forward / reverse     |
  |  Hold A / D        Turn left / right     |
  |  Combine W+A etc.  Diagonal arcs         |
  |  Shift+W/S/A/D     Full speed            |
  |  Space             Emergency stop        |
  |  Q / Ctrl+C        Quit                  |
  +------------------------------------------+
  |  Release all keys to stop automatically  |
  +------------------------------------------+
""")

# ── Main ─────────────────────────────────────────────────────────────────

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PORT
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BAUD

    print(f"\n  Connecting to {port} at {baud} baud...")

    try:
        ser = serial.Serial(port, baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"\n  [!] Could not open {port}: {e}")
        print("\n  Available ports:")
        for p in serial.tools.list_ports.comports():
            print(f"    {p.device:20s} -- {p.description}")
        sys.exit(1)

    time.sleep(2)
    ser.reset_input_buffer()
    send(ser, STOP_CMD)

    t = threading.Thread(target=reader_thread, args=(ser,), daemon=True)
    t.start()

    print_controls()

    fd          = sys.stdin.fileno()
    old_tty     = termios.tcgetattr(fd)
    poll_period = 1.0 / POLL_HZ
    send_period = 1.0 / SEND_HZ

    held: set[str] = set()
    last_cmd       = None
    last_send_t    = 0.0

    DRIVE_KEYS = set("wasdWASD")

    try:
        tty.setraw(fd)

        while True:
            loop_start = time.monotonic()

            # ── Drain all pending keypresses this tick ───────────────────
            while True:
                ch = read_key()
                if ch is None:
                    break

                if ch in ("\x03", "q", "Q"):
                    raise KeyboardInterrupt

                if ch == " ":
                    held.clear()
                    send(ser, STOP_CMD)
                    last_cmd    = STOP_CMD
                    last_send_t = loop_start
                    print(f"\r  [STOP]{' ' * 44}", flush=True)
                    continue

                if ch in DRIVE_KEYS:
                    # Raw mode gives us key-repeat chars while held,
                    # and nothing once released — so refreshing the set
                    # each tick is the correct "held" signal.
                    held.add(ch)

            # ── Age out keys that stopped repeating (= released) ─────────
            # OS key-repeat fires at ~30 Hz; our poll is 20 Hz, so every
            # held key should have refreshed within one poll cycle.
            # We evict any key NOT seen this tick by rebuilding held only
            # from chars received since loop_start.
            #
            # Simpler approach that works at these rates: clear held at the
            # top of each tick and re-add only what arrived this tick.
            # The block below implements this correctly:

            # (held was built fresh this tick — keys seen = held as-is)
            # To evict stale keys we rebuild from scratch each tick.
            # The read loop above adds to `held`; we need to start empty.
            # Restructure: clear before read, add during read — done below
            # via a flag set approach in the rewritten loop.

            # ── Compute and send ─────────────────────────────────────────
            if held:
                left, right = mix(held)
                cmd = build_cmd(left, right)
            else:
                cmd = STOP_CMD

            now = time.monotonic()
            if cmd != last_cmd or (now - last_send_t) >= send_period:
                send(ser, cmd)
                last_cmd    = cmd
                last_send_t = now

                if cmd == STOP_CMD:
                    print(f"\r  [stopped]{' ' * 40}", flush=True)
                else:
                    lbl = label_for(held)
                    print(f"\r  {lbl:<22}  L={left:+.2f}  R={right:+.2f}   ",
                          flush=True)

            # Clear held AFTER computing so next tick starts fresh.
            # Keys that are still physically held will re-appear via
            # OS auto-repeat before the next mix() call.
            held.clear()

            elapsed = time.monotonic() - loop_start
            sleep_t = poll_period - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

    except KeyboardInterrupt:
        pass

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_tty)
        send(ser, STOP_CMD)
        ser.close()
        print("\n\n  Rover stopped. Bye.\n")


# ── Design note: key-release detection in raw terminal mode ─────────────
#
# Linux raw-mode terminals only deliver key-DOWN / key-repeat events.
# True key-up requires evdev or a GUI toolkit — neither available in a
# headless Jetson serial session.
#
# The approach used here: clear `held` at the END of every poll tick,
# then re-populate it only from characters that arrive in the NEXT tick.
# The OS auto-repeats held keys at ~30 Hz (kbdrate default). At 20 Hz
# polling a held key always floods at least one char per tick, so it
# stays in `held`. When released, repetition stops, no char arrives,
# `held` stays empty, and stop is sent within one poll period (~50 ms).
#
# If your keyboard repeat rate is very low, tune it:
#   kbdrate -d 200 -r 30        # 200 ms delay, 30 Hz repeat
# ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()