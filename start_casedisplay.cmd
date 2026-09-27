@echo off
rem Manual start: LibreHardwareMonitor first, then CaseDisplay (8s later).
rem Safe to run when already running (task setting IgnoreNew).
echo Starting LibreHardwareMonitor...
schtasks /run /tn LibreHardwareMonitor
ping -n 9 127.0.0.1 >nul
echo Starting CaseDisplay...
schtasks /run /tn CaseDisplay
ping -n 3 127.0.0.1 >nul
