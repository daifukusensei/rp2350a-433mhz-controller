"""
433mhz Keyboard Controller
Waveshare RP2350-USB-A + CircuitPython 10.x

Requires in /lib:
  neopixel.mpy

Requires boot.py on CIRCUITPY root:
  import usb_host, board
  usb_host.Port(board.GP12, board.GP13)
"""

import board
import time
import neopixel
import usb.core

# ==============================================================================
# NEOPIXEL FIRST -- so we have visual feedback for every subsequent stage
# ==============================================================================
np = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2, auto_write=True)

def led(g, r, b):
    np[0] = (g, r, b)

def led_off():
    np[0] = (0, 0, 0)

def flash_led(g, r, b, times=3, on_ms=80, off_ms=80):
    for _ in range(times):
        led(g, r, b)
        time.sleep(on_ms / 1000)
        led_off()
        time.sleep(off_ms / 1000)

# Immediate power-on blink so we know the board booted
flash_led(50, 50, 50, times=1)   # white = alive
flash_led(0, 0, 50, times=5)     # blue = headless

# ==============================================================================
# MODIFIER BITMASKS
# ==============================================================================
MOD_LCTRL  = 0x01
MOD_LSHIFT = 0x02
MOD_LALT   = 0x04
MOD_LGUI   = 0x08
MOD_RCTRL  = 0x10
MOD_RSHIFT = 0x20
MOD_RALT   = 0x40
MOD_RGUI   = 0x80

# ==============================================================================
# CUSTOM ACTIONS
#
# Format: (modifier_byte, keycode_byte): function
#   modifier_byte  combine MOD_* constants, or 0x00 for none
#   keycode_byte   raw HID usage ID  (A=0x04, F1=0x3A, ScrollLock=0x47 ...)
# ==============================================================================
CUSTOM_ACTIONS = {
    (0x00, 0x04): lambda: flash_led(50, 0, 0, times=3), # A -> flash LED green
	(0x00, 0x05): lambda: flash_led(0, 50, 0, times=3), # B -> flash LED red
	(0x00, 0x06): lambda: flash_led(0, 0, 50, times=3), # C -> flash LED blue

    # Stubs for future local-hardware actions:
    # (0x00, 0x3B): action_433_send,    # F2 -> transmit 433 MHz code
    # (0x00, 0x3C): action_gpio_toggle, # F3 -> toggle GPIO pin
}

# ==============================================================================
# ENDPOINT AUTO-DETECTION
# ==============================================================================
CANDIDATE_ENDPOINTS = [0x81, 0x82, 0x83, 0x84]

def detect_endpoint(dev):
    """
    Block on each candidate endpoint waiting for the first keypress (timeout=0
    means wait forever in CircuitPython's usb.core -- NOT zero milliseconds).
    A USBTimeoutError means the endpoint doesn't exist on this device; move on.
    Any other exception also means this endpoint isn't valid; move on.
    Returns (endpoint, report_has_id).
    report_has_id=True  -> [report_id, modifier, reserved, kc0..kc4]
    report_has_id=False -> [modifier, reserved, kc0..kc5]
    """
    probe = bytearray(8)
    print("Press any key on the keyboard to complete detection...")

    for ep in CANDIDATE_ENDPOINTS:
        try:
            dev.read(ep, probe, timeout=0)   # blocks until a report arrives
            has_id = (probe[0] in range(1, 10)) and (probe[2] == 0x00)
            print("Endpoint found:", hex(ep), "| Report ID prefix:", has_id)
            print("Sample report:", list(probe))
            return ep, has_id
        except usb.core.USBTimeoutError:
            print("No response on", hex(ep), "-- trying next...")
        except Exception as e:
            print("Probe error on", hex(ep), ":", e)

    print("No endpoint responded, defaulting to 0x81")
    return 0x81, False

# ==============================================================================
# USB HOST: FIND AND CONNECT TO KEYBOARD
# ==============================================================================
def find_keyboard(timeout_ms=2000):
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for dev in usb.core.find(find_all=True):
            return dev
        time.sleep(0.01)
    return None

def connect_keyboard():
    global prev_buf

    # Stage 1: scanning -- poll until device appears
    dev = find_keyboard(timeout_ms=2000)
    led_off()

    if dev is None:
        print("No USB device found on host port")
        return None, None, False

    # Stage 2: configure -- errors here are normal, do not abort
    try:
        dev.set_configuration()
        print("Device configured:", dev.manufacturer, dev.product)
    except Exception as e:
        print("set_configuration (non-fatal, continuing):", e)

    # Stage 3: endpoint detection
    ep, has_id = detect_endpoint(dev)

    # Stage 4: ready (two green flashes)
    flash_led(50, 0, 0, times=2)
    prev_buf[:] = bytearray(8)
    print("Connected: endpoint", hex(ep), "report_has_id:", has_id)
    return dev, ep, has_id

# ==============================================================================
# REPORT PARSING
# ==============================================================================
def parse_report(buf, has_id):
    if has_id:
        return buf[1], [k for k in buf[3:8] if k]
    return buf[0], [k for k in buf[2:8] if k]

# ==============================================================================
# MAIN LOOP
# ==============================================================================
print("Starting -- waiting for USB keyboard on host port...")

kbd_dev       = None
hid_endpoint  = None
report_has_id = False
buf           = bytearray(8)
prev_buf      = bytearray(8)

while True:

    # Connect / reconnect
    if kbd_dev is None:
        kbd_dev, hid_endpoint, report_has_id = connect_keyboard()
        if kbd_dev is None:
            time.sleep(0.5)
            continue

    # Read one HID report (10 ms timeout)
    try:
        kbd_dev.read(hid_endpoint, buf, timeout=10)
    except usb.core.USBTimeoutError:
        continue
    except Exception as e:
        print("Read error (disconnected?):", e)
        kbd_dev      = None
        hid_endpoint = None
        led_off()
        continue

    # Skip if state unchanged
    modifier,      keycodes      = parse_report(buf,      report_has_id)
    prev_modifier, prev_keycodes = parse_report(prev_buf, report_has_id)
    if modifier == prev_modifier and keycodes == prev_keycodes:
        continue
    prev_buf[:] = buf

    # Dispatch custom actions
    for kc in keycodes:
        action = CUSTOM_ACTIONS.get((modifier, kc))
        if action:
            action()