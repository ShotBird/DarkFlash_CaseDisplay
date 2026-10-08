"""Gigabyte motherboard RGB (RGB Fusion 2 USB, ITE IT5711 048D:5711) without GCC.

Source of truth: GCC's own code (decompiled RgbMotherboard.dll MCU_8297.SetLedEffect / write_to_mcu / Apply /
TurnOffLed / Enable_DLedStripCtrl, GCC 26.08.28.01, rgbMotherboard 26.08.27.01), cross-checked with OpenRGB
Controllers/GigabyteRGBFusion2USBController (same packet layout, same apply command).

Transport: 64-byte HID feature reports, report id 0xCC, on the usage_page 0xFF89 / usage 0xCC collection.
  CC 60           info request; get_feature_report returns "IT5711-GIGABYTE V1.0.29.6" (checked before writing)
  CC 32 00        builtin effects on for every ARGB header (GCC Enable_DLedStripCtrl(31, false))
  CC 20 <effect>  effect for all zones: [2..5] zone mask 0x07FF, [11] mode, [12] max brightness, [13] min,
                  [14..17] color 0x00RRGGBB LE, [22..29] 4 x u16 timings, [30] CtrlVal0 [31] CtrlVal1 [32] CtrlOem0
  CC 28 FF 07     apply to all zones (GCC Apply(-1) on IT5711)
Only whole-board hardware effects are ported. Not ported on purpose: per-zone colors (zone layout of this board
unknown), ARGB software effects (GCC drives them from a thread), wave/scene/beat modes, BIOS sleep-LED option.

config.json "mobo": {"enabled": true = CaseDisplay owns the board (false = leave it to GCC),
                     "effect": off|static|pulse|flash|dflash|cycle, "color": [r,g,b],
                     "brightness": 0-8 (GCC level; 0 = GCC Min), "speed": 0-9 (0 = slowest),
                     "off_when_dark": true = off while the PC sleeps / monitors are off, effect back on wake}
The controller keeps an effect on its own, so it is sent only on change, at start, and after the PC wakes up.
PC sleep: casedisplay calls suspend_now() from PBT_APMSUSPEND so the board is dark before Windows suspends.
"""
import threading, time
import hid

VID, PID, RID = 0x048D, 0x5711, 0xCC
ZONES = 0x07FF                                         # IT5711: 11 zones
EFFECTS = ("off", "static", "pulse", "flash", "dflash", "cycle")

# tables copied from MCU_8297 (index = GCC level)
LEVEL = (26, 51, 77, 102, 128, 153, 179, 204, 255)     # LedBrightness[0..8]
PULSE = ((1600, 1600, 200), (1400, 1400, 200), (1200, 1200, 200), (1000, 1000, 200), (900, 900, 200),
         (800, 800, 200), (700, 700, 200), (600, 600, 200), (500, 500, 200), (400, 400, 200))
FLASH = ((100, 100, 2400), (100, 100, 2200), (100, 100, 2000), (100, 100, 1800), (100, 100, 1600),
         (100, 100, 1400), (100, 100, 1200), (100, 100, 1000), (100, 100, 800), (100, 100, 600))
DFLASH = ((100, 100, 2600), (100, 100, 2400), (100, 100, 2200), (100, 100, 2000), (100, 100, 1800),
          (100, 100, 1600), (100, 100, 1400), (100, 100, 1200), (100, 100, 1000), (100, 100, 800))
CYCLE = ((2400, 2200), (1100, 900), (1000, 800), (900, 700), (800, 600),
         (700, 500), (600, 400), (500, 300), (400, 200), (300, 100))


def _clamp(v, lo, hi):
    return max(lo, min(hi, int(v)))


def effect_packet(effect, color=(255, 255, 255), brightness=0, speed=5):
    """64-byte CC 20 report, field values exactly as MCU_8297.SetLedEffect builds them."""
    if effect not in EFFECTS:
        raise ValueError(f"unknown effect {effect!r}")
    lv, sp = _clamp(brightness, 0, 8), _clamp(speed, 0, 9)
    r, g, b = (_clamp(v, 0, 255) for v in color)
    mode, maxb, t, cv0, cv1, oem0 = 1, LEVEL[lv], (0, 0, 0), 0, 0, 0
    if effect == "off":                                # TurnOffLed(): Static, color 0, level 9 -> capped 8
        mode, maxb, r, g, b = 1, LEVEL[8], 0, 0, 0
    elif effect == "pulse":                            # GCC ignores the level for Pulse (fixed 100)
        mode, maxb, t, cv1 = 2, 100, PULSE[sp], 1
    elif effect == "flash":
        mode, t, cv1, oem0 = 3, FLASH[sp], 1, 1
    elif effect == "dflash":                           # DFlash = Flash mode with CtrlOem0 = 2
        mode, t, cv1, oem0 = 3, DFLASH[sp], 1, 2
    elif effect == "cycle":
        mode, t, cv0 = 4, CYCLE[sp] + (0,), 7
    p = [0] * 64
    p[0], p[1] = RID, 0x20
    p[2:6] = ZONES.to_bytes(4, "little")
    p[11], p[12], p[13] = mode, maxb, 0
    p[14:18] = ((r << 16) | (g << 8) | b).to_bytes(4, "little")
    for i, v in enumerate(t):
        p[22 + 2 * i:24 + 2 * i] = v.to_bytes(2, "little")
    p[30], p[31], p[32] = cv0, cv1, oem0
    return p


STRIPS_BUILTIN = [RID, 0x32, 0x00] + [0] * 61
APPLY_ALL = [RID, 0x28, 0xFF, 0x07] + [0] * 60


def _path():
    for d in hid.enumerate(VID, PID):
        if d["usage_page"] == 0xFF89 and d["usage"] == 0xCC:
            return d["path"]
    raise OSError("mobo RGB controller 048D:5711 not found")


def _lamparray(rgb):
    """Windows LampArray interface (usage page 0x59) of the same chip.
    09-29: after a boot without GCC, Windows Dynamic Lighting (background controller) held the chip in host mode;
    the chip then ignores CC 20 and keeps the LampArray color (stuck white full). CC 20 alone stopped working,
    LampArray host mode + range update worked (board went dark). So every state is also sent here:
    AutonomousMode=0, then LampRangeUpdate (report 5: flags=1, lamps 0..0 = all, R G B intensity)."""
    for d in hid.enumerate(VID, PID):
        if d["usage_page"] == 0x59:
            h = hid.device(); h.open_path(d["path"])
            try:
                h.send_feature_report([6, 0]); time.sleep(0.1)
                r, g, b = rgb
                h.send_feature_report([5, 1, 0, 0, 0, 0, r, g, b, 255 if (r or g or b) else 0])
            finally:
                h.close()
            return


LAMP_SOLID = ("off", "static")   # 10-08: only these go through LampArray host mode


def _lamparray_release():
    """Hand the chip back to its own effects (LampArray AutonomousMode=1) so CC 20 effects run.
    10-08: host mode (AutonomousMode=0) made the chip ignore CC 20, so pulse/flash/dflash/cycle all showed as a solid color."""
    for d in hid.enumerate(VID, PID):
        if d["usage_page"] == 0x59:
            h = hid.device(); h.open_path(d["path"])
            try:
                h.send_feature_report([6, 1])
            finally:
                h.close()
            return


def _lamp_hold(effect, color=(255, 255, 255), brightness=0, speed=5):
    """off/static: LampArray host mode + solid color (09-29 guard against Windows grabbing the chip).
    Effects: release the chip so the CC 20 effect is what shows."""
    if effect in LAMP_SOLID:
        _lamparray(_lamp_rgb(effect, color, brightness, speed))
    else:
        _lamparray_release()


def _lamp_rgb(effect, color=(255, 255, 255), brightness=0, speed=5):
    """LampArray has no effects: solid color dimmed by the GCC level; off = black."""
    if effect == "off":
        return (0, 0, 0)
    k = LEVEL[_clamp(brightness, 0, 8)] / 255
    return tuple(int(_clamp(v, 0, 255) * k) for v in color)


def apply(effect, color=(255, 255, 255), brightness=0, speed=5):
    pkt = effect_packet(effect, color, brightness, speed)          # validate before touching the device
    try:
        _lamp_hold(effect, color, brightness, speed)
    except Exception:
        pass
    d = hid.device(); d.open_path(_path())
    try:
        d.send_feature_report([RID, 0x60] + [0] * 62)
        info = bytes(d.get_feature_report(RID, 64))
        if b"IT5711" not in info:
            raise OSError(f"unexpected controller info {info[12:40]!r}")
        for rep in (STRIPS_BUILTIN, pkt, APPLY_ALL):
            if d.send_feature_report(rep) != 64:
                raise OSError("mobo write failed")
        return info[12:40].split(b"\0")[0].decode(errors="replace")
    finally:
        d.close()


def wanted(cfg, dark=False):
    """config 'mobo' -> (effect, color, brightness, speed); None = not ours. dark = sleep / monitors off."""
    if not cfg.get("enabled", False):
        return None
    if dark and cfg.get("off_when_dark", True):
        return ("off", (0, 0, 0), 0, 0)
    eff = cfg.get("effect") or ("static" if cfg.get("on", True) else "off")    # 09-28 'on' key still read
    if eff not in EFFECTS:
        eff = "off"
    col = cfg.get("color", [255, 255, 255])
    col = tuple(_clamp(v, 0, 255) for v in col) if isinstance(col, list) and len(col) == 3 else (255, 255, 255)
    return (eff, col, _clamp(cfg.get("brightness", 0), 0, 8), _clamp(cfg.get("speed", 5), 0, 9))


class MoboLed:
    """Checks config every 2 s; sends on change, and again after a wall-clock gap (sleep/hibernate)."""

    def __init__(self, log, get_cfg, is_dark=lambda: False):
        self.log, self.get_cfg, self.is_dark, self.last = log, get_cfg, is_dark, None
        self.stop, self.lock, self.kick = threading.Event(), threading.Lock(), threading.Event()
        self.resend = []
        threading.Thread(target=self._run, name="mobo_led", daemon=True).start()

    def _send(self, want):
        with self.lock:
            fw = apply(*want)
            self.last = want
            now = time.time()
            self.resend = [now + t for t in (0.7, 2.0)]   # LampArray color only, guards against Windows re-grab
        self.log(f"mobo RGB {want[0]} color={list(want[1])} level={want[2]} speed={want[3]} ({fw})")

    def poke(self):
        self.kick.set()

    def burst(self):
        """Lock/unlock/monitor event: send now, then 3 re-sends within 4 s to beat Windows Dynamic Lighting,
        then nothing (no periodic USB traffic)."""
        self.kick.set()     # 09-29 v2: only check now; re-sends happen only after a real state change (_send)

    def suspend_now(self):
        """Called on the power-watch thread right before Windows sleeps: turn off at once."""
        want = wanted((self.get_cfg() or {}).get("mobo", {}), dark=True)
        if want is not None and want != self.last:
            self._send(want)

    def _run(self):
        tick = time.time()
        while not self.stop.is_set():
            now = time.time()
            if now - tick > 15 and self.last is not None:
                self.log("mobo RGB: wake-up detected - resend"); self.last = None
            tick = now
            want = wanted((self.get_cfg() or {}).get("mobo", {}), dark=bool(self.is_dark()))
            if want is None:
                self.last = None
            elif self.resend and now >= self.resend[0]:   # burst after lock/unlock/monitor event (Windows grabs the chip)
                self.resend.pop(0)
                if want == self.last:     # same state: LampArray color only, no CC 20 effect restart (that blinked)
                    try:
                        with self.lock:
                            _lamp_hold(*want)   # 10-08: effects re-release instead of re-grabbing as solid color
                    except Exception:
                        pass
                else:
                    self.last = None
                continue
            elif want != self.last:
                try:
                    self._send(want)
                except Exception as e:
                    self.log(f"mobo RGB error: {e} - retry in 10s")
                    self.stop.wait(10); continue
            nxt = (self.resend[0] - time.time()) if self.resend else 2
            self.kick.wait(max(0.05, min(2, nxt))); self.kick.clear()   # poke()/burst() wake at once


if __name__ == "__main__":      # manual test: python mobo_led.py <effect> [r g b] [level 0-8] [speed 0-9]
    import sys
    a = sys.argv[1:] or ["off"]
    col = tuple(int(v) for v in a[1:4]) if len(a) >= 4 else (255, 255, 255)
    lv = int(a[4]) if len(a) >= 5 else 0
    sp = int(a[5]) if len(a) >= 6 else 5
    print(apply(a[0], col, lv, sp), a[0], col, lv, sp)
