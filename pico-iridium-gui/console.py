# Debug console on a 128x64 SSD1306 I2C OLED (16 chars x 8 lines).
# Line 0 is a fixed status header (e.g. the IP address); lines 1-7 scroll.
# Everything is also printed to the USB serial console.
# If no display is found, log() just prints.
from machine import Pin, I2C

COLS, ROWS = 16, 8

_oled = None
_header = ""
_lines = []

try:
    import ssd1306
    _i2c = I2C(1, sda=Pin(2), scl=Pin(3), freq=400_000)
    addrs = _i2c.scan()
    addr = 0x3C if 0x3C in addrs else (0x3D if 0x3D in addrs else None)
    if addr is None:
        print("OLED: no display found on I2C1 (GP2/GP3), scan:", [hex(a) for a in addrs])
    else:
        _oled = ssd1306.SSD1306_I2C(128, 64, _i2c, addr=addr)
except ImportError:
    print("OLED: ssd1306 driver missing, run: mpremote mip install ssd1306")
except Exception as e:
    print("OLED init failed:", e)


def _draw():
    if not _oled:
        return
    try:
        _oled.fill(0)
        _oled.fill_rect(0, 0, 128, 8, 1)          # inverted header bar
        _oled.text(_header[:COLS], 0, 0, 0)
        for i, line in enumerate(_lines):
            _oled.text(line, 0, 8 * (i + 1))
        _oled.show()
    except Exception as e:  # never let the display crash the app
        print("OLED error:", e)


def header(text):
    """Set the fixed top line (e.g. IP address)."""
    global _header
    _header = str(text)
    _draw()


def log(*args):
    """Print to serial and append to the OLED, wrapping long lines."""
    msg = " ".join(str(a) for a in args)
    print(msg)
    for raw in msg.split("\n"):
        raw = raw or " "
        for i in range(0, len(raw), COLS):
            _lines.append(raw[i:i + COLS])
    del _lines[:-(ROWS - 1)]
    _draw()
