# Builds AirFare.exe (the launcher) into the AirFare folder with the C# compiler that ships with Windows.
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File .\launcher\build.ps1
# -IfStale (install.ps1): only when AirFare.exe is missing, launcher\AirFare.cs is newer than it, or its file version
# differs from airfare\__init__.py's, so source-code installs get the new launcher.
param([switch]$IfStale)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
# A version's numbers, four of them: the file version 1.5.0.0 is the release 1.5.0, as is 1.5.0rc1.
function Get-Release([string]$text) {
    $numbers = @(([regex]::Match("$text", '^\s*\d+(\.\d+)*').Value.Trim() -split '\.') | Where-Object { $_ } | ForEach-Object { [int64]$_ })
    while ($numbers.Count -lt 4) { $numbers += 0 }
    return ($numbers[0..3] -join ".")
}
if ($IfStale) {
    $exe = Join-Path $root "AirFare.exe"
    $source = Join-Path $PSScriptRoot "AirFare.cs"
    if (Test-Path -LiteralPath $exe) {
        $file = Get-Item -LiteralPath $exe
        $found = Select-String -LiteralPath (Join-Path $root "airfare\__init__.py") -Pattern '__version__ = "([^"]+)"'
        $code = if ($found) { $found.Matches[0].Groups[1].Value } else { "" }
        $newer = (Get-Item -LiteralPath $source).LastWriteTimeUtc -gt $file.LastWriteTimeUtc
        if (-not $newer -and (Get-Release $file.VersionInfo.FileVersion) -eq (Get-Release $code)) { exit 0 }
    }
}
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { $csc = Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe" }
if (-not (Test-Path $csc)) { throw "The .NET Framework C# compiler (csc.exe) wasn't found." }
$out = Join-Path $root "AirFare.exe"
& $csc /nologo /codepage:65001 /target:winexe /optimize+ /debug- "/out:$out" "/win32icon:$(Join-Path $root 'assets\airfare.ico')" `
    /reference:System.Windows.Forms.dll (Join-Path $PSScriptRoot "AirFare.cs")
if ($LASTEXITCODE -ne 0) { throw "Building AirFare.exe failed." }
Write-Host "Built $out"
