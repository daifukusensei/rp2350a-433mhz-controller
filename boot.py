import usb_host
import board
import storage
import digitalio

usb_host.Port(board.GP12, board.GP13)

btn = digitalio.DigitalInOut(board.GP15)
btn.switch_to_input(pull=digitalio.Pull.UP)

if btn.value:
    # Button not held -- normal operation, code.py can write (5V or USB)
    storage.remount("/", readonly=False)
# else: button held -- CIRCUITPY is writable from your PC

btn.deinit()