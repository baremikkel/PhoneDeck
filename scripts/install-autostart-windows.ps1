# Starter PhoneDeck automatisk, når du logger ind på Windows (uden et konsolvindue).
#
#   powershell -ExecutionPolicy Bypass -File scripts\install-autostart-windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install-autostart-windows.ps1 -Remove
#
# Lægger en genvej i din Startup-mappe, der kører  pythonw -m phonedeck  i projektmappen.
param([switch]$Remove)
$ErrorActionPreference = "Stop"

$startup = [Environment]::GetFolderPath("Startup")
$link = Join-Path $startup "PhoneDeck.lnk"

if ($Remove) {
    if (Test-Path $link) { Remove-Item $link; Write-Host "Autostart fjernet." } else { Write-Host "Der var ingen autostart." }
    exit 0
}

$repo = Split-Path -Parent $PSScriptRoot
$pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $pythonw) {
    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($py) { $pythonw = Join-Path (Split-Path $py) "pythonw.exe" }
}
if (-not $pythonw -or -not (Test-Path $pythonw)) {
    Write-Error "Fandt ikke pythonw.exe – installer Python 3.11+ fra python.org (sæt flueben ved 'Add to PATH')."
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($link)
$s.TargetPath = $pythonw
$s.Arguments = "-m phonedeck"
$s.WorkingDirectory = $repo
$s.Description = "PhoneDeck – dashboard på telefonen"
$s.Save()

Write-Host "Autostart lagt i $link"
Write-Host "Start PhoneDeck nu med:  pythonw -m phonedeck   (eller log ud og ind)"
