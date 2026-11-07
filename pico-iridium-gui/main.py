# Super-basic Iridium web GUI for the W5500-EVB-Pico (MicroPython)
# RockBLOCK on UART1: GP4 = Pico TX, GP5 = Pico RX
# RockBLOCK+ uses RS-232 levels: put a MAX3232 between it and the Pico.
# Optional SSD1306 OLED debug console on I2C1: GP2 = SDA, GP3 = SCL (see console.py)
import network, socket, time, math
from machine import Pin, SPI, UART
from console import log, header

header("Iridium booting")
log("Starting...")

# --- Ethernet (W5500 on SPI0) ---
spi = SPI(0, 2_000_000, mosi=Pin(19), miso=Pin(16), sck=Pin(18))
nic = network.WIZNET5K(spi, Pin(17), Pin(20))
nic.active(True)
# Static IP: (address, subnet mask, gateway, DNS)
IP, MASK, GATEWAY, DNS = "192.168.0.69", "255.255.255.0", "192.168.0.1", "192.168.0.1"
log("Ethernet: static %s" % IP)
nic.ifconfig((IP, MASK, GATEWAY, DNS))
ip = nic.ifconfig()[0]
header(ip)
log("Open http://%s" % ip)

# --- Iridium modem ---
uart = UART(1, 19200, tx=Pin(4), rx=Pin(5), rxbuf=512)
msgs = []     # (direction, text, result), newest first
terminal = [] # (AT command, reply) typed on the web page, newest first
note = ""     # result of the last action, shown once
AT_DEBUG = True  # show every AT command (>) and modem reply (<) on the console


def txt(b):
    try:
        return b.decode()
    except Exception:
        return str(b)


def at(cmd, wait=5):
    """Send an AT command, return the reply text (waits for OK/ERROR or timeout)."""
    junk = uart.read()
    if junk and AT_DEBUG:
        log("<?" + oneline(txt(junk)))  # unsolicited/leftover bytes
    if AT_DEBUG:
        log(">" + cmd)
    uart.write(cmd + "\r")
    end = time.ticks_add(time.ticks_ms(), wait * 1000)
    buf = b""
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if uart.any():
            buf += uart.read()
            if b"OK\r\n" in buf or b"ERROR" in buf:
                break
        time.sleep_ms(20)
    reply = txt(buf)
    if AT_DEBUG:
        log("<" + (oneline(reply) or "(no reply)"))
    return reply


def oneline(s):
    """Collapse a multi-line modem reply to one line for the OLED."""
    return " ".join(l.strip() for l in s.split("\n") if l.strip())


def field(reply, prefix):
    for line in reply.split("\r\n"):
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def session():
    """Run an SBD session (sends the outgoing buffer, downloads any waiting message)."""
    v = field(at("AT+SBDIX", 120), "+SBDIX:")
    if not v:
        return "no reply from modem"
    mo, momsn, mt, mtmsn, mtlen, queued = [int(x) for x in v.split(",")]
    if mt == 1:
        r = at("AT+SBDRT", 5)
        msg = r.split("+SBDRT:", 1)[-1].rsplit("\r\nOK", 1)[0].strip()
        msgs.insert(0, ("IN", msg, "received"))
        log("RX: " + msg)
    result = "OK" if mo <= 4 else "failed (code %d)" % mo
    if queued:
        result += ", %d more waiting" % queued
    return result


def send(text):
    if "OK" not in at("AT+SBDWT=" + text):
        return "modem refused the message"
    result = session()
    msgs.insert(0, ("OUT", text, result))
    return "Send: " + result


def check():
    log("Mailbox check")
    at("AT+SBDD0")  # clear the outgoing buffer so nothing is re-sent
    return "Mailbox check: " + session()


def raw_at(cmd):
    """Run a user-typed AT command; long timeout for commands that open a satellite session."""
    slow = any(k in cmd.upper() for k in ("SBDI", "CSQ"))
    reply = at(cmd, 90 if slow else 10)
    terminal.insert(0, (cmd, reply.strip() or "(no reply)"))
    del terminal[10:]


def position():
    """Rough lat/lon from the Iridium network (AT-MSGEO). The 9602 has no GPS:
    this is the network's estimate, updated when the modem talks to a satellite,
    and can be off by tens of km. Returns (lat, lon, age_seconds or None) or None."""
    g = field(at("AT-MSGEO", 3), "-MSGEO:")
    try:
        x, y, z, stamp = [v.strip() for v in g.split(",")]
        x, y, z = int(x), int(y), int(z)  # Earth-centred coordinates in km
    except Exception:
        return None
    if not (x or y or z):
        return None
    r = math.sqrt(x * x + y * y + z * z)
    lat = math.asin(z / r) * 180 / math.pi
    lon = math.atan2(y, x) * 180 / math.pi
    try:  # both are Iridium system time, 90 ms ticks
        age = (int(field(at("AT-MSSTM", 3), "-MSSTM:"), 16) - int(stamp, 16)) * 90 // 1000
    except Exception:
        age = None  # no network time available right now
    return lat, lon, age


def ago(s):
    if s is None:
        return "age unknown"
    if s < 120:
        return "%d s old" % s
    if s < 7200:
        return "%d min old" % (s // 60)
    return "%d h old" % (s // 3600)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def page():
    global note
    ok = "OK" in at("AT", 2)
    csq = field(at("AT+CSQ", 15), "+CSQ:") if ok else None
    pos = position() if ok else None
    if pos:
        lat, lon, age = pos
        where = ('%.3f, %.3f <small>(Iridium estimate, rough, %s) '
                 '<a href="https://www.openstreetmap.org/?mlat=%.4f&amp;mlon=%.4f#map=9/%.4f/%.4f">map</a></small>'
                 % (lat, lon, ago(age), lat, lon, lat, lon))
    else:
        where = "? <small>(no Iridium fix yet)</small>"
    rows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (d, esc(t), esc(r))
                   for d, t, r in msgs[:20])
    term = "".join("<b>&gt; %s</b>\n%s\n\n" % (esc(c), esc(r)) for c, r in terminal)
    html = """<!doctype html><html><head><meta name=viewport content="width=device-width">
<title>Iridium</title></head><body style="font-family:sans-serif;max-width:600px;margin:auto;padding:10px">
<h2>Iridium modem</h2>
<p>Modem: <b>%s</b><br>Signal: <b>%s / 5</b><br>Position: %s<br>IMEI: %s</p>
<p><i>%s</i></p>
<form method=post action=/send><input name=msg maxlength=120 style="width:70%%"> <button>Send</button></form>
<p><small>Sending or checking can take up to a minute.</small></p>
<form method=post action=/check><button>Check for messages</button></form>
<h3>Messages</h3><table border=1 cellpadding=4 style="border-collapse:collapse">%s</table>
<h3>AT command</h3>
<form method=post action=/at><input name=cmd value="AT" autocapitalize=characters style="width:70%%;font-family:monospace"> <button>Run</button></form>
<p><small>Sent to the modem as typed. AT+SBDI* commands can take up to 90 s. Newest first.</small></p>
<pre style="background:#eee;padding:8px;white-space:pre-wrap">%s</pre>
<p><a href=/>Refresh</a></p></body></html>""" % (
        "connected" if ok else "NOT RESPONDING", csq or "?", where, imei, esc(note), rows, term)
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
log("Modem setup...")
for c in ("ATE0", "AT&K0", "AT&D0"):
    at(c)
imei = "?"
for line in at("AT+CGSN").split("\r\n"):
    if line.strip().isdigit():
        imei = line.strip()
log("IMEI " + imei if imei != "?" else "Modem: no reply!")

# --- Web server ---
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 80))
s.listen(2)
log("Web server ready")

while True:
    c, _ = s.accept()
    c.settimeout(5)  # don't hang on idle browser connections
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
            log(note)
            c.sendall(b"HTTP/1.0 303 See Other\r\nLocation: /\r\n\r\n")
        elif method == b"POST" and path == b"/at":
            cmd = form_value(body, b"cmd").strip()
            if cmd:
                raw_at(cmd)
            c.sendall(b"HTTP/1.0 303 See Other\r\nLocation: /\r\n\r\n")
        elif path == b"/":
            c.sendall(b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n" + page().encode())
        else:
            c.sendall(b"HTTP/1.0 404 Not Found\r\n\r\n")
    except Exception as e:
        log("ERR:", e)
    c.close()
