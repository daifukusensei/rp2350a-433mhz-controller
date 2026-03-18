# Waveshare RP2350A 433 MHz Universal RF Controller

Control 433 MHz radio-frequency (RF) devices like outlets with a standard USB keyboard, using a Waveshare RP2350A microcontroller running CircuitPython.

<p align="center">
  <img width="400" alt="image" src="https://github.com/user-attachments/assets/c794544b-a42c-437f-8f0d-c70990d79b4e" />
</p>

I built this as a replacement for the remotes of the various brands of RF outlets I have around the house, in order to control all from a single keyboard.

---

## How it works

The RP2350A sits between a USB keyboard and your computer (or headless, via dedicated USB power supply). As with a universal TV remote, button presses from the device’s RF remote are first recorded to individual keys on your keyboard, allowing subsequent keypresses to duplicate the same function.

---

## What you need

- Waveshare RP2350A running CircuitPython 10.x (can likely work with other RP2350 devices with USB host support)
- A 433 MHz receiver module (XY-MK-5V) wired to **GP28**
- A 433 MHz transmitter module (FS1000A) wired to **GP29**
- A USB keyboard plugged into the RP2350A's USB host port
- The `neopixel.mpy` library present in `/lib` on the board

---

## Files in this repository

| File | Purpose |
|---|---|
| `boot.py` | Runs at power-on. Sets up USB host mode and controls whether the board's storage is writable from a PC. |
| `code.py` | The main program. Reads the keyboard, records RF signals, and replays them. |
| `pcb/` | Gerber file and EasyEDA project used to manufacture a custom PCB, instead of using a breadboard (so-named 'Project Makemake', per planetary-body naming convention of [previous hardware-based repos of mine](https://github.com/daifukusensei/arduino-gps-logger)). |
| `signals/` | RF signals of products I currently use. |

---
 
## Setup
 
### 1. Flash CircuitPython
Download CircuitPython 10.x for the Waveshare RP2350-USB-A board profile:
https://circuitpython.org/board/waveshare_rp2350a/
- Hold **BOOTSEL**, plug into your PC, then release
- A drive called `RPI-RP2` appears — drag the `.UF2` onto it
- The board reboots and remounts as `CIRCUITPY`
 
### 2. Install libraries
Using `circup` (recommended):
```bash
pip install circup
circup install neopixel
```
Or manually copy into `CIRCUITPY/lib/` from the [Adafruit CircuitPython Bundle](https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases):
- `neopixel.mpy`
 
### 3. Deploy the files
Copy `boot.py` and `code.py` to the root of your `CIRCUITPY` drive. CircuitPython automatically runs `boot.py` first, then `code.py` on every boot.
 
> `boot.py` initialises the USB host port and configures storage — it **must** live in the root of `CIRCUITPY`, not inside a subfolder.
 
### 4. Copy pre-made signals (optional)
Copy the `signals/` folder to the root of your `CIRCUITPY` drive. Any `.sig` files inside will be loaded automatically at boot and immediately available as key bindings to the same key as the filename.
 
### 5. File structure
```
CIRCUITPY/
  boot.py              ← USB host init + storage config (runs before code.py)
  code.py              ← Main script
  signals/             ← Saved RF signals, one .sig file per key binding
    A.sig
    B.sig
    ...
  lib/
    neopixel.mpy       ← NeoPixel LED library
```
 
---

## Recording a new signal

1. Connect your keyboard and power the RP2350A.
2. **Hold down the key** you want to assign (e.g. `A`, `SHIFT+1`, `F3`) for **4 seconds**.
3. The RP2350A's LED turns **solid yellow**, and the board is now listening for an RF signal.
4. **Press and hold the button on your original remote** while close to the RP2350A and receiver. 
5. The LED flashes **yellow twice** on success, or **red three times** if it timed out (try again).

The signal is saved automatically to the `signals/` folder, named after the key you've recorded it to, and re-assigned to the same key automatically across power-cycles. For example, `A.sig` or `SHIFT_F1.sig`. It can be opened in a text editor if you want to add a label or note, or backed up.

---

## Replaying a signal

Just press the key. The LED flashes **blue briefly** while transmitting, then goes off. If the blue LED is seen but the target device fails to respond, try re-recording.

---

## Pre-made signals

The `signals/` folder contains recordings for a few products I currently own. Feel free to re-use them, naming them after the key to which they should be assigned.

---

## Transferring signal files to/from your PC

By default, the board's storage is **not writable from your PC** while the main program is running (this is required so the program itself can save new recordings).

To copy files to or from your PC, **hold the button on GP15 while plugging in** the USB cable. This puts the board into PC-writable mode, and the `CIRCUITPY` drive will appear as normal on your computer. You can then drag `.sig` files in or out of the `signals/` folder freely.

---

## LED status guide

| Colour | Meaning |
|---|---|
| White (single flash) | Board just powered on |
| Blue (5 flashes) | Starting up |
| Yellow (2 flashes) | Keyboard connected |
| Solid yellow | Waiting to record — point your remote at the receiver |
| Yellow (2 flashes) | Signal recorded successfully |
| Red (3 flashes) | Recording timed out — no signal detected |
| Blue (brief) | Replaying a signal |
| White (rapid) | An unexpected error occurred — connect via serial for details |

---

## Adding or editing signals manually

Each `.sig` file in the `signals/` folder is plain text, with one number per line representing pulse timings in microseconds. Lines starting with `#` are comments and are ignored. You can open any file in a text editor to add notes, or copy signal files from another device.

To delete a signal and thus remove a key's mapping, simply delete its `.sig` file.
