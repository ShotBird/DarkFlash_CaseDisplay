# hand the chip back to its own effects (LampArray AutonomousMode=1) so CC 20 works again
import hid
for d in hid.enumerate(0x048D, 0x5711):
    if d["usage_page"] == 0x59:
        h = hid.device(); h.open_path(d["path"]); print("autonomous=1", h.send_feature_report([6, 1])); h.close()
