# AirFare setup: Python (if it's missing), AirFare's own Python environment and packages, the AirFare launcher,
# shortcuts (desktop, Start menu, Startup), then a health check. AirFare.exe runs this the first time it starts;
# you can also run it yourself from the AirFare folder:  powershell -ExecutionPolicy Bypass -File .\install.ps1
# -Quiet: no questions and no Settings page at the end (for scripted installs).
param([switch]$Quiet)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location -LiteralPath $root      # -LiteralPath everywhere: a folder name may contain [ or ]
$Host.UI.RawUI.WindowTitle = "AirFare setup"

function Step([string]$text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Done([int]$code) {
    if (-not $Quiet) { Write-Host ""; try { Read-Host "Press Enter to close this window" | Out-Null } catch { } }
    exit $code
}
function Fail([string]$text) { Write-Host ""; Write-Host $text -ForegroundColor Red; Done 1 }

# Run a program and judge it by its exit code alone. (In Windows PowerShell with "Stop", a program that only
# prints a warning would count as failed.)
function Invoke-Native([string]$exe, [string[]]$arguments) {
    $ErrorActionPreference = "Continue"
    try {
        $out = & $exe @arguments 2>$null
        return @{ Code = $LASTEXITCODE; Out = "$out".Trim() }
    } catch {
        return @{ Code = -1; Out = "" }
    }
}

# A Python 3.12+ interpreter: the py launcher, python on PATH, or a per-user install (where winget puts it).
function Find-Python {
    $probe = "import sys; print(sys.executable if sys.version_info >= (3, 12) else '')"
    $tries = @()
    foreach ($v in "3.14", "3.13", "3.12") { $tries += , @("py", "-$v") }
    $tries += , @("python")
    foreach ($exe in Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe", "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending) {
        $tries += , @($exe.FullName)
    }
    foreach ($t in $tries) {
        $r = Invoke-Native $t[0] (@($t | Select-Object -Skip 1) + @("-c", $probe))
        if ($r.Code -eq 0 -and $r.Out) { return $r.Out }
    }
    return $null
}

try {
    Write-Host "Setting up AirFare in $root"

    # Some packages nest files about 150 characters deep, and Windows refuses paths over 260 characters
    # unless long paths are switched on.
    $long = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -ErrorAction SilentlyContinue).LongPathsEnabled -eq 1
    if ($root.Length -gt 100 -and -not $long) {
        Fail ("This folder's path is too long for Windows ($($root.Length) characters):`n  $root`n" +
              "Move the AirFare folder somewhere shorter, such as Documents\AirFare or C:\AirFare, and start AirFare.exe again.")
    }

    # Files unzipped from a download or copied from another PC carry a "from the internet" mark that makes Windows
    # warn about the launcher and scripts every time. They come from this folder, so clear it.
    $skip = @("$root\.venv\", "$root\data\")
    Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $f = $_.FullName; -not ($skip | Where-Object { $f.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) }) } |
        Unblock-File -ErrorAction SilentlyContinue

    Step "Python"
    $python = Find-Python
    if (-not $python) {
        Write-Host "AirFare needs Python 3.12 or newer, and it isn't installed on this PC."
        if (-not $Quiet -and (Get-Command winget -ErrorAction SilentlyContinue)) {
            Write-Host "AirFare can install Python 3.13 (free, from python.org) with Windows' winget. That accepts"
            Write-Host "Python's license and the winget source terms: https://docs.python.org/3/license.html"
            $answer = Read-Host "Install Python 3.13 now? [Y/n]"
            if ($answer -eq "" -or $answer -match "^[yY]") {
                winget install --exact --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
                $python = Find-Python
            }
        }
        if (-not $python) {
            Fail "Install Python from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then start AirFare.exe again."
        }
    }
    Write-Host "Using $python"

    Step "AirFare's Python environment"
    $venvPy = Join-Path $root ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPy) {
        # A .venv copied from another PC points at that PC's Python; start a fresh one if this one doesn't run.
        if ((Invoke-Native $venvPy @("-c", "import sys")).Code -ne 0) {
            Write-Host "The existing environment doesn't work here; making a new one."
            Remove-Item -LiteralPath (Join-Path $root ".venv") -Recurse -Force
        } elseif (-not (Test-Path -LiteralPath (Join-Path $root ".venv\Scripts\pythonw.exe"))) {
            # pythonw.exe (Python without a console window) went missing: put the environment's launchers back.
            Write-Host "Restoring pythonw.exe in the environment."
            & $python -m venv --upgrade (Join-Path $root ".venv")
        }
    }
    if (-not (Test-Path -LiteralPath $venvPy)) {
        & $python -m venv (Join-Path $root ".venv")
        if (-not (Test-Path -LiteralPath $venvPy)) { Fail "Couldn't create AirFare's Python environment in $root\.venv." }
    }
    Write-Host "Installing packages. This takes a few minutes (the Claude Agent SDK is about 130 MB)..."
    & $venvPy -m pip install --upgrade pip --quiet --disable-pip-version-check
    & $venvPy -m pip install -r (Join-Path $root "requirements.txt") --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { Fail "Installing packages failed. Check the internet connection and start AirFare.exe again." }

    Step "Launcher and shortcuts"
    $launcher = Join-Path $root "AirFare.exe"
    if (-not (Test-Path -LiteralPath $launcher)) {
        try { & (Join-Path $root "launcher\build.ps1") } catch { Write-Host "Couldn't build AirFare.exe: $_" -ForegroundColor Yellow }
    }
    $shell = New-Object -ComObject WScript.Shell
    function New-Shortcut([string]$path, [string]$arguments, [string]$description) {
        $s = $shell.CreateShortcut($path)
        if (Test-Path -LiteralPath $launcher) {
            $s.TargetPath = $launcher
            $s.Arguments = $arguments
            $s.IconLocation = "$launcher,0"
        } else {
            # No launcher: point at Python directly (Windows then lists the startup entry as Python).
            $s.TargetPath = Join-Path $root ".venv\Scripts\pythonw.exe"
            $s.Arguments = "-m airfare " + @{ "--service" = "service"; "" = "setup" }[$arguments]
            $s.IconLocation = (Join-Path $root "assets\airfare.ico") + ",0"
        }
        $s.WorkingDirectory = $root
        $s.Description = $description
        $s.Save()
        Write-Host "Added $path"
    }
    New-Shortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "AirFare.lnk") "" "AirFare: flights, settings and prices"
    New-Shortcut (Join-Path ([Environment]::GetFolderPath("Programs")) "AirFare.lnk") "" "AirFare: flights, settings and prices"
    New-Shortcut (Join-Path ([Environment]::GetFolderPath("Startup")) "AirFare.lnk") "--service" "AirFare: checks flight prices at startup and on its schedule"
    $old = Join-Path ([Environment]::GetFolderPath("Desktop")) "AirFare Settings.lnk"
    if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old; Write-Host "Removed the old shortcut $old" }
    # Notifications show as AirFare, and airfare: links (from notifications and saved pages) open AirFare.
    & $venvPy -c "from airfare import links, notify; notify.app_id(); links.register()"

    Step "Health check"
    & $venvPy -m airfare doctor

    Write-Host ""
    if ($Quiet) { Write-Host "AirFare is installed." -ForegroundColor Green; exit 0 }
    Write-Host "AirFare is installed. Its Settings page is opening in your browser." -ForegroundColor Green
    Write-Host "There, in this order:"
    Write-Host "  1. AI analyst: log in to Claude or ChatGPT, paste an API key, or choose 'No analyst'."
    Write-Host "  2. Price sources: load the browser extension (steps shown there) and/or paste a SerpApi key."
    Write-Host "  3. Add your flights, press Save, then Test links."
    Write-Host "Later, open AirFare from its desktop or Start menu icon. It checks prices by itself at every PC start."
    # Process.Start, not Start-Process: it takes the path literally even with [ ] in a folder name.
    $open = if (Test-Path -LiteralPath $launcher) { New-Object Diagnostics.ProcessStartInfo($launcher, "--settings") }
            else { New-Object Diagnostics.ProcessStartInfo((Join-Path $root ".venv\Scripts\pythonw.exe"), "-m airfare setup") }
    $open.WorkingDirectory = $root
    $open.UseShellExecute = $false
    [void][Diagnostics.Process]::Start($open)
    Done 0
} catch {
    Fail "Setup stopped: $_"
}
