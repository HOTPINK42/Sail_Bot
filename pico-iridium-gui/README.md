# Pico Iridium web GUI

Super-basic web GUI for an Iridium SBD modem (RockBLOCK) on a WIZnet W5500-EVB-Pico.
Shows modem status, signal and IMEI, and lets you send and receive messages from a browser.

## Hardware
- WIZnet W5500-EVB-Pico (Ethernet)
- RockBLOCK on UART1 at 19200 baud (TX/RX cross over: Pico TX → modem RX)
- RockBLOCK+ uses RS-232 levels and a 9–30 V supply: put a MAX3232 between it and the Pico
- Optional: 0.96" SSD1306 128x64 I2C OLED as a debug console (I2C1)

| RockBLOCK (via MAX3232)            | Pico pin |
|------------------------------------|----------|
| RX input, yellow (data into modem) | GP4 / UART1 TX (pin 6) |
| TX output, blue (data out of modem) | GP5 / UART1 RX (pin 7) |
| GND                                | GND (pin 8) |

The MAX3232 breakout sits in the middle: power it from the Pico's 3V3 (not 5 V) and tie its
GND to both the Pico and the RockBLOCK. Breakout TX/RX labels are often from the board's own
point of view — if the modem doesn't answer, the MAX3232's TTL output (it idles at 3.3 V) must
land on GP5, not GP4.

| OLED | Pico pin |
|------|----------|
| VCC  | 3V3 (pin 36) |
| GND  | GND (pin 3) |
| SDA  | GP2 (pin 4) |
| SCL  | GP3 (pin 5) |

The top line shows the IP address; below it is a scrolling log (network, IMEI, results, errors)
plus all RockBLOCK UART traffic: `>` = AT command sent, `<` = modem reply, `<?` = unexpected
bytes. Garbage after `<` usually means wrong baud rate, swapped TX/RX or missing MAX3232.
Set `AT_DEBUG = False` in `main.py` to hide the UART traffic. Without a display everything
still goes to serial.

## Setup
1. Flash MicroPython for the board: https://micropython.org/download/W5500_EVB_PICO/
2. Install the OLED driver: `mpremote mip install ssd1306`
3. Copy the scripts: `mpremote cp console.py : + cp main.py :`
4. Plug in Ethernet, reset, and open http://192.168.0.69 (static IP set at the top of `main.py`).

Sends and mailbox checks can take up to a minute. Messages are kept in memory only.
