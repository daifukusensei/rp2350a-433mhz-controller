"""
boot.py  --  place this file on the CIRCUITPY root drive.

Changes vs original:
  * storage.remount("/", readonly=False) so code.py can write signal files.
    The board will NO LONGER appear as a writable USB drive to your PC while
    this is in effect.  To edit files again, hold BOOTSEL while plugging in
    (enters UF2 bootloader) or delete / comment out the remount line.
"""
import usb_host
import board
import storage

# Enable USB host on GP12 / GP13 (unchanged from original)
usb_host.Port(board.GP12, board.GP13)

# Make the filesystem writable from code.py.
# readonly=False  means the microcontroller owns writes;
# the CIRCUITPY USB drive will appear read-only on your PC.
storage.remount("/", readonly=False)