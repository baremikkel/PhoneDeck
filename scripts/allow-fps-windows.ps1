# Giver din bruger lov til at måle FPS (én gang).
#
#   powershell -ExecutionPolicy Bypass -File scripts\allow-fps-windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\allow-fps-windows.ps1 -Remove
#
# FPS-måleren lytter til Windows' hændelseslog for DirectX (ETW). Det må kun
# administratorer og medlemmer af den indbyggede gruppe "Performance Log Users"
# ("Brugere af ydelseslogfiler", SID S-1-5-32-559). Scriptet sætter din bruger i den
# gruppe – det beder selv om administrator-adgang. Log ud og ind bagefter.
param([switch]$Remove, [string]$UserSid = "")
$ErrorActionPreference = "Stop"
$group = "S-1-5-32-559"

if (-not $UserSid) {
    $UserSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
}

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    # start igen som administrator, men for den bruger der kørte scriptet
    $argv = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-UserSid", $UserSid)
    if ($Remove) { $argv += "-Remove" }
    Start-Process powershell -Verb RunAs -ArgumentList $argv -Wait
    exit
}

$members = Get-LocalGroupMember -SID $group | ForEach-Object { $_.SID.Value }
if ($Remove) {
    if ($members -contains $UserSid) {
        Remove-LocalGroupMember -SID $group -Member $UserSid
        Write-Host "Fjernet fra Performance Log Users."
    } else { Write-Host "Brugeren var ikke med i gruppen." }
} elseif ($members -contains $UserSid) {
    Write-Host "Brugeren har allerede adgang. Har du logget ud og ind siden?"
} else {
    Add-LocalGroupMember -SID $group -Member $UserSid
    Write-Host "Klar. Log ud og ind igen, så virker FPS-måleren."
}
Start-Sleep -Seconds 4
