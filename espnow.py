#!/usr/bin/env python3
"""
ESP32 Serial Terminal — Jetson
Sends JSON commands to the ESP32 transmitter over UART,
which forwards them to the rover via ESP-NOW.

Usage:
    python3 esp32_terminal.py [port] [baud]

    port  — defaults to /dev/ttyUSB0
    baud  — defaults to 115200

Examples:
    python3 esp32_terminal.py
    python3 esp32_terminal.py /dev/ttyUSB1
    python3 esp32_terminal.py /dev/ttyUSB0 115200
"""

import serial
import serial.tools.list_ports
import threading
import sys
import time

# ── Config ────────────────────────────────────────────────────────────
DEFAULT_PORT = "/dev/ttyTHS1"
DEFAULT_BAUD = 115200

# ── Preset commands (type the shortcut instead of full JSON) ──────────
PRESETS = {
    "stop":      '{"T":1,"L":0,"R":0}',
    "fwd":       '{"T":1,"L":0.5,"R":0.5}',
    "back":      '{"T":1,"L":-0.5,"R":-0.5}',
    "left":      '{"T":1,"L":-0.3,"R":0.3}',
    "right":     '{"T":1,"L":0.3,"R":-0.3}',
    "fwd_fast":  '{"T":1,"L":1.0,"R":1.0}',
    "back_fast": '{"T":1,"L":-1.0,"R":-1.0}',
}

# ─────────────────────────────────────────────────────────────────────

def list_ports():
    """Print all available serial ports."""
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("  No serial ports found.")
    for p in ports:
        print(f"  {p.device:20s} — {p.description}")

def reader_thread(ser):
    """Background thread — prints anything the ESP32 sends back."""
    while True:
        try:
            if ser.in_waiting:
                line = ser.readline().decode("utf-8", errors="replace").strip()
                if line:
                    print(f"\n  ← {line}")
                    print("  > ", end="", flush=True)
        except serial.SerialException:
            print("\n[!] Serial connection lost.")
            break
        except Exception:
            pass
        time.sleep(0.01)

def send(ser, cmd):
    """Send a command string, appending newline."""
    cmd = cmd.strip()
    if not cmd:
        return
    ser.write((cmd + "\n").encode("utf-8"))
    print(f"  → {cmd}")

def print_help():
    print("""
  ── Commands ──────────────────────────────────────────
  Any JSON string        Send raw JSON to rover
                         e.g. {"T":1,"L":0.5,"R":0.5}

  ── Presets ───────────────────────────────────────────""")
    for k, v in PRESETS.items():
        print(f"  {k:15s}  →  {v}")
    print("""
  ── Terminal commands ─────────────────────────────────
  help                   Show this message
  ports                  List available serial ports
  quit / exit / q        Exit
  ─────────────────────────────────────────────────────
""")

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PORT
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BAUD

    print(f"\n  ESP32 Serial Terminal")
    print(f"  Connecting to {port} at {baud} baud...\n")

    # Auto-detect if default port doesn't exist
    try:
        ser = serial.Serial(port, baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"  [!] Could not open {port}: {e}")
        print("\n  Available ports:")
        list_ports()
        print("\n  Run with: python3 esp32_terminal.py /dev/ttyUSBx\n")
        sys.exit(1)

    time.sleep(2)  # Wait for ESP32 to boot / reset after serial connect
    ser.reset_input_buffer()

    print(f"  Connected. Type 'help' for commands.\n")

    # Start background reader
    t = threading.Thread(target=reader_thread, args=(ser,), daemon=True)
    t.start()

    try:
        while True:
            try:
                user_input = input("  > ").strip()
            except EOFError:
                break

            if not user_input:
                continue

            low = user_input.lower()

            if low in ("quit", "exit", "q"):
                # Send stop before exiting for safety
                send(ser, PRESETS["stop"])
                print("\n  Bye.\n")
                break

            elif low == "help":
                print_help()

            elif low == "ports":
                print("\n  Available ports:")
                list_ports()
                print()

            elif low in PRESETS:
                send(ser, PRESETS[low])

            else:
                # Treat as raw JSON
                send(ser, user_input)

    except KeyboardInterrupt:
        send(ser, PRESETS["stop"])
        print("\n\n  Interrupted — stop sent. Bye.\n")

    finally:
        ser.close()

if __name__ == "__main__":
    main()