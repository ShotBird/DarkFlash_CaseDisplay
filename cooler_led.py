"""Thermalright FROZEN HORIZON 360 Digital cooler LED (USB HID 0416:8001), replaces TRCC.

Protocol (from TRCC 2.1.6, see docs\\PROTOCOL_COOLER.md):
  report = 0x00 + 64 bytes. handshake: DA DB DC DD, byte12=1 -> reply byte6 = model (64 here), byte5 = sub.
  frame:   DA DB DC DD, byte12=2, byte16=90, then 30 LEDs x RGB (x0.4), split into 64-byte reports.
  The cooler only stays lit while frames keep coming (TRCC resends on a timer) -> send every ~0.5 s.
LED map (style 1): 0,1 logo, 2,3 CPU, 4,5 GPU, 6 degC, 7 degF, 8 %, 9-15 / 16-22 / 23-29 = digits 1-3 segments A-G.
"""
import threading, time
import hid

VID, PID, N = 0x0416, 0x8001, 30
SEG = {'0': 'ABCDEF', '1': 'BC', '2': 'ABDEG', '3': 'ABCDG', '4': 'BCFG', '5': 'ACDFG',
       '6': 'ACDEFG', '7': 'ABC', '8': 'ABCDEFG', '9': 'ABCDFG', '-': 'G', ' ': ''}
ICON = {'cpu': (2, 3), 'gpu': (4, 5), 'c': (6,), 'f': (7,), 'pct': (8,), 'logo': (0, 1)}


def _hdr(cmd, length=0):
    h = [0xDA, 0xDB, 0xDC, 0xDD] + [0] * 16
    h[12], h[16] = cmd, length
    return h


def leds_for(text, icons):
    on = set()
    for k, ch in enumerate(text.rjust(3)[-3:]):
        for s in SEG.get(ch, ''):
            on.add(9 + 7 * k + 'ABCDEFG'.index(s))
    for i in icons:
        on.update(ICON.get(i, ()))
    return on


def frame(on, color):
    body = []
    for i in range(N):
        body += [int(v * 0.4) for v in color] if i in on else [0, 0, 0]
    return _hdr(2, N * 3) + body


class CoolerLed:
    """Own thread: independent of the case LCD loop (which runs every 2 s)."""

    def __init__(self, log, get_cfg, is_dark, read_value):
        self.log, self.get_cfg, self.is_dark, self.read_value = log, get_cfg, is_dark, read_value
        self.dev, self.stop = None, threading.Event()
        threading.Thread(target=self._run, name="cooler_led", daemon=True).start()

    def _open(self):
        d = hid.device(); d.open(VID, PID)
        d.write(b'\x00' + bytes(_hdr(1)) + b'\x00' * 44)
        r = d.read(64, 2000)
        if not r or r[:4] != [0xDA, 0xDB, 0xDC, 0xDD]:
            d.close(); raise OSError("cooler handshake: no reply")
        self.log(f"cooler connected model={r[6]} sub={r[5]}")
        return d

    def _send(self, payload):
        buf = bytes(payload)
        for i in range(0, len(buf), 64):
            c = buf[i:i + 64]
            if self.dev.write(b'\x00' + c + b'\x00' * (64 - len(c))) < 0:
                raise OSError("cooler write failed")

    def close(self):
        try:
            if self.dev:
                self._send(frame(set(), (0, 0, 0))); self.dev.close()
        except Exception:
            pass
        self.dev = None

    def _run(self):
        value, last_read, dark_logged = None, 0.0, False
        while not self.stop.is_set():
            cfg = (self.get_cfg() or {}).get("cooler", {})
            period = float(cfg.get("interval_seconds", 0.5))
            try:
                if not cfg.get("enabled", False):
                    if self.dev:
                        self.close(); self.log("cooler disabled")
                    self.stop.wait(2); continue
                if self.is_dark():                          # monitors asleep / locked / session end: stop sending -> LEDs go dark
                    if self.dev and not dark_logged:
                        self._send(frame(set(), (0, 0, 0))); self.log("cooler off (screen off)"); dark_logged = True
                    self.stop.wait(1); continue
                if dark_logged:
                    dark_logged = False; self.log("cooler on")
                if self.dev is None:
                    self.dev = self._open()
                now = time.time()
                if now - last_read >= float(cfg.get("read_seconds", 1.0)):
                    value, last_read = self.read_value(cfg.get("source", "CPU Temperature")), now
                text = "---" if value is None else str(max(-99, min(999, int(round(value)))))
                on = leds_for(text, cfg.get("icons", ["cpu", "c"]))
                self._send(frame(on, tuple(cfg.get("color", [255, 255, 255]))))
            except Exception as e:
                self.log(f"cooler error: {e} - retry in 5s")
                try:
                    if self.dev: self.dev.close()
                except Exception:
                    pass
                self.dev = None; self.stop.wait(5); continue
            self.stop.wait(period)
