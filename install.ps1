# AirFare setup: Python (if it's missing), AirFare's own Python environment and packages, the AirFare launcher,
# shortcuts (desktop, Start menu, Startup), then a health check. AirFare.exe runs this the first time it starts;
# you can also run it yourself from the AirFare folder:  powershell -ExecutionPolicy Bypass -File .\install.ps1
# -Quiet: no questions and no Settings page at the end (for scripted installs).
# -Upgrade: AirFare.exe found the files of a new release in this folder. The same steps finish the update: the
# previous version's background checker and Settings server stop, files it left behind go (MANIFEST.txt), the
# packages update, the data is backed up and migrated (airfare\migrate.py), and the checker starts again.
# Running this again without -Upgrade does the same; the data folder is never deleted or replaced.
# Only one runs at a time: it holds .venv\airfare-install.lock from start to end, and AirFare.exe and python -m airfare
# say that AirFare is being updated while it does. A copy unzipped inside an AirFare folder stops before anything.
# (This file starts with a UTF-8 mark: without one, Windows PowerShell misreads the Spanish and Russian texts.)
param([switch]$Quiet, [switch]$Upgrade)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location -LiteralPath $root      # -LiteralPath everywhere: a folder name may contain [ or ]
$Host.UI.RawUI.WindowTitle = if ($Upgrade) { "AirFare update" } else { "AirFare setup" }
$version = ""
$found = Select-String -LiteralPath (Join-Path $root "airfare\__init__.py") -Pattern '__version__ = "([^"]+)"' -ErrorAction SilentlyContinue
if ($found) { $version = $found.Matches[0].Groups[1].Value }
# What a failed update says: nothing in the data folder has changed, and how to try again or go back.
$untouched = "Your data is untouched. Fix the problem above and double-click AirFare.exe again, or go back by " +
             "extracting the previous release into the folder that contains this one."
$installLock = $null

function Step([string]$text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Release-Lock { if ($script:installLock) { $script:installLock.Dispose(); $script:installLock = $null } }
function Done([int]$code) {
    Release-Lock       # before waiting for Enter: this window staying open is no reason to hold anything up
    if (-not $Quiet) { Write-Host ""; try { Read-Host "Press Enter to close this window" | Out-Null } catch { } }
    exit $code
}
function Fail([string]$text) { Write-Host ""; Write-Host $text -ForegroundColor Red; Done 1 }

# The language picked in that folder's Settings; before setup, Windows' display language.
function Get-Language([string]$folder) {
    $config = Join-Path $folder "data\config.json"
    if (Test-Path -LiteralPath $config) {
        try {
            $picked = [regex]::Match((Get-Content -LiteralPath $config -Raw -Encoding UTF8), '"language"\s*:\s*"(en|es|ru)"')
            if ($picked.Success) { return $picked.Groups[1].Value }
        } catch { }
    }
    $ui = (Get-UICulture).TwoLetterISOLanguageName
    if ($ui -eq "es" -or $ui -eq "ru") { return $ui }
    return "en"
}
function Pick-Text([string]$language, [string]$en, [string]$es, [string]$ru) {
    if ($language -eq "es") { return $es }
    if ($language -eq "ru") { return $ru }
    return $en
}

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

# A copy unzipped inside an AirFare folder (the zip has a top-level AirFare folder): stop before anything is
# installed, and leave both folders' data alone.
# (On Windows, where capitals don't count, an inner AirFare folder is the same folder as the outer one's airfare.)
$outer = [IO.Path]::GetDirectoryName($root)
if ($outer -and (Test-Path -LiteralPath (Join-Path $outer "airfare\__init__.py")) -and (Test-Path -LiteralPath (Join-Path $outer "data") -PathType Container)) {
    $language = Get-Language $outer
    $above = [IO.Path]::GetDirectoryName($outer)
    if (-not $above) { $above = $outer }
    $name = [IO.Path]::GetFileName($outer)
    $text = (Pick-Text $language "This copy was unzipped inside your AirFare folder. Delete this inner folder and extract the zip into {0} instead." `
        "Esta copia se descomprimió dentro de tu carpeta de AirFare. Borra esta carpeta interior y extrae el zip en {0}." `
        "Эта копия распакована внутри вашей папки AirFare. Удалите эту внутреннюю папку и извлеките архив в {0}.") -f $above
    if ($name -ne "AirFare") {
        $text += "`n" + ((Pick-Text $language "Your AirFare folder is called {0}. The zip makes a folder called AirFare, so rename yours to AirFare first." `
            "Tu carpeta de AirFare se llama {0}. El zip crea una carpeta llamada AirFare, así que antes cambia el nombre de la tuya a AirFare." `
            "Ваша папка AirFare называется {0}. Архив создаёт папку с именем AirFare, поэтому сначала переименуйте свою в AirFare.") -f $name)
    }
    if (Test-Path -LiteralPath (Join-Path $root "data") -PathType Container) {
        $text += "`n" + (Pick-Text $language "This inner folder has a data folder of its own. If it holds settings or prices you want to keep, move it somewhere safe first." `
            "Esta carpeta interior tiene su propia carpeta data. Si guarda ajustes o precios que quieras conservar, muévela antes a un lugar seguro." `
            "Во внутренней папке есть своя папка data. Если в ней есть нужные настройки или цены, сначала перенесите её в надёжное место.")
    }
    Fail ($text + "`n" + $root)
}

# One installer at a time, for the whole run. Windows lets go of the file if this script dies.
try { [void][IO.Directory]::CreateDirectory((Join-Path $root ".venv")) } catch { }
$lockName = "airfare-install.lock"
for ($try = 1; $try -le 3 -and -not $installLock; $try++) {
    try {
        $installLock = [IO.File]::Open((Join-Path $root ".venv\$lockName"), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch {
        if ($_.Exception.InnerException -isnot [IO.IOException]) { break }     # not "in use": the steps below will say what's wrong
        if ($try -eq 3) {
            Fail (Pick-Text (Get-Language $root) "AirFare is being updated, try again in a few minutes" `
                "AirFare se está actualizando; inténtalo de nuevo en unos minutos" `
                "AirFare обновляется, попробуйте ещё раз через несколько минут")
        }
        Start-Sleep -Milliseconds 300      # someone looking whether it's held has it open for a moment
    }
}

try {
    if ($Upgrade) { Write-Host "Updating AirFare in $root to version $version" } else { Write-Host "Setting up AirFare $version in $root" }

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
            Get-ChildItem -LiteralPath (Join-Path $root ".venv") -Force | Where-Object { $_.Name -ne $lockName } | Remove-Item -Recurse -Force
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
    # A background checker or Settings page still running the previous version holds its files open, and files
    # the previous version had but this one doesn't would stay behind: both are handled before pip runs.
    & $venvPy -m airfare.upgrade prepare
    if ($LASTEXITCODE -ne 0) { Write-Host "Couldn't stop the previous version everywhere; quit AirFare (tray icon, Quit AirFare) if the next step fails." -ForegroundColor Yellow }
    Write-Host "Installing packages. This takes a few minutes (the Claude Agent SDK is about 130 MB)..."
    & $venvPy -m pip install --upgrade pip --quiet --disable-pip-version-check
    & $venvPy -m pip install -r (Join-Path $root "requirements.txt") --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        if ($Upgrade) { Fail "Installing packages failed, so AirFare wasn't updated. Check the internet connection and quit AirFare (tray icon, Quit AirFare). $untouched" }
        Fail "Installing packages failed. Check the internet connection and start AirFare.exe again."
    }

    Step "Your data"
    # Backed up to data\backups first, then brought up to this version's format; on any problem it is put back.
    & $venvPy -m airfare migrate
    if ($LASTEXITCODE -ne 0) { Fail "Updating the data folder failed. $untouched" }
    # From here on the data has been brought up to this version: "untouched" no longer holds.
    $untouched = "Your data is kept and backed up in data\backups. Fix the problem above and double-click AirFare.exe " +
                 "again, or go back by extracting the previous release into the folder that contains this one."

    Step "Launcher and shortcuts"
    $launcher = Join-Path $root "AirFare.exe"
    # Missing, or older than launcher\AirFare.cs or the code's version: source-code installs get the new launcher.
    try { & (Join-Path $root "launcher\build.ps1") -IfStale } catch { Write-Host "Couldn't build AirFare.exe: $_" -ForegroundColor Yellow }
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
    # Records what is installed (AirFare.exe compares it with the code) and starts the background checker again
    # if the settings need it running.
    & $venvPy -m airfare.upgrade finish
    if ($LASTEXITCODE -ne 0) { Fail "Finishing the setup failed. $untouched" }

    Step "Health check"
    & $venvPy -m airfare doctor

    Write-Host ""
    if ($Quiet) { Write-Host "AirFare is installed." -ForegroundColor Green; exit 0 }
    if ($Upgrade) {
        Write-Host "AirFare is updated to version $version. Its Settings page is opening in your browser." -ForegroundColor Green
        Write-Host "Your settings, routes, price history and conversations are kept; the copy made before the update"
        Write-Host "is in data\backups (Clean up lists it)."
        Write-Host "If Settings says the browser runs an older extension, reload it there (Firefox: sign and install the new .xpi)."
    } else {
    Write-Host "AirFare is installed. Its Settings page is opening in your browser." -ForegroundColor Green
    Write-Host "There, in this order:"
    Write-Host "  1. AI analyst: log in to Claude or ChatGPT, paste an API key, or choose 'No analyst'."
    Write-Host "  2. Price sources: load the browser extension (steps shown there) and/or paste a SerpApi key."
    Write-Host "  3. Add your flights, press Save, then Test links."
    Write-Host "Later, open AirFare from its desktop or Start menu icon. It checks prices by itself at every PC start."
    }
    Release-Lock       # the launcher would otherwise see it held and say AirFare is being updated
    # Process.Start, not Start-Process: it takes the path literally even with [ ] in a folder name.
    $open = if (Test-Path -LiteralPath $launcher) { New-Object Diagnostics.ProcessStartInfo($launcher, "--settings") }
            else { New-Object Diagnostics.ProcessStartInfo((Join-Path $root ".venv\Scripts\pythonw.exe"), "-m airfare setup") }
    $open.WorkingDirectory = $root
    $open.UseShellExecute = $false
    [void][Diagnostics.Process]::Start($open)
    Done 0
} catch {
    if ($Upgrade) { Fail "The update stopped: $_`n$untouched" }
    Fail "Setup stopped: $_"
}
