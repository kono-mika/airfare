# Removes AirFare from this PC's startup, desktop, Start menu and notification list, and stops its background
# checker. Your settings, keys, reports and history in .\data are kept: delete the AirFare folder to remove them too.
# Run: right-click uninstall.ps1 > Run with PowerShell
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$links = @(
    (Join-Path ([Environment]::GetFolderPath("Startup")) "AirFare.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "AirFare.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "AirFare Settings.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Programs")) "AirFare.lnk")
)
foreach ($l in $links) {
    if (Test-Path $l) { Remove-Item $l; Write-Host "Removed $l" }
}
$key = "HKCU:\Software\Classes\AppUserModelId\AirFare.FlightPrices"
if (Test-Path $key) { Remove-Item $key -Recurse; Write-Host "Removed AirFare from the notification senders" }
$protocol = "HKCU:\Software\Classes\airfare"
if (Test-Path $protocol) { Remove-Item $protocol -Recurse; Write-Host "Removed airfare: links" }

# AirFare's own Python processes (background checker, settings server) run from this folder's .venv.
$venv = (Join-Path $root ".venv").ToLower()
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object {
    $_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($venv) -or ($_.CommandLine -and $_.CommandLine.ToLower().Contains($venv) -and $_.CommandLine -match "-m airfare")
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host "Stopped AirFare process $($_.ProcessId)" }

Write-Host ""
Write-Host "AirFare no longer runs at startup. To remove everything, delete the folder $root"
Write-Host "In your browser, you can also remove 'AirFare collector' from its extensions page (about:addons in Firefox)."
Read-Host "Press Enter to close" | Out-Null
