"""
433mhz Keyboard Controller
Waveshare RP2350-USB-A + CircuitPython 10.x

Requires in /lib:
  neopixel.mpy

Requires boot.py on CIRCUITPY root:
  import usb_host, board, storage
  usb_host.Port(board.GP12, board.GP13)
  storage.remount("/", readonly=False)   # <-- NEW: allows file writes

433 MHz wiring:
  RX data pin -> GP28
  TX data pin -> GP29  (change RF_TX_PIN below if different)

Signal persistence:
  Recorded signals are saved to /signals/<name>.sig on the CIRCUITPY flash.
  Files are plain binary dumps of the array.array('H', ...) pulse train.
  They are loaded automatically at boot so signals survive power cycles.
  Filename examples:  A.sig  B.sig  SHIFT_A.sig  CTRL_F1.sig
"""

import array
import board
import os
import time
import neopixel
import pulseio
import supervisor
import usb.core

# ==============================================================================
# NEOPIXEL FIRST -- so we have visual feedback for every subsequent stage
# ==============================================================================
np = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2, auto_write=True)

def led(g, r, b):
    np[0] = (g, r, b)

def led_off():
    np[0] = (0, 0, 0)

def debug(*args, **kwargs):
    """Print only when a serial terminal is actively connected.
    Headless / 5 V-supply operation: CDC TX buffer never fills, no stalling."""
    if supervisor.runtime.serial_connected:
        print(*args, **kwargs)

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
# 433 MHz CONFIG
# ==============================================================================
RF_RX_PIN           = board.GP28
RF_TX_PIN           = board.GP29

RF_CARRIER_HZ       = 433_920      # standard 433.92 MHz carrier for OOK modules
RF_RECORD_TIMEOUT_S  = 60.0        # give up listening after this many seconds
RF_RX_MAXLEN         = 512         # pulse buffer depth (must be power of 2)
RF_PULSE_MIN_US      = 500         # pulses shorter than this are always noise (µs)
RF_PULSE_MAX_US      = 20_000      # pulses longer than this are always noise (µs)
# Consistency-based signal detection.
# A real OOK remote sends pulses of only 2-3 fixed widths; noise is random.
# We bucket pulse widths (resolution RF_BUCKET_US) and require that the top
# RF_CONSIST_BUCKETS buckets account for at least RF_CONSIST_RATIO of all
# valid pulses AND that at least RF_CONSIST_MIN_PULSES valid pulses arrived.
RF_BURST_WINDOW_S     = 0.15       # detection sample window in seconds (150 ms)
RF_CONSIST_MIN_PULSES = 20         # minimum valid pulses required in detection window
RF_BUCKET_US          = 50         # pulse-width bucket resolution (µs)
RF_CONSIST_BUCKETS    = 3          # top N buckets that must dominate
RF_CONSIST_RATIO      = 0.70       # fraction of pulses that must fall in top buckets
RF_CONSIST_CONFIRMATIONS = 10       # consecutive passing windows required before capture
                                   # (prevents switching-supply noise false positives)
RF_CAPTURE_WINDOW_S   = 0.35       # how long to record after signal detected (ms)
RF_REPLAY_TIMES       = 1          # number of times to repeat transmission

# Keyed by (modifier_byte, keycode_byte), value is an array.array('H', pulses)
RF_SIGNALS = {}

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
# SIGNAL FILE PERSISTENCE
# ==============================================================================
SIGNALS_DIR = "/signals"

# HID Usage ID -> human-readable name used for the filename stem.
# Add more entries here if you use keys not yet listed.
KEYCODE_NAMES = {
    # Letters
    0x04: "A",  0x05: "B",  0x06: "C",  0x07: "D",
    0x08: "E",  0x09: "F",  0x0A: "G",  0x0B: "H",
    0x0C: "I",  0x0D: "J",  0x0E: "K",  0x0F: "L",
    0x10: "M",  0x11: "N",  0x12: "O",  0x13: "P",
    0x14: "Q",  0x15: "R",  0x16: "S",  0x17: "T",
    0x18: "U",  0x19: "V",  0x1A: "W",  0x1B: "X",
    0x1C: "Y",  0x1D: "Z",
    # Digits (top-row)
    0x1E: "1",  0x1F: "2",  0x20: "3",  0x21: "4",  0x22: "5",
    0x23: "6",  0x24: "7",  0x25: "8",  0x26: "9",  0x27: "0",
    # Common keys
    0x28: "ENTER",  0x29: "ESC",   0x2A: "BACKSPACE", 0x2B: "TAB",
    0x2C: "SPACE",  0x2D: "MINUS", 0x2E: "EQUALS",
    0x2F: "LBRACE", 0x30: "RBRACE",0x31: "BACKSLASH",
    0x33: "SEMICOLON", 0x34: "QUOTE", 0x36: "COMMA",
    0x37: "PERIOD", 0x38: "SLASH",
    # Function keys
    0x3A: "F1",  0x3B: "F2",  0x3C: "F3",  0x3D: "F4",
    0x3E: "F5",  0x3F: "F6",  0x40: "F7",  0x41: "F8",
    0x42: "F9",  0x43: "F10", 0x44: "F11", 0x45: "F12",
    # Navigation / editing
    0x47: "SCROLLLOCK", 0x49: "INSERT", 0x4A: "HOME",
    0x4B: "PAGEUP", 0x4C: "DELETE", 0x4D: "END", 0x4E: "PAGEDOWN",
    0x4F: "RIGHT", 0x50: "LEFT",  0x51: "DOWN",  0x52: "UP",
    # Numpad
    0x53: "NUM_LOCK", 0x54: "KP_SLASH", 0x55: "KP_STAR",
    0x56: "KP_MINUS", 0x57: "KP_PLUS",  0x58: "KP_ENTER",
    0x59: "KP_1", 0x5A: "KP_2", 0x5B: "KP_3", 0x5C: "KP_4",
    0x5D: "KP_5", 0x5E: "KP_6", 0x5F: "KP_7", 0x60: "KP_8",
    0x61: "KP_9", 0x62: "KP_0", 0x63: "KP_DOT",
}

# Modifier flags -> short prefix string (only non-zero combinations get a prefix)
_MOD_PARTS = [
    (MOD_LCTRL | MOD_RCTRL,  "CTRL"),
    (MOD_LSHIFT | MOD_RSHIFT, "SHIFT"),
    (MOD_LALT | MOD_RALT,    "ALT"),
    (MOD_LGUI | MOD_RGUI,    "GUI"),
]

def _modifier_prefix(modifier):
    """Return a string like 'CTRL_SHIFT_' for the active modifier bits, or ''."""
    parts = []
    for mask, name in _MOD_PARTS:
        if modifier & mask:
            parts.append(name)
    return "_".join(parts) + "_" if parts else ""

def key_combo_to_filename(key_combo):
    """
    Convert (modifier, keycode) to a safe filename stem.
    Examples:
      (0x00, 0x04) -> "A"
      (0x02, 0x04) -> "SHIFT_A"
      (0x01, 0x3B) -> "CTRL_F2"
      (0x00, 0xFF) -> "KEY_FF"   (unknown keycode fallback)
    """
    modifier, keycode = key_combo
    key_name = KEYCODE_NAMES.get(keycode, "KEY_{:02X}".format(keycode))
    return _modifier_prefix(modifier) + key_name

def _ensure_signals_dir():
    """Create /signals directory if it doesn't exist yet."""
    try:
        os.stat(SIGNALS_DIR)
    except OSError:
        os.mkdir(SIGNALS_DIR)

def save_signal(key_combo, pulses, comment=""):
    """
    Persist *pulses* (array.array('H')) to SIGNALS_DIR/<n>.sig as plain text.
    Each pulse width is written as one integer per line (microseconds).
    Lines beginning with '#' are comments and are ignored on load.

    A '# Key: <n>' line is always written automatically.  Pass an optional
    comment string to include a second comment line, e.g.:
        save_signal(key_combo, pulses, comment="garage door opener")

    To annotate a recording later, open the .sig file in any text editor and
    freely add or edit '#' lines -- they survive reloads unchanged.
    Overwrites any previous recording for the same key.

    Example  signals/A.sig:
      # Key: A
      # garage door opener
      560
      1680
      560
      ...
    """
    _ensure_signals_dir()
    name = key_combo_to_filename(key_combo)
    path = SIGNALS_DIR + "/" + name + ".sig"
    try:
        with open(path, "w") as f:
            f.write("# Key: {}\n".format(name))
            if comment:
                f.write("# {}\n".format(comment))
            for p in pulses:
                f.write("{}\n".format(p))
        debug("Signal saved to", path, "(", len(pulses), "pulses )")
    except Exception as e:
        debug("save_signal failed for", path, ":", e)
def load_all_signals():
    """
    Read every *.sig file from SIGNALS_DIR and populate RF_SIGNALS.
    The filename stem is matched against KEYCODE_NAMES (and modifier prefix)
    in reverse to reconstruct the (modifier, keycode) key.
    Falls back to storing by filename if reverse-mapping fails.

    Called once at startup so recorded signals survive power cycles.
    """
    # Build a reverse map:  "CTRL_A"  ->  (0x01, 0x04)
    reverse = {}
    for kc, kname in KEYCODE_NAMES.items():
        # No-modifier version
        reverse[kname] = (0x00, kc)
        # All meaningful modifier combinations
        for mod_mask, mod_name in _MOD_PARTS:
            # Use only the canonical left-side bit for storage key consistency
            lbit = mod_mask & 0x0F  # works because left bits are lower nibble
            reverse[mod_name + "_" + kname] = (lbit, kc)
        # Two-modifier combos (extend as needed)
        for i, (m1, n1) in enumerate(_MOD_PARTS):
            for m2, n2 in _MOD_PARTS[i+1:]:
                lb1 = m1 & 0x0F
                lb2 = m2 & 0x0F
                reverse[n1 + "_" + n2 + "_" + kname] = (lb1 | lb2, kc)

    _ensure_signals_dir()
    try:
        entries = os.listdir(SIGNALS_DIR)
    except OSError:
        debug("load_all_signals: could not list", SIGNALS_DIR)
        return

    loaded = 0
    for fname in entries:
        if not fname.endswith(".sig"):
            continue
        stem = fname[:-4]                       # strip ".sig"
        path = SIGNALS_DIR + "/" + fname
        try:
            with open(path, "r") as f:
                lines = f.read().splitlines()
            values = []
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue          # skip comments and blank lines
                try:
                    values.append(int(line))
                except ValueError:
                    debug("load_all_signals: ignoring bad line in", fname, ":", line)
            pulses = array.array('H', values)
            key_combo = reverse.get(stem)
            if key_combo is None:
                # Unknown name -- store under a dummy key so it isn't lost
                debug("load_all_signals: no reverse mapping for", stem,
                      "-- skipping (re-record to fix)")
                continue
            RF_SIGNALS[key_combo] = pulses
            debug("Loaded signal", path, "->", key_combo,
                  "(", len(pulses), "pulses )")
            loaded += 1
        except Exception as e:
            debug("load_all_signals: error reading", fname, ":", e)

    debug("Loaded", loaded, "signal(s) from", SIGNALS_DIR)

# Load persisted signals before anything else runs
load_all_signals()

# ==============================================================================
# CUSTOM ACTIONS
#
# Format: (modifier_byte, keycode_byte): function
#   modifier_byte  combine MOD_* constants, or 0x00 for none
#   keycode_byte   raw HID usage ID  (A=0x04, F1=0x3A, ScrollLock=0x47 ...)
#
# Note: if a key also has an RF_SIGNALS entry, the RF replay takes priority
# and the CUSTOM_ACTIONS entry is skipped for that key.
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
# 433 MHz RECORD
# Blocking call -- runs while the yellow LED is active and waits for a signal.
# On success: stores pulses in RF_SIGNALS, two yellow flashes, LED off.
# On timeout: three red flashes, LED off.
# Either way clears hold_yellow_active and recording_key before returning.
# ==============================================================================
def record_433_signal(key_combo):
    global hold_yellow_active, recording_key

    debug("RF record: listening on GP28 for key", key_combo,
          "(timeout", RF_RECORD_TIMEOUT_S, "s)...")
    led(50, 50, 0)  # keep yellow while listening

    rx = pulseio.PulseIn(RF_RX_PIN, maxlen=RF_RX_MAXLEN, idle_state=False)
    rx.pause()
    rx.clear()
    # Settling pause: let the receiver AGC stabilise, then discard whatever
    # noise drifted in during that time before we start burst detection.
    time.sleep(0.2)
    rx.clear()
    rx.resume()

    deadline = time.monotonic() + RF_RECORD_TIMEOUT_S
    captured = None
    exc_info = None
    confirm  = 0          # consecutive windows that passed the consistency check

    try:
        while time.monotonic() < deadline:
            # --- Consistency-based signal detection --------------------------
            # Pure noise is randomly distributed across the valid width range.
            # A real OOK remote sends pulses of only 2-3 fixed widths, so the
            # pulse-width histogram is strongly peaked.  We sample a short
            # window, bucket the widths, and check whether the top few buckets
            # account for >= RF_CONSIST_RATIO of all valid pulses.
            #
            # We also require RF_CONSIST_CONFIRMATIONS consecutive passing
            # windows before accepting.  Switching-supply noise can satisfy
            # the histogram test in a single window but won't do so repeatedly
            # at the same pulse widths; real remotes repeat their code.
            rx.clear()
            time.sleep(RF_BURST_WINDOW_S)
            raw   = [rx[i] for i in range(len(rx))]
            valid = [p for p in raw if RF_PULSE_MIN_US <= p <= RF_PULSE_MAX_US]

            if len(valid) >= RF_CONSIST_MIN_PULSES:
                # Build a bucket histogram keyed by (width // RF_BUCKET_US)
                buckets = {}
                for p in valid:
                    k = p // RF_BUCKET_US
                    buckets[k] = buckets.get(k, 0) + 1
                top_counts = sorted(buckets.values(), reverse=True)[:RF_CONSIST_BUCKETS]
                ratio = sum(top_counts) / len(valid)

                if ratio >= RF_CONSIST_RATIO:
                    confirm += 1
                    debug("RF window:", len(valid), "valid pulses, ratio:", ratio,
                          "confirm:", confirm, "/", RF_CONSIST_CONFIRMATIONS)
                else:
                    confirm = 0
                    debug("RF window:", len(valid), "valid pulses, ratio:", ratio,
                          "(below threshold, resetting)")
            else:
                confirm = 0
                debug("RF window:", len(valid), "valid pulses (too few, waiting...)")

            if confirm >= RF_CONSIST_CONFIRMATIONS:
                # Real signal confirmed across multiple windows.
                # The buffer already holds the most recent detection window --
                # extend by RF_CAPTURE_WINDOW_S to catch any trailing pulses.
                time.sleep(RF_CAPTURE_WINDOW_S)
                raw = [rx[i] for i in range(len(rx))]
                # Trim leading/trailing out-of-range pulses (noise) without
                # disrupting the alternating on/off structure PulseOut needs.
                first = None
                for i, p in enumerate(raw):
                    if RF_PULSE_MIN_US <= p <= RF_PULSE_MAX_US:
                        first = i
                        break
                last = None
                for i, p in enumerate(reversed(raw)):
                    if RF_PULSE_MIN_US <= p <= RF_PULSE_MAX_US:
                        last = i
                        break
                if first is not None and last is not None:
                    end     = len(raw) if last == 0 else len(raw) - last
                    trimmed = raw[first:end]
                    captured = array.array('H', [])
                    for p in trimmed:
                        captured.append(p)
                break

    except Exception as e:
        # Catch any hardware/allocation error so it doesn't propagate to the
        # CircuitPython supervisor and silently restart code.py.
        # 5 rapid white flashes = exception during recording (visible headless).
        # Connect serial to read the error message.
        exc_info = e
        debug("RF record exception:", e)

    finally:
        rx.pause()
        rx.deinit()

    hold_yellow_active = False
    recording_key      = None

    if exc_info is not None:
        flash_led(50, 50, 50, times=5, on_ms=60, off_ms=60)  # white x5 = exception
    elif captured is not None:
        RF_SIGNALS[key_combo] = captured
        save_signal(key_combo, captured)           # <-- persist to flash
        debug("RF record: captured", len(captured), "pulses -> saved to", key_combo)
        flash_led(50, 50, 0, times=2)  # two yellow flashes = success
    else:
        debug("RF record: timeout -- no signal detected")
        flash_led(0, 50, 0, times=3)   # three red flashes = failure

    led_off()

# ==============================================================================
# 433 MHz REPLAY
# Transmits a previously recorded pulse train on RF_TX_PIN.
# ==============================================================================
def replay_433_signal(pulses):
    debug("RF replay:", len(pulses), "pulses,", RF_REPLAY_TIMES, "times")
    led(0, 0, 50)  # brief blue while transmitting
    try:
        tx = pulseio.PulseOut(RF_TX_PIN, frequency=RF_CARRIER_HZ,
                              duty_cycle=0x8000)
        for _ in range(RF_REPLAY_TIMES):
            tx.send(pulses)
            # Small gap between repeats mimics how real remotes transmit.
            time.sleep(0.01)
        tx.deinit()
    except Exception as e:
        debug("RF replay error:", e)
    led_off()

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
    debug("Press any key on the keyboard to complete detection...")

    for ep in CANDIDATE_ENDPOINTS:
        try:
            dev.read(ep, probe, timeout=0)   # blocks until a report arrives
            has_id = (probe[0] in range(1, 10)) and (probe[2] == 0x00)
            debug("Endpoint found:", hex(ep), "| Report ID prefix:", has_id)
            debug("Sample report:", list(probe))
            return ep, has_id
        except usb.core.USBTimeoutError:
            debug("No response on", hex(ep), "-- trying next...")
        except Exception as e:
            debug("Probe error on", hex(ep), ":", e)

    debug("No endpoint responded, defaulting to 0x81")
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
        debug("No USB device found on host port")
        return None, None, False

    # Stage 2: configure -- errors here are normal, do not abort
    try:
        dev.set_configuration()
        debug("Device configured:", dev.manufacturer, dev.product)
    except Exception as e:
        debug("set_configuration (non-fatal, continuing):", e)

    # Stage 3: endpoint detection
    ep, has_id = detect_endpoint(dev)

    # Stage 4: ready (two yellow flashes)
    flash_led(50, 50, 0, times=2)
    prev_buf[:] = bytearray(8)
    debug("Connected: endpoint", hex(ep), "report_has_id:", has_id)
    return dev, ep, has_id

# ==============================================================================
# REPORT PARSING
# ==============================================================================
def parse_report(buf, has_id):
    if has_id:
        return buf[1], [k for k in buf[3:8] if k]
    return buf[0], [k for k in buf[2:8] if k]

# ==============================================================================
# HOLD DETECTION
# Tracks when the current set of keys was first pressed so we can light the
# LED solid yellow after HOLD_THRESHOLD_S seconds of continuous hold.
# The yellow LED stays on until the key(s) change (i.e. any new press).
# When yellow activates, recording_key is set so the main loop triggers RF
# capture for that key combo.
# ==============================================================================
HOLD_THRESHOLD_S = 4.0

hold_start_time    = None   # monotonic timestamp of when current keys went down
hold_yellow_active = False  # True while the "held 4 s" yellow LED is lit
recording_key      = None   # (modifier, kc) waiting to be recorded, or None

def update_hold_state(keycodes, prev_keycodes, modifier, prev_modifier):
    """
    Call once per report (after change detection).
    keycodes / prev_keycodes are already-parsed lists.
    Returns nothing; manages hold_start_time and hold_yellow_active globals
    and drives the LED directly.

    LED behaviour:
      - Lights solid yellow once a key has been held for HOLD_THRESHOLD_S.
      - Stays yellow even after the key is released.
      - Turns off (and timer resets) only when a new key is pressed.
    """
    global hold_start_time, hold_yellow_active, recording_key

    keys_now  = (modifier, tuple(sorted(keycodes)))
    keys_prev = (prev_modifier, tuple(sorted(prev_keycodes)))

    # --- State changed -------------------------------------------------------
    if keys_now != keys_prev:
        if keycodes:
            # One or more keys are now down -- this counts as a new press.
            # Cancel any active yellow LED and restart the hold timer.
            if hold_yellow_active:
                hold_yellow_active = False
                recording_key      = None
                led_off()
                debug("New key press: LED cleared")
            hold_start_time = time.monotonic()
        # If keycodes is empty the user just released; leave the LED and
        # timer completely untouched so yellow stays lit if it was on.
        return

    # --- Same keys still held -- check duration ------------------------------
    # Guard: only meaningful while at least one key is physically down.
    if keycodes and hold_start_time is not None and not hold_yellow_active:
        held_for = time.monotonic() - hold_start_time
        if held_for >= HOLD_THRESHOLD_S:
            hold_yellow_active = True
            # Record against the first (lowest) keycode so the mapping is
            # always a single (modifier, kc) pair.
            recording_key = (modifier, min(keycodes))
            led(50, 50, 0)  # solid yellow
            debug("Key held for 4 s: LED solid yellow, will record RF for",
                  recording_key)

# ==============================================================================
# MAIN LOOP
# ==============================================================================
debug("Starting -- waiting for USB keyboard on host port...")

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

    # --------------------------------------------------------------------------
    # RF RECORDING (blocking) -- entered only when hold_yellow_active just fired.
    # Handled before the next USB read so the yellow LED stays on uninterrupted
    # while we wait for the incoming RF signal.
    # --------------------------------------------------------------------------
    if recording_key is not None:
        try:
            record_433_signal(recording_key)
        except Exception as e:
            # Last-resort catch: record_433_signal should never raise, but if
            # something slips through, recover gracefully instead of letting
            # the CircuitPython supervisor restart code.py silently.
            debug("Unhandled exception in record_433_signal:", e)
            flash_led(50, 50, 50, times=10, on_ms=40, off_ms=40)  # white x10 = outer crash
            hold_yellow_active = False
            recording_key      = None
            led_off()
        # recording_key and hold_yellow_active are cleared inside the function.
        # Flush prev_buf so the key-release that follows doesn't look like a
        # spurious state change.
        prev_buf[:] = bytearray(8)
        continue

    # Read one HID report (10 ms timeout)
    try:
        kbd_dev.read(hid_endpoint, buf, timeout=10)
    except usb.core.USBTimeoutError:
        # Even on timeout we need to check whether a held key has crossed the
        # 4-second threshold, so fall through using the unchanged buffer.
        pass
    except Exception as e:
        debug("Read error (disconnected?):", e)
        kbd_dev            = None
        hid_endpoint       = None
        hold_start_time    = None
        hold_yellow_active = False
        recording_key      = None
        led_off()
        continue

    modifier,      keycodes      = parse_report(buf,      report_has_id)
    prev_modifier, prev_keycodes = parse_report(prev_buf, report_has_id)

    # Hold-state update (runs every loop iteration, not just on change)
    update_hold_state(keycodes, prev_keycodes, modifier, prev_modifier)

    # Skip dispatch if nothing changed
    if modifier == prev_modifier and keycodes == prev_keycodes:
        continue
    prev_buf[:] = buf

    # Dispatch: RF replay takes priority over CUSTOM_ACTIONS for the same key
    for kc in keycodes:
        key_combo = (modifier, kc)
        if key_combo in RF_SIGNALS:
            replay_433_signal(RF_SIGNALS[key_combo])
        else:
            action = CUSTOM_ACTIONS.get(key_combo)
            if action:
                action()
