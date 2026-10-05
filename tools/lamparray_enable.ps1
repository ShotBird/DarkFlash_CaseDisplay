$id = 'HID\VID_048D&PID_5711&MI_00\A&1C89D933&0&0000'
Enable-PnpDevice -InstanceId $id -Confirm:$false
Add-Content -Encoding utf8 'C:\dev\1_PC_Setup\_evidence\lamparray-fix-0929.log' "$(Get-Date -f 'yyyy-MM-dd HH:mm:ss') re-enabled (user: back to LampArray control): $((Get-PnpDevice -InstanceId $id).Status)"
