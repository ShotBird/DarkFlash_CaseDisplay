$id = 'HID\VID_048D&PID_5711&MI_00\A&1C89D933&0&0000'
$log = 'C:\dev\1_PC_Setup\_evidence\lamparray-fix-0929.log'
function L($m) { Add-Content -Encoding utf8 $log "$(Get-Date -f 'yyyy-MM-dd HH:mm:ss') $m" }
Enable-PnpDevice -InstanceId $id -Confirm:$false; Start-Sleep 10
L ("enabled: " + (Get-PnpDevice -InstanceId $id).Status)
L ("release: " + (& 'C:\Users\hans1\AppData\Local\Programs\Python\Python313\python.exe' 'C:\dev\1_PC_Setup\CaseDisplay\tools\lamparray_release.py' 2>&1))
Start-Sleep 3
L ("cc20: " + (& 'C:\Users\hans1\AppData\Local\Programs\Python\Python313\python.exe' 'C:\dev\1_PC_Setup\CaseDisplay\mobo_led.py' static 255 255 255 0 0 2>&1))
Disable-PnpDevice -InstanceId $id -Confirm:$false
L ("disabled: " + (Get-PnpDevice -InstanceId $id).Status)
