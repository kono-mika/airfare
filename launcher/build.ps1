# Builds AirFare.exe (the launcher) into the AirFare folder with the C# compiler that ships with Windows.
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File .\launcher\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { $csc = Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe" }
if (-not (Test-Path $csc)) { throw "The .NET Framework C# compiler (csc.exe) wasn't found." }
$out = Join-Path $root "AirFare.exe"
& $csc /nologo /codepage:65001 /target:winexe /optimize+ /debug- "/out:$out" "/win32icon:$(Join-Path $root 'assets\airfare.ico')" `
    /reference:System.Windows.Forms.dll (Join-Path $PSScriptRoot "AirFare.cs")
if ($LASTEXITCODE -ne 0) { throw "Building AirFare.exe failed." }
Write-Host "Built $out"
