# Starter PhoneDeck automatisk, når du logger ind på Windows (uden et konsolvindue).
#
#   powershell -ExecutionPolicy Bypass -File scripts\install-autostart-windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install-autostart-windows.ps1 -Remove
#
# Lægger en genvej i din Startup-mappe, der kører  pythonw -m phonedeck  i projektmappen.
#
# NB: filen skal gemmes som UTF-8 *med* BOM – ellers læser Windows PowerShell 5.1
# den som ANSI, og tegn som – og å ødelægger parsingen.
param([switch]$Remove)
$ErrorActionPreference = "Stop"

$startup = [Environment]::GetFolderPath("Startup")
$link = Join-Path $startup "PhoneDeck.lnk"

if ($Remove) {
    if (Test-Path $link) { Remove-Item $link; Write-Host "Autostart fjernet." } else { Write-Host "Der var ingen autostart." }
    exit 0
}

$repo = Split-Path -Parent $PSScriptRoot

# Find pythonw.exe. Først via py-launcheren (findes også når Python ikke er i PATH,
# fx efter  winget install Python.Python.3.13), derefter via PATH.
# Microsoft Store-aliasserne i WindowsApps er ikke rigtige Python-installationer og springes over.
$pythonw = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $ErrorActionPreference = "Continue"
    $exe = & py -3 -c "import sys; print(sys.executable)" 2>$null
    $ErrorActionPreference = "Stop"
    if ($LASTEXITCODE -eq 0 -and $exe) { $pythonw = Join-Path (Split-Path "$exe".Trim()) "pythonw.exe" }
}
if (-not $pythonw -or -not (Test-Path $pythonw)) {
    foreach ($name in "pythonw", "python") {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue |
            Where-Object { $_.Source -notlike "*\WindowsApps\*" } | Select-Object -First 1
        if ($cmd) { $pythonw = Join-Path (Split-Path $cmd.Source) "pythonw.exe"; break }
    }
}
if (-not $pythonw -or -not (Test-Path $pythonw)) {
    Write-Error "Fandt ikke pythonw.exe – installer Python 3.11+ fra python.org (eller: winget install Python.Python.3.13)."
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($link)
$s.TargetPath = $pythonw
$s.Arguments = "-m phonedeck"
$s.WorkingDirectory = $repo
$s.Description = "PhoneDeck – dashboard på telefonen"
$s.Save()

Write-Host "Autostart lagt i $link  (bruger $pythonw)"
Write-Host "Start PhoneDeck nu med:  pyw -m phonedeck   (fra PhoneDeck-mappen, eller log ud og ind)"
