"""Golden test for mobo_led.effect_packet: bytes must equal what GCC's MCU_8297 builds (no device needed).

Expected layout = DataFormat_8297 marshalled after [0]=0xCC [1]=0x20:
  2-5 Zone_Sel0, 6-9 Zone_Sel1, 10 Reserve0, 11 Mode_Sel, 12 MaxBrightness, 13 MinBrightness,
  14-17 dwColor0, 18-21 dwColor1, 22-29 wTime_base0..3, 30 CtrlVal0, 31 CtrlVal1, 32 CtrlOem0, 33 CtrlOem1.
Run: python tools/test_mobo_led.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mobo_led as m


def gcc(mode, maxb, color, times=(0, 0, 0, 0), cv0=0, cv1=0, oem0=0):
    p = [0] * 64
    p[0], p[1] = 0xCC, 0x20
    p[2:6] = [0xFF, 0x07, 0, 0]                        # Zone_Sel0 = 2047 (IT5711, Divisions -1)
    p[11], p[12] = mode, maxb
    p[14:18] = list(color.to_bytes(4, "little"))
    for i, t in enumerate(times):
        p[22 + 2 * i:24 + 2 * i] = list(t.to_bytes(2, "little"))
    p[30], p[31], p[32] = cv0, cv1, oem0
    return p


CASES = [
    # TurnOffLed(): SetLedEffect(Static, color 0, speed 0, level 9 -> 8) -> MaxBrightness 255
    (("off", (255, 255, 255), 0, 5), gcc(1, 255, 0)),
    # Static, level 0 (GCC Min) = 26, level 8 = 255
    (("static", (255, 255, 255), 0, 5), gcc(1, 26, 0xFFFFFF)),
    (("static", (255, 0, 0), 8, 5), gcc(1, 255, 0xFF0000)),
    (("static", (0x12, 0x34, 0x56), 3, 0), gcc(1, 102, 0x123456)),
    # Pulse speed 0 / 9: PluseTiming, MaxBrightness fixed 100, CtrlVal1 1
    (("pulse", (0, 0, 255), 0, 0), gcc(2, 100, 0x0000FF, (1600, 1600, 200, 0), cv1=1)),
    (("pulse", (0, 0, 255), 8, 9), gcc(2, 100, 0x0000FF, (400, 400, 200, 0), cv1=1)),
    # Flash speed 5, level 6: FlashTiming[5], CtrlVal1 1, CtrlOem0 1
    (("flash", (0, 255, 0), 6, 5), gcc(3, 179, 0x00FF00, (100, 100, 1400, 0), cv1=1, oem0=1)),
    # DFlash speed 2: Mode 3, DFlashTiming[2], CtrlOem0 2
    (("dflash", (0, 255, 0), 1, 2), gcc(3, 51, 0x00FF00, (100, 100, 2200, 0), cv1=1, oem0=2)),
    # ColorCycle speed 0 / 9: CycleTiming, CtrlVal0 7
    (("cycle", (1, 2, 3), 4, 0), gcc(4, 128, 0x010203, (2400, 2200, 0, 0), cv0=7)),
    (("cycle", (1, 2, 3), 4, 9), gcc(4, 128, 0x010203, (300, 100, 0, 0), cv0=7)),
]

fail = 0
for args, want in CASES:
    got = m.effect_packet(*args)
    ok = got == want and len(got) == 64
    fail += not ok
    print("OK  " if ok else "FAIL", args)
    if not ok:
        print("  want", " ".join(f"{b:02X}" for b in want[:34]))
        print("  got ", " ".join(f"{b:02X}" for b in got[:34]))

# clamps and config parsing
assert m.effect_packet("static", (300, -5, 0), 99, 99)[12] == 255
assert m.effect_packet("static", (300, -5, 0), 99, 99)[14:18] == [0, 0, 0xFF, 0]
assert m.wanted({"enabled": False}) is None
assert m.wanted({"enabled": True, "on": False}) == ("off", (255, 255, 255), 0, 5)        # 09-28 config shape
assert m.wanted({"enabled": True, "effect": "bogus"})[0] == "off"                         # unknown -> off, never guess
assert m.wanted({"enabled": True, "effect": "pulse", "color": [1, 2], "brightness": 3, "speed": 9}) == ("pulse", (255, 255, 255), 3, 9)
assert m.wanted({"enabled": True, "effect": "static"}, dark=True) == ("off", (0, 0, 0), 0, 0)          # sleep -> off
assert m.wanted({"enabled": True, "effect": "static", "off_when_dark": False}, dark=True)[0] == "static"
assert m.wanted({"enabled": True, "effect": "static"}, dark=False)[0] == "static"                        # wake -> back on
assert m.wanted({"enabled": False}, dark=True) is None
assert m.effect_packet(*m.wanted({"enabled": True, "effect": "pulse"}, dark=True)) == m.effect_packet("off")
assert m.STRIPS_BUILTIN[:3] == [0xCC, 0x32, 0x00] and len(m.STRIPS_BUILTIN) == 64
assert m.APPLY_ALL[:4] == [0xCC, 0x28, 0xFF, 0x07] and len(m.APPLY_ALL) == 64
try:
    m.effect_packet("wave"); fail += 1; print("FAIL unknown effect accepted")
except ValueError:
    pass
print("ALL OK" if not fail else f"{fail} FAILED")
sys.exit(1 if fail else 0)
