@echo off
setlocal

echo Stopping local app...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'Name = ''python.exe''' | Where-Object { $_.CommandLine -match 'iching_alpha\.webapp' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Done.
