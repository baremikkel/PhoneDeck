# Forbinder telefonen over USB og åbner dashboardet på den (Windows).
#
#   powershell -ExecutionPolicy Bypass -File scripts\phone-connect.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\phone-connect.ps1 -Port 9000
#
# Kræver: adb (Android SDK Platform-Tools, fx  winget install Google.PlatformTools)
# og USB-fejlfinding slået til på telefonen.
#
# NB: filen skal gemmes som UTF-8 *med* BOM – ellers læser Windows PowerShell 5.1
# den som ANSI, og tegn som – og å ødelægger parsingen.
param([int]$Port = 8765)
$ErrorActionPreference = "Stop"

if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
    Write-Error "adb mangler – installer med: winget install Google.PlatformTools (og åbn en ny PowerShell bagefter)"
    exit 1
}

Write-Host "Venter på telefonen (godkend 'Tillad USB-fejlfinding' på skærmen) …"
adb wait-for-device

# localhost:$Port på telefonen -> localhost:$Port på PC'en (gennem USB-kablet)
adb reverse "tcp:$Port" "tcp:$Port" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "adb reverse fejlede – tjek 'adb devices' (står telefonen som 'unauthorized', så godkend prompten på telefonen)."
    exit 1
}

# Hold skærmen tændt mens den lader (nogle telefoner nægter – dashboardet holder den vågen selv).
# Windows PowerShell 5.1 gør stderr fra native programmer til fejl, så "Stop" må ikke gælde her.
$ErrorActionPreference = "Continue"
adb shell settings put global stay_on_while_plugged_in 7 2>$null | Out-Null
$stayOnFailed = $LASTEXITCODE -ne 0
$ErrorActionPreference = "Stop"
if ($stayOnFailed) {
    Write-Host "Bemærk: telefonen tillod ikke 'hold skærmen tændt' – slå evt. 'Stay awake' til under Developer options."
}

# Åbn dashboardet; application_id får Chrome til at genbruge samme fane
adb shell am start -a android.intent.action.VIEW -d "http://localhost:$Port" --es com.android.browser.application_id phonedeck | Out-Null

Write-Host "Klar ✔  Tryk på uret på telefonen for fuld skærm."
