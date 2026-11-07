# Super-basic Iridium web GUI for the W5500-EVB-Pico (MicroPython)
# RockBLOCK on UART1: GP4 = Pico TX, GP5 = Pico RX
# RockBLOCK+ uses RS-232 levels: put a MAX3232 between it and the Pico.
import network, socket, time
from machine import Pin, SPI, UART

# --- Ethernet (W5500 on SPI0) ---
spi = SPI(0, 2_000_000, mosi=Pin(19), miso=Pin(16), sck=Pin(18))
nic = network.WIZNET5K(spi, Pin(17), Pin(20))
nic.active(True)
nic.ifconfig("dhcp")
print("Open http://%s" % nic.ifconfig()[0])

# --- Iridium modem ---
uart = UART(1, 19200, tx=Pin(4), rx=Pin(5), rxbuf=512)
log = []      # (direction, text, result), newest first
note = ""     # result of the last action, shown once


def txt(b):
    try:
        return b.decode()
    except Exception:
        return str(b)


def at(cmd, wait=5):
    """Send an AT command, return the reply text (waits for OK/ERROR or timeout)."""
    uart.read()
    uart.write(cmd + "\r")
    end = time.ticks_add(time.ticks_ms(), wait * 1000)
    buf = b""
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if uart.any():
            buf += uart.read()
            if b"OK\r\n" in buf or b"ERROR" in buf:
                break
        time.sleep_ms(20)
    return txt(buf)


def field(reply, prefix):
    for line in reply.split("\r\n"):
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def session():
    """Run an SBD session (sends the outgoing buffer, downloads any waiting message)."""
    v = field(at("AT+SBDIX", 60), "+SBDIX:")
    if not v:
        return "no reply from modem"
    mo, momsn, mt, mtmsn, mtlen, queued = [int(x) for x in v.split(",")]
    if mt == 1:
        r = at("AT+SBDRT", 5)
        msg = r.split("+SBDRT:", 1)[-1].rsplit("\r\nOK", 1)[0].strip()
        log.insert(0, ("IN", msg, "received"))
    result = "OK" if mo <= 4 else "failed (code %d)" % mo
    if queued:
        result += ", %d more waiting" % queued
    return result


def send(text):
    if "OK" not in at("AT+SBDWT=" + text):
        return "modem refused the message"
    result = session()
    log.insert(0, ("OUT", text, result))
    return "Send: " + result


def check():
    at("AT+SBDD0")  # clear the outgoing buffer so nothing is re-sent
    return "Mailbox check: " + session()


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def page():
    global note
    ok = "OK" in at("AT", 2)
    csq = field(at("AT+CSQ", 15), "+CSQ:") if ok else None
    rows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (d, esc(t), esc(r))
                   for d, t, r in log[:20])
    html = """<!doctype html><html><head><meta name=viewport content="width=device-width">
<title>Iridium</title></head><body style="font-family:sans-serif;max-width:600px;margin:auto;padding:10px">
<h2>Iridium modem</h2>
<p>Modem: <b>%s</b><br>Signal: <b>%s / 5</b><br>IMEI: %s</p>
<p><i>%s</i></p>
<form method=post action=/send><input name=msg maxlength=120 style="width:70%%"> <button>Send</button></form>
<p><small>Sending or checking can take up to a minute.</small></p>
<form method=post action=/check><button>Check for messages</button></form>
<h3>Messages</h3><table border=1 cellpadding=4 style="border-collapse:collapse">%s</table>
<p><a href=/>Refresh</a></p></body></html>""" % (
        "connected" if ok else "NOT RESPONDING", csq or "?", imei, esc(note), rows)
    note = ""
    return html


def form_value(body, key):
    """Get one field from a URL-encoded form body."""
    for part in body.split(b"&"):
        if part.startswith(key + b"="):
            b = part[len(key) + 1:].replace(b"+", b" ")
            out = bytearray()
            i = 0
            while i < len(b):
                if b[i] == 37 and i + 2 < len(b):  # %XX
                    out.append(int(b[i + 1:i + 3].decode(), 16))
                    i += 3
                else:
                    out.append(b[i])
                    i += 1
            return txt(bytes(out))
    return ""


# Modem setup: echo off, no flow control, ignore DTR
for c in ("ATE0", "AT&K0", "AT&D0"):
    at(c)
imei = "?"
for line in at("AT+CGSN").split("\r\n"):
    if line.strip().isdigit():
        imei = line.strip()

# --- Web server ---
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 80))
s.listen(2)

while True:
    c, _ = s.accept()
    try:
        req = c.recv(1024)
        parts = req.split(b"\r\n\r\n", 1)
        head, body = parts[0], parts[1] if len(parts) > 1 else b""
        n = 0
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                n = int(line[15:].decode())
        while len(body) < n:
            more = c.recv(512)
            if not more:
                break
            body += more
        method, path = head.split(b" ")[:2]

        if method == b"POST" and path in (b"/send", b"/check"):
            if path == b"/send":
                text = form_value(body, b"msg").strip()
                note = send(text) if text else "Type a message first"
            else:
                note = check()
            c.sendall(b"HTTP/1.0 303 See Other\r\nLocation: /\r\n\r\n")
        elif path == b"/":
            c.sendall(b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n" + page().encode())
        else:
            c.sendall(b"HTTP/1.0 404 Not Found\r\n\r\n")
    except Exception as e:
        print("error:", e)
    c.close()
