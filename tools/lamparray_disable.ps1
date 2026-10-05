# 09-29: Windows Dynamic Lighting grabs the mobo RGB chip (048D:5711) through its LampArray interface (MI_00)
# on every lock/unlock -> blink / CaseDisplay loses control. Disabling only that interface cuts Windows off;
# CaseDisplay keeps using the vendor interface (MI_01 Col02, CC 20). Undo: Enable-PnpDevice with the same id.
$id = 'HID\VID_048D&PID_5711&MI_00\A&1C89D933&0&0000'
$log = 'C:\dev\1_PC_Setup\_evidence\lamparray-disable-0929.log'
"$(Get-Date -f 'yyyy-MM-dd HH:mm:ss') before: $((Get-PnpDevice -InstanceId $id).Status)" | Out-File $log -Append
Disable-PnpDevice -InstanceId $id -Confirm:$false
"$(Get-Date -f 'yyyy-MM-dd HH:mm:ss') after: $((Get-PnpDevice -InstanceId $id).Status)" | Out-File $log -Append
