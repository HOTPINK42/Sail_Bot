# Pico Iridium web GUI

Super-basic web GUI for an Iridium SBD modem (RockBLOCK) on a WIZnet W5500-EVB-Pico.
Shows modem status, signal and IMEI, and lets you send and receive messages from a browser.

## Hardware
- WIZnet W5500-EVB-Pico (Ethernet)
- RockBLOCK on UART1: GP4 = Pico TX, GP5 = Pico RX, common GND
- RockBLOCK+ uses RS-232 levels and a 9–30 V supply: put a MAX3232 between it and the Pico

## Setup
1. Flash MicroPython for the board: https://micropython.org/download/W5500_EVB_PICO/
2. Copy the script: `mpremote cp main.py :main.py`
3. Plug in Ethernet, reset, and open the IP printed on the serial console.

Sends and mailbox checks can take up to a minute. Messages are kept in memory only.
