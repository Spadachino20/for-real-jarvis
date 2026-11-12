# For Real J.A.R.V.I.S. - one-step installer for Windows 10/11.
# Run from the repo folder:  powershell -ExecutionPolicy Bypass -File install.ps1
# Safe to run again: it only adds what is missing and asks before touching your agent's config.
param([switch]$Yes)  # -Yes: answer "yes" to every question (for agents installing it for you)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root
function Say($t) { Write-Host "  $t" }
function Step($t) { Write-Host "`n== $t" -ForegroundColor Cyan }
function Ask($q) { if ($Yes) { return $true }; (Read-Host "  $q [Y/n]") -notmatch '^(n|no)$' }

Write-Host "`nFor Real J.A.R.V.I.S. installer" -ForegroundColor Cyan

# 1. Your agent -----------------------------------------------------------------------------------
Step "1/6  Looking for your agent"
$openclaw = Join-Path $HOME ".openclaw\openclaw.json"
$hermes = Join-Path $HOME ".hermes"
if (Test-Path $openclaw) { $kind = "openclaw"; Say "Found OpenClaw." }
elseif (Test-Path $hermes) { $kind = "hermes"; Say "Found Hermes." }
else {
    Write-Host "  No agent found. JARVIS is a door to YOUR agent, so you need one first:" -ForegroundColor Yellow
    Say "  OpenClaw (recommended, full panel): https://github.com/openclaw/openclaw"
    Say "  Hermes Agent:                     https://github.com/NousResearch/hermes-agent"
    Say "Install one, then run this installer again."
    exit 1
}

# 2. Python ---------------------------------------------------------------------------------------
Step "2/6  Python"
$venvPy = ".venv\Scripts\python.exe"
$haveVenv = $false
if (Test-Path $venvPy) { & $venvPy -c "1" 2>$null; $haveVenv = $LASTEXITCODE -eq 0 }
if ($haveVenv) { Say "Using the existing .venv." }
else {
    $py = $null
    foreach ($cand in @(@("py", "-3.12"), @("py", "-3.11"), @("py", "-3.10"), @("python"))) {
        try {
            $ver = & $cand[0] $cand[1..9] -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ver -in "3.10", "3.11", "3.12") { $py = $cand; break }
        } catch { }
    }
    if (-not $py) {
        Write-Host "  Python 3.10-3.12 is needed (3.13+ is too new for the speech libraries)." -ForegroundColor Yellow
        # never automatic, not even with -Yes: installing software on the PC is the user's call
        if (-not $Yes -and (Read-Host "  Install Python 3.12 with winget now? [y/N]") -match '^(y|yes)$') {
            winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
            $py = @("py", "-3.12")
        } else { Say "Install Python 3.12 from https://www.python.org/downloads/ and run this again."; exit 1 }
    }
    Say "Using $($py -join ' ')"
    & $py[0] $py[1..9] -m venv .venv
}

# 3. Libraries ------------------------------------------------------------------------------------
Step "3/6  Libraries (the first time it downloads ~2 GB: speech recognition models)"
& $venvPy -c "import RealtimeSTT, kokoro_onnx, sounddevice, pyaudio, httpx, websockets, psutil, PIL" 2>$null
if ($LASTEXITCODE -eq 0) { Say "Already installed." }
else {
    & $venvPy -m ensurepip --upgrade 2>$null | Out-Null
    & $venvPy -m pip install --upgrade pip --quiet
    & $venvPy -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Write-Host "  pip failed: see the error above." -ForegroundColor Red; exit 1 }
}

# 4. Local voice (Kokoro) -------------------------------------------------------------------------
Step "4/6  Local voice"
New-Item -ItemType Directory -Force models, data | Out-Null
$base = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
foreach ($f in "kokoro-v1.0.int8.onnx", "voices-v1.0.bin") {
    if (-not (Test-Path "models\$f")) { Say "Downloading $f..."; Invoke-WebRequest "$base/$f" -OutFile "models\$f" -UseBasicParsing }
}
Say "Voice ready."

# 5. Connect to your agent ------------------------------------------------------------------------
Step "5/6  Connecting to your agent"
if ($kind -eq "openclaw") {
    $cfg = Get-Content $openclaw -Raw | ConvertFrom-Json
    $port = if ($cfg.gateway.port) { $cfg.gateway.port } else { 18789 }
    $workspace = if ($cfg.agents.defaults.workspace) { $cfg.agents.defaults.workspace } else { Join-Path $HOME ".openclaw\workspace" }
    $enabled = $cfg.gateway.http.endpoints.chatCompletions.enabled
    if (-not $enabled) {
        Say "JARVIS talks to OpenClaw through its local chat API (gateway.http.endpoints.chatCompletions), which is off."
        if (Ask "Turn it on? (local only, protected by your gateway token)") {
            openclaw config set gateway.http.endpoints.chatCompletions.enabled true
            Say "On. Restart your OpenClaw gateway so it takes effect."
        } else { Say "Skipped: JARVIS won't be able to talk to OpenClaw until you turn it on." }
    }
    $agent = @{ kind = "openclaw"; url = "http://127.0.0.1:$port"; model = "openclaw/main" }
    $skillsDir = Join-Path $workspace "skills"
} else {
    $envFile = Join-Path $hermes ".env"
    $envText = if (Test-Path $envFile) { Get-Content $envFile -Raw } else { "" }
    if ($envText -notmatch 'API_SERVER_ENABLED\s*=\s*true') {
        Say "JARVIS talks to Hermes through its API server, which is off (API_SERVER_ENABLED in $envFile)."
        if (Ask "Turn it on (127.0.0.1:8642, local only)?") {
            Add-Content $envFile "`nAPI_SERVER_ENABLED=true`nAPI_SERVER_HOST=127.0.0.1`nAPI_SERVER_PORT=8642"
            Say "On. Restart 'hermes gateway' so it takes effect."
        }
    }
    $key = if ($envText -match 'API_SERVER_KEY\s*=\s*(\S+)') { $Matches[1] } else { "" }
    $agent = @{ kind = "hermes"; url = "http://127.0.0.1:8642"; model = "hermes-agent"; token = $key }
    $skillsDir = Join-Path $hermes "skills"
}
if (-not (Test-Path "data\settings.json")) {
    $lang = if ($Yes) { "en" } else { (Read-Host "  Language you'll speak to JARVIS: en (English) or es (Spanish)? [en]").Trim().ToLower() }
    if ($lang -ne "es") { $lang = "en" }
    @{ agent = $agent; language = $lang } | ConvertTo-Json | Set-Content "data\settings.json" -Encoding UTF8
}
# Skills: copied into your agent, pointing at this folder. Your agent's personality and memory are not touched.
foreach ($s in Get-ChildItem "skills" -Directory) {
    $dest = Join-Path $skillsDir $s.Name
    New-Item -ItemType Directory -Force $dest | Out-Null
    (Get-Content "$($s.FullName)\SKILL.md" -Raw -Encoding UTF8).Replace("{{JARVIS_HOME}}", $Root) | Set-Content "$dest\SKILL.md" -Encoding UTF8
}
Say "Skills installed in $skillsDir (jarvis-pc, jarvis-modes, jarvis-personalize, jarvis-reminders)."
Say "Your agent keeps its personality, memory and notes: nothing of that was changed."

# 6. Shortcuts --------------------------------------------------------------------------------------
Step "6/6  Shortcuts"
$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "JARVIS.lnk"))
$lnk.TargetPath = "$Root\Restart JARVIS.cmd"; $lnk.WorkingDirectory = $Root; $lnk.WindowStyle = 7
$lnk.IconLocation = "$Root\jarvis\static\orb.ico,0"; $lnk.Description = "Start (or restart) JARVIS"; $lnk.Save()
Say "Desktop shortcut 'JARVIS' created (starts it, or restarts it if the orb ever freezes)."
if (Ask "Start JARVIS automatically when you log in to Windows?") {
    $auto = $sh.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Startup")) "JARVIS.lnk"))
    $auto.TargetPath = "$Root\Start JARVIS.cmd"; $auto.WorkingDirectory = $Root; $auto.WindowStyle = 7
    $auto.IconLocation = "$Root\jarvis\static\orb.ico,0"; $auto.Save()
    Say "Done."
}

Write-Host "`nAll set." -ForegroundColor Green
Say "1. Double-click JARVIS on your desktop (the orb appears top right; the first start takes ~20 s)."
Say "2. Say 'Hey Jarvis' (or press Ctrl+Shift+J) and talk."
Say "3. Right-click the orb > Open panel > 'Personalize JARVIS' so he gets to know you,"
Say "   and 'Create a mode' to build your first mode with him."
if (Ask "Start JARVIS now?") { & "$Root\Start JARVIS.cmd" }
