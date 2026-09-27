"""Read-only probe of the Gigabyte RGB Fusion 2 USB controller (ITE 048D:5711). Sends CC 60 (info request) only."""
import hid

for d in hid.enumerate(0x048D, 0x5711):
    print(d['interface_number'], hex(d['usage_page']), hex(d['usage']), d['path'])

for d in hid.enumerate(0x048D, 0x5711):
    try:
        h = hid.device(); h.open_path(d['path'])
        buf = [0xCC, 0x60] + [0] * 62
        w = h.send_feature_report(buf)
        r = h.get_feature_report(0xCC, 64)
        print('path', d['path'], 'send', w, 'got', len(r))
        print(' '.join(f'{b:02X}' for b in r))
        print('ascii', bytes(b if 32 <= b < 127 else 46 for b in r).decode())
        h.close()
    except Exception as e:
        print('path', d['path'], 'ERR', e)
