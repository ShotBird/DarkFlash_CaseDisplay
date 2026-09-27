"""Gigabyte motherboard RGB (RGB Fusion 2 USB, ITE IT5711 048D:5711) on/off without GCC.

Protocol (from OpenRGB Controllers/GigabyteRGBFusion2USBController, master 2026-09):
  64-byte HID feature reports on the usage-page 0xFF89 / usage 0xCC collection, report id 0xCC.
  CC 60 -> get_feature_report returns "IT5711-GIGABYTE V1.0.29.6" (info).
  effect packet: [0]=CC [1]=header 0x20 (all zones) [2..5]=zone0 mask LE (0x07FF on 5711) [6..9]=zone1
                 [10]=0 [11]=effect (1 static) [12]=max_brightness [13]=min_brightness [14..17]=color0 LE 0x00RRGGBB
  apply: CC 28 FF 07.
Hardware effects persist in the controller, so a state is sent only when it changes (no resend loop).
config.json "mobo": {"enabled": false = leave the board to GCC, "on": bool, "color": [r,g,b], "brightness": 0-255}.
Only one program should drive the board: with "enabled" true, keep GCC's RGB Fusion from re-applying its own effect.
"""
import threading
import hid

VID, PID, RID = 0x048D, 0x5711, 0xCC
ZONES = 0x07FF


def _path():
    for d in hid.enumerate(VID, PID):
        if d["usage_page"] == 0xFF89 and d["usage"] == 0xCC:
            return d["path"]
    raise OSError("mobo RGB controller 048D:5711 not found")


def effect_packet(on, color, brightness):
    r, g, b = (color if on else (0, 0, 0))
    p = [0] * 64
    p[0], p[1] = RID, 0x20
    p[2:6] = ZONES.to_bytes(4, "little")
    p[11] = 1                                  # EFFECT_STATIC (black = off)
    p[12] = max(0, min(255, int(brightness))) if on else 0
    p[14:18] = ((r << 16) | (g << 8) | b).to_bytes(4, "little")
    return p


def apply(on, color=(255, 255, 255), brightness=255):
    d = hid.device(); d.open_path(_path())
    try:
        d.send_feature_report([RID, 0x60] + [0] * 62)
        info = bytes(d.get_feature_report(RID, 64))
        if b"IT57" not in info:
            raise OSError(f"unexpected controller info {info[12:40]!r}")
        for pkt in (effect_packet(on, color, brightness), [RID, 0x28, 0xFF, 0x07] + [0] * 60):
            if d.send_feature_report(pkt) != 64:
                raise OSError("mobo write failed")
        return info[12:40].split(b"\0")[0].decode(errors="replace")
    finally:
        d.close()


class MoboLed:
    """Watches config every 2 s and sends the board state when it changes."""

    def __init__(self, log, get_cfg):
        self.log, self.get_cfg, self.last, self.stop = log, get_cfg, None, threading.Event()
        threading.Thread(target=self._run, name="mobo_led", daemon=True).start()

    def _run(self):
        while not self.stop.is_set():
            cfg = (self.get_cfg() or {}).get("mobo", {})
            if not cfg.get("enabled", False):
                self.last = None
            else:
                want = (bool(cfg.get("on", True)), tuple(cfg.get("color", [255, 255, 255])), int(cfg.get("brightness", 255)))
                if want != self.last:
                    try:
                        fw = apply(*want)
                        self.last = want
                        self.log(f"mobo RGB {'on' if want[0] else 'off'} ({fw})")
                    except Exception as e:
                        self.log(f"mobo RGB error: {e} - retry in 10s")
                        self.stop.wait(10); continue
            self.stop.wait(2)


if __name__ == "__main__":      # manual test: python mobo_led.py on|off [r g b] [brightness]
    import sys
    a = sys.argv[1:] or ["off"]
    col = tuple(int(v) for v in a[1:4]) if len(a) >= 4 else (255, 255, 255)
    br = int(a[4]) if len(a) >= 5 else 255
    print(apply(a[0] == "on", col, br), a[0])
