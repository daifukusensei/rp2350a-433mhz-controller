# Waveshare RP2350-USB-A Keyboard Interceptor

A USB keyboard pass-through device built on the Waveshare RP2350-USB-A and CircuitPython. It sits between a physical keyboard and a host PC, intercepts keystrokes, executes custom actions, and transparently forwards all keys to the PC. It also runs in **standalone mode** — powered without a host PC — so you can use keystrokes to control hardware directly (LEDs, 433 MHz transmitters, relays, etc.).

```
Physical Keyboard  →  [USB-A]  RP2350-USB-A  [USB-C]  →  Host PC
                                    ↕
                             GPIO / UART / SPI
                          (LEDs, 433 MHz TX, relays …)
```

---

## Operating Modes

The script detects which mode to use automatically at boot by attempting to initialise the HID output device. No configuration is needed.

| Mode | How to trigger | Behaviour |
|---|---|---|
| **Passthrough** | USB-C plugged into a host PC | Custom actions fire AND keypresses are forwarded to the PC |
| **Standalone** | Powered from USB power bank, bench supply, etc. | Custom actions fire only; HID output is silently skipped |

The NeoPixel flashes at startup to confirm the active mode:

| Colour | Meaning |
|---|---|
| Green flash ×2 at boot | Passthrough mode — host PC detected |
| Blue flash ×2 at boot | Standalone mode — no host PC |

---

## Features

- **Dual-mode** — works with or without a connected host PC
- Fully transparent in passthrough mode — the PC sees a standard HID keyboard
- Intercept any key or key combination to trigger custom actions
- Consume keys (PC never sees them) or forward them alongside the action
- NeoPixel LED provides visual feedback for actions and state
- Automatic reconnect if the keyboard is unplugged and replugged

---

## Hardware Required

| Item | Notes |
|---|---|
| Waveshare RP2350-USB-A | Has both USB-C (to PC) and USB-A (for keyboard) |
| USB keyboard | Any standard wired USB HID keyboard |
| USB-C cable | To connect the board to the host PC (passthrough mode), or any USB power source (standalone mode) |

---

## Setup

### 1. Flash CircuitPython

Download CircuitPython 10.x for the Waveshare RP2350-Zero board profile:
https://circuitpython.org/board/waveshare_rp2350_zero/

- Hold **BOOTSEL**, plug into your PC, then release
- A drive called `RPI-RP2` appears — drag the `.UF2` onto it
- The board reboots and remounts as `CIRCUITPY`

### 2. Install Libraries

Using `circup` (recommended):
```bash
pip install circup
circup install adafruit_hid neopixel
```

Or manually copy into `CIRCUITPY/lib/` from the [Adafruit CircuitPython Bundle](https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases):
- `adafruit_hid/` (folder)
- `neopixel.mpy`

> `adafruit_hid` is required even in standalone mode — the script imports `Keycode` from it to resolve keycode constants in `CUSTOM_ACTIONS`. If the library is absent the script will fall back gracefully, but you won't be able to reference `Keycode.*` in your action definitions.

### 3. Create boot.py

Create `boot.py` in the root of your `CIRCUITPY` drive. This initialises the USB host port before CircuitPython starts — it **must** be in `boot.py`, not `code.py`:

```python
import usb_host
import board

usb_host.Port(board.GP12, board.GP13)
```
> The RP2350-USB-A USB-A host port is implemented via PIO on **GP12 (D+)** and **GP13 (D−)**. `usb_host.Port()` takes arguments in (D+, D−) order, so the correct call is `usb_host.Port(board.GP12, board.GP13)`.

### 4. Deploy the Script

Copy `keyboard_passthrough.py` to your `CIRCUITPY` drive and rename it `code.py`. CircuitPython automatically runs `code.py` on every boot.

### 5. File Structure

```
CIRCUITPY/
  boot.py              ← USB host port init (runs before code.py)
  code.py              ← Main passthrough script
  lib/
    adafruit_hid/      ← HID keyboard output library
    neopixel.mpy       ← NeoPixel LED library
```

---

## Custom Actions

Actions are defined in the `CUSTOM_ACTIONS` dict in `code.py`:

```python
CUSTOM_ACTIONS = {
    # (modifier_byte, keycode): (function, pass_through_to_pc)
    (0x00, 0x68):       (action_flash,        False),  # F13        → flash LED, consume
    (MOD_LCTRL, 0x3A):  (action_type_macro,   False),  # Ctrl+F1    → type macro, consume
    (0x00, 0x47):       (action_toggle_layer,  True),  # Scroll Lock → toggle + forward
}
```

| Parameter | Description |
|---|---|
| `modifier_byte` | Combine `MOD_*` constants with `\|`, or `0x00` for none |
| `keycode` | Raw HID keycode for the key |
| `function` | Python function to call when the key is pressed |
| `pass_through` | `True` = also forward to PC, `False` = consume. Ignored in standalone mode. |

### Writing Actions for Both Modes

Action functions should handle both modes. Use the helper functions for any host output — they are no-ops in standalone mode:

| Helper | Passthrough | Standalone |
|---|---|---|
| `hid_press(*keys)` | Presses keys on host PC | Silent no-op |
| `hid_release_all()` | Releases all keys | Silent no-op |
| `hid_type(text)` | Types a string via `KeyboardLayoutUS` | Prints to REPL |

Use the `PASSTHROUGH_MODE` boolean to branch when an action needs to do fundamentally different things in each mode:

```python
def action_type_macro():
    if PASSTHROUGH_MODE:
        hid_type("Hello from Pico!\n")
    else:
        # Standalone: trigger hardware instead
        # e.g. pulse a 433 MHz transmitter, toggle a relay, etc.
        print("[STANDALONE] macro key pressed")
        flash_led(50, 25, 0, times=2)
```

### Modifier Constants

| Constant | Key |
|---|---|
| `MOD_LCTRL` | Left Ctrl |
| `MOD_LSHIFT` | Left Shift |
| `MOD_LALT` | Left Alt |
| `MOD_LGUI` | Left Win / Cmd |
| `MOD_RCTRL` | Right Ctrl |
| `MOD_RSHIFT` | Right Shift |
| `MOD_RALT` | Right Alt |
| `MOD_RGUI` | Right Win / Cmd |

### Common HID Keycodes

| Key | Code | Key | Code |
|---|---|---|---|
| A–Z | 0x04–0x1D | Space | 0x2C |
| F1–F12 | 0x3A–0x45 | Enter | 0x28 |
| F13–F24 | 0x68–0x73 | Escape | 0x29 |
| Scroll Lock | 0x47 | Insert | 0x49 |
| Pause | 0x48 | Tab | 0x2B |

Full keycode table: [USB HID Usage Tables, page 83](https://usb.org/sites/default/files/hut1_3_0.pdf)

### Example: Standalone GPIO Action

```python
import digitalio

# Set up a GPIO output (e.g. connected to a 433 MHz transmitter data pin)
tx_pin = digitalio.DigitalInOut(board.GP15)
tx_pin.direction = digitalio.Direction.OUTPUT

def action_transmit():
    """Pulse GP15 to trigger a 433 MHz transmitter."""
    tx_pin.value = True
    time.sleep(0.1)
    tx_pin.value = False
    flash_led(50, 0, 50, times=1)   # purple flash = transmitted

# Add to CUSTOM_ACTIONS:
# (0x00, 0x68): (action_transmit, False),  # F13 → transmit
```

### Example: Passthrough Macro

```python
def action_open_notepad():
    hid_press(Keycode.LEFT_GUI, Keycode.R)
    time.sleep(0.1)
    hid_release_all()
    time.sleep(0.3)
    hid_type("notepad\n")

# Add to CUSTOM_ACTIONS:
# (MOD_LGUI, 0x3A): (action_open_notepad, False),  # Win+F1
```

---

## NeoPixel LED Reference

| Colour | Meaning |
|---|---|
| Green flash ×2 at boot | Passthrough mode active |
| Blue flash ×2 at boot | Standalone mode active |
| Green flash ×2 (later) | Keyboard connected successfully |
| Green flash ×3 | `action_flash` triggered |
| Blue solid | Custom layer active |
| Off | Idle / layer inactive |

Colours are RGB tuples — edit the `led(r, g, b)` calls in each action function to customise.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Green LED blinks 2× every 5s | CircuitPython import error | Connect Thonny, check REPL for traceback |
| Stuck on "Waiting for USB keyboard" | Keyboard not detected | Check USB connection; try a different keyboard |
| Keys doubled on PC | `pass_through=True` AND action also types | Set `pass_through=False` |
| No `CIRCUITPY` drive | Board not in correct mode | Hold BOOTSEL, replug, wait for `RPI-RP2` |
| `boot.py` changes not taking effect | Board not hard-reset | Unplug and replug |
| Wrong keys intercepted | Incorrect keycode | Print `list(buf)` in the main loop to verify raw values |
| Always enters standalone mode | `usb_hid` not enumerating | Ensure USB-C is connected to a powered host PC (not a charger) before boot |
| Standalone actions not running | `PASSTHROUGH_MODE` branch missing | Add an `else` branch in your action function for standalone behaviour |

---

## Dependencies

- [CircuitPython 10.x](https://circuitpython.org/board/waveshare_rp2350_zero/)
- [adafruit_hid](https://github.com/adafruit/Adafruit_CircuitPython_HID)
- [neopixel](https://github.com/adafruit/Adafruit_CircuitPython_NeoPixel)