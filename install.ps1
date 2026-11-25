# For Real J.A.R.V.I.S. - one-step installer for Windows 10/11.
# Run from the repo folder:  powershell -ExecutionPolicy Bypass -File install.ps1
# Safe to run again: it only adds what is missing and asks before touching your agent's config.
param(
    [switch]$Yes,                                  # answer "yes" to every question (for agents installing it for you)
    [ValidateSet("", "agent", "jarvis")][string]$Who = "",          # who lives in the orb: your agent (default) or a separate JARVIS
    [ValidateSet("", "openclaw", "hermes")][string]$Which = "",     # which one, if you have both
    [ValidateSet("", "openclaw", "claude")][string]$Brain = "",     # a separate JARVIS thinks with: a second OpenClaw agent, or Claude Code
    [ValidateSet("", "en", "es")][string]$Lang = "",
    [string]$Extras = "",                          # "parakeet,openmic"
    [switch]$NoAutostart,                          # don't start JARVIS with Windows
    [switch]$NoShortcuts                           # nothing on the desktop, doesn't start it
)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root
# a program that writes to stderr would stop the whole installer on Windows PowerShell 5.1: here only its exit code counts
function Quiet([scriptblock]$b) { $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"; try { & $b 2>$null } finally { $ErrorActionPreference = $old } }
function Say($t) { Write-Host "  $t" }
function Step($t) { Write-Host "`n== $t" -ForegroundColor Cyan }
function Ask($q) { if ($Yes) { return $true }; (Read-Host "  $q [Y/n]") -notmatch '^(n|no)$' }

Write-Host "`nFor Real J.A.R.V.I.S. installer" -ForegroundColor Cyan

# 1. Your agent -----------------------------------------------------------------------------------
Step "1/6  Looking for your agent"
$openclaw = Join-Path $HOME ".openclaw\openclaw.json"
# Hermes: HERMES_HOME, %LOCALAPPDATA%\hermes (native Windows) or ~\.hermes
$hermes = @($env:HERMES_HOME, (Join-Path $env:LOCALAPPDATA "hermes"), (Join-Path $HOME ".hermes")) | ? { $_ -and (Test-Path $_) } | select -First 1
$claude = Get-Command claude -ErrorAction SilentlyContinue
$found = @(); if (Test-Path $openclaw) { $found += "openclaw" }; if ($hermes) { $found += "hermes" }
$id = "main"; $agentName = "your agent"
if ($found -contains "openclaw") {  # its default agent may not be called "main"
    $cfg = Get-Content $openclaw -Raw -Encoding UTF8 | ConvertFrom-Json
    # agents.entries (an object) since OpenClaw 2026, agents.list (an array) before
    $list = if ($cfg.agents.entries) { @($cfg.agents.entries.PSObject.Properties | % { $_.Value | Add-Member id $_.Name -Force -PassThru }) }
            else { @($cfg.agents.list | ? { $_ -and $_.id }) }
    $me = $list | ? { $_.default } | select -First 1
    if (-not $me) { $me = $list | ? { $_.id -eq "main" } | select -First 1 }
    if (-not $me) { $me = $list | select -First 1 }
    if ($me) { $id = $me.id }
    if ($me.identity.name) { $agentName = $me.identity.name } elseif ($me.name) { $agentName = $me.name }
}
if (-not $found -and -not $claude) {
    Write-Host "  JARVIS is a body without a brain: it needs one of these first (any of them):" -ForegroundColor Yellow
    Say "  OpenClaw (recommended, full panel): https://github.com/openclaw/openclaw"
    Say "  Hermes Agent:                     https://github.com/NousResearch/hermes-agent"
    Say "  Claude Code (with a Claude plan):  https://claude.com/claude-code"
    Say "Install one, then run this installer again."
    exit 1
}
if ($found) { Say "Found $($found -join ' and ')." }
if ($claude) { Say "Found Claude Code." }

# The one question: who lives in the orb
if (-not $found) { $Who = "jarvis"; Say "No OpenClaw or Hermes: JARVIS will be his own agent, thinking with Claude Code." }
if (-not $Who) {
    $Who = "agent"
    if (-not $Yes -and ($found -contains "openclaw" -or $claude)) {
        Say ""
        Say "Who lives in the orb?"
        Say "  1) $agentName (recommended): it keeps its name, its memory and its model, and gets the orb, the voice and the panel"
        Say "  2) JARVIS, a separate agent: yours stays where it is and JARVIS starts from zero, with his own memory"
        if ((Read-Host "  1 or 2? [1]").Trim() -eq "2") { $Who = "jarvis" }
    }
}
if ($Who -eq "agent" -and -not $found) { Write-Host "  There's no OpenClaw or Hermes agent here to put in the orb." -ForegroundColor Red; exit 1 }
if ($Who -eq "agent") {
    if ($Which -and $found -notcontains $Which) { Write-Host "  $Which isn't installed here." -ForegroundColor Red; exit 1 }
    if (-not $Which) {
        $Which = $found[0]
        if (-not $Yes -and $found.Count -gt 1 -and (Read-Host "  Which one: 1) OpenClaw  2) Hermes? [1]").Trim() -eq "2") { $Which = "hermes" }
    }
    $kind = $Which
}
else {
    if (-not $Brain) {
        $Brain = if ($found -contains "openclaw") { "openclaw" } else { "claude" }
        if (-not $Yes -and $found -contains "openclaw" -and $claude) {
            Say "What does JARVIS think with?"
            Say "  1) a second agent in your OpenClaw: same model and keys as yours, full panel"
            Say "  2) Claude Code: your Claude plan; he asks your yes before anything that can't be undone, and keeps a daily memory"
            if ((Read-Host "  1 or 2? [1]").Trim() -eq "2") { $Brain = "claude" }
        }
    }
    if ($Brain -eq "openclaw" -and $found -notcontains "openclaw") { Write-Host "  OpenClaw isn't installed." -ForegroundColor Red; exit 1 }
    if ($Brain -eq "claude" -and -not $claude) { Write-Host "  Claude Code isn't installed: https://claude.com/claude-code" -ForegroundColor Red; exit 1 }
    $kind = $Brain
}

# 2. Python ---------------------------------------------------------------------------------------
Step "2/6  Python"
$venvPy = ".venv\Scripts\python.exe"
$haveVenv = $false
if (Test-Path $venvPy) { Quiet { & $venvPy -c "1" }; $haveVenv = $LASTEXITCODE -eq 0 }
if ($haveVenv) { Say "Using the existing .venv." }
else {
    $py = $null
    foreach ($cand in @(@("py", "-3.12"), @("python"))) {
        try {
            $rest = @($cand | select -Skip 1)
            $ver = Quiet { & $cand[0] $rest -c "import sys; print('%d.%d' % sys.version_info[:2])" }
            if ($LASTEXITCODE -eq 0 -and $ver -eq "3.12") { $py = $cand; break }
        } catch { }
    }
    if (-not $py) {
        Write-Host "  Python 3.12 is needed (exactly: the speech libraries need it and 3.13+ is too new for them)." -ForegroundColor Yellow
        # never automatic, not even with -Yes: installing software on the PC is the user's call
        if (-not $Yes -and (Read-Host "  Install Python 3.12 with winget now? [y/N]") -match '^(y|yes)$') {
            winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
            $py = @("py", "-3.12")
        } else { Say "Install Python 3.12 from https://www.python.org/downloads/ and run this again."; exit 1 }
    }
    Say "Using $($py -join ' ')"
    $rest = @($py | select -Skip 1)
    & $py[0] $rest -m venv .venv
}

# 3. Libraries ------------------------------------------------------------------------------------
Step "3/6  Libraries (the first time it downloads ~2 GB: speech recognition models)"
Quiet { & $venvPy -c "import RealtimeSTT, kokoro_onnx, sounddevice, pyaudio, httpx, websockets, psutil, PIL" }
if ($LASTEXITCODE -eq 0) { Say "Already installed." }
else {
    Quiet { & $venvPy -m ensurepip --upgrade } | Out-Null
    $ErrorActionPreference = "Continue"  # pip warns on stderr
    & $venvPy -m pip install --upgrade pip --quiet
    & $venvPy -m pip install -r requirements.txt
    $ErrorActionPreference = "Stop"
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
    $port = if ($cfg.gateway.port) { $cfg.gateway.port } else { 18789 }
    $workspace = if ($me.workspace) { $me.workspace } elseif ($cfg.agents.defaults.workspace) { $cfg.agents.defaults.workspace } else { Join-Path $HOME ".openclaw\workspace" }
    $enabled = $cfg.gateway.http.endpoints.chatCompletions.enabled
    if (-not $enabled) {
        Say "JARVIS talks to OpenClaw through its local chat API (gateway.http.endpoints.chatCompletions), which is off."
        if (Ask "Turn it on? (local only, protected by your gateway token)") {
            $ErrorActionPreference = "Continue"
            openclaw config set gateway.http.endpoints.chatCompletions.enabled true
            $set = $LASTEXITCODE; $ErrorActionPreference = "Stop"
            if ($set -ne 0) { Write-Host "  OpenClaw didn't accept it: see above, fix it and run this again." -ForegroundColor Red; exit 1 }
            Say "On. (If JARVIS can't reach it below, restart your OpenClaw gateway.)"
        } else { Say "Skipped: JARVIS won't be able to talk to OpenClaw until you turn it on." }
    }
    if ($Who -eq "jarvis") {
        if ($old = $list | ? { $_.id -eq "jarvis" } | select -First 1) { Say "Using the 'jarvis' agent your OpenClaw already has."; if ($old.workspace) { $workspace = $old.workspace } }
        else {
            $workspace = Join-Path $HOME ".openclaw\workspace-jarvis"
            if (-not (Ask "Add a second agent called 'jarvis' to your OpenClaw ($workspace)? Yours isn't touched.")) { Say "Nothing done."; exit 1 }
            New-Item -ItemType Directory -Force $workspace | Out-Null
            foreach ($f in "SOUL.md", "USER.md") { if (-not (Test-Path "$workspace\$f")) { Copy-Item "agent-template\$f" $workspace } }
            $ErrorActionPreference = "Continue"
            openclaw agents add jarvis --workspace $workspace --non-interactive
            $added = $LASTEXITCODE; $ErrorActionPreference = "Stop"
            if ($added -ne 0) { Write-Host "  OpenClaw couldn't add it: see above." -ForegroundColor Red; exit 1 }
            Say "Added. (If he doesn't answer below, restart your OpenClaw gateway.)"
        }
        $id = "jarvis"
    }
    $agent = @{ kind = "openclaw"; url = "http://127.0.0.1:$port"; model = "openclaw/$id"; session = "agent:${id}:main" }
    $skillsDir = Join-Path $workspace "skills"
} elseif ($kind -eq "claude") {
    $workspace = Join-Path $HOME "jarvis-agent"
    New-Item -ItemType Directory -Force $workspace, "$workspace\memory" | Out-Null
    foreach ($f in Get-ChildItem "agent-template" -File) {
        if (-not (Test-Path "$workspace\$($f.Name)")) { (Get-Content $f.FullName -Raw -Encoding UTF8).Replace("{{JARVIS_HOME}}", $Root) | Set-Content "$workspace\$($f.Name)" -Encoding UTF8 }
    }
    Say "JARVIS's own folder: $workspace (his personality, his notes, his memory)."
    $agent = @{ kind = "claude-cli"; model = "claude-haiku-5-5"; model_hard = "claude-sonnet-5-5"; workspace = $workspace }
    $skillsDir = Join-Path $workspace "skills"
} else {
    $envFile = Join-Path $hermes ".env"
    $envText = if (Test-Path $envFile) { Get-Content $envFile -Raw } else { "" }
    $key = if ($envText -match 'API_SERVER_KEY\s*=\s*(\S+)') { $Matches[1] } else { "" }
    if ($envText -notmatch 'API_SERVER_ENABLED\s*=\s*true' -or -not $key) {
        Say "JARVIS talks to Hermes through its API server (API_SERVER_* in $envFile), which isn't fully on."
        if (Ask "Turn it on (127.0.0.1:8642, local only, with a random key)?") {
            $add = ""
            if ($envText -notmatch 'API_SERVER_ENABLED\s*=\s*true') { $add += "`nAPI_SERVER_ENABLED=true" }
            if (-not $key) {  # Hermes requires a key even on localhost
                $key = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
                $add += "`nAPI_SERVER_KEY=$key"
            }
            Add-Content $envFile $add
            Say "On. Restart 'hermes gateway' so it takes effect."
        }
    }
    $agent = @{ kind = "hermes"; url = "http://127.0.0.1:8642"; model = "hermes-agent"; token = $key; session = "for-real-jarvis" }
    $skillsDir = Join-Path $hermes "skills\jarvis"   # Hermes: ~/.hermes/skills/<category>/<skill>/SKILL.md
}
if (-not (Test-Path "data\settings.json")) {
    $lang = if ($Lang) { $Lang } elseif ($Yes) { "en" } else { (Read-Host "  Language you'll speak to JARVIS: en (English) or es (Spanish)? [en]").Trim().ToLower() }
    if ($lang -ne "es") { $lang = "en" }
    $conf = @{ agent = $agent; language = $lang }
    $want = { param($name, $q) ($Extras -split "[, ]+") -contains $name -or (-not $Yes -and (Read-Host "  $q [y/N]") -match '^(y|yes|s|si)$') }
    if (& $want "parakeet" "Extra: faster ears (Parakeet, ~10x faster, +670 MB download)?") {
        $ErrorActionPreference = "Continue"
        & $venvPy -m pip install --quiet "onnx-asr[cpu,hub]"
        if ($LASTEXITCODE -eq 0) { $conf.stt = "parakeet" } else { Say "Couldn't install it; staying with Whisper." }
        $ErrorActionPreference = "Stop"
    }
    if (& $want "openmic" "Extra: open mic? He also answers orders without 'Jarvis'; what you say near the PC that may be for him goes to your model") { $conf.open_mic = $true }
    $conf | ConvertTo-Json | Set-Content "data\settings.json" -Encoding UTF8
    if ($Who -eq "jarvis") { '{"name": "J.A.R.V.I.S.", "letter": "J"}' | Set-Content "data\identity.json" -Encoding ASCII }
} else { Say "data\settings.json already exists: it stays as it is (delete it and run this again to choose again)." }
# Skills: copied into your agent, pointing at this folder. Your agent's personality and memory are not touched.
foreach ($s in Get-ChildItem "skills" -Directory) {
    $dest = Join-Path $skillsDir $s.Name
    New-Item -ItemType Directory -Force $dest | Out-Null
    (Get-Content "$($s.FullName)\SKILL.md" -Raw -Encoding UTF8).Replace("{{JARVIS_HOME}}", $Root) | Set-Content "$dest\SKILL.md" -Encoding UTF8
}
Say "Skills installed in $skillsDir (jarvis-pc, jarvis-modes, jarvis-personalize, jarvis-reminders)."
if ($Who -eq "agent") { Say "Your agent keeps its personality, memory and notes: nothing of that was changed." }
Say "Asking it for one word, to see that it answers..."
$ErrorActionPreference = "Continue"
& $venvPy -m jarvis --check-agent
$answers = $LASTEXITCODE -eq 0
$ErrorActionPreference = "Stop"

if ($NoShortcuts) { exit $(if ($answers) { 0 } else { 2 }) }

# 6. Shortcuts --------------------------------------------------------------------------------------
Step "6/6  Shortcuts"
$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "JARVIS.lnk"))
$lnk.TargetPath = "$Root\Restart JARVIS.cmd"; $lnk.WorkingDirectory = $Root; $lnk.WindowStyle = 7
$lnk.IconLocation = "$Root\jarvis\static\orb.ico,0"; $lnk.Description = "Start (or restart) JARVIS"; $lnk.Save()
Say "Desktop shortcut 'JARVIS' created (starts it, or restarts it if the orb ever freezes)."
if (-not $NoAutostart -and (Ask "Start JARVIS automatically when you log in to Windows?")) {
    $auto = $sh.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Startup")) "JARVIS.lnk"))
    $auto.TargetPath = "$Root\Start JARVIS.cmd"; $auto.WorkingDirectory = $Root; $auto.WindowStyle = 7
    $auto.IconLocation = "$Root\jarvis\static\orb.ico,0"; $auto.Save()
    Say "Done."
}

if ($answers) { Write-Host "`nAll set." -ForegroundColor Green }
else { Write-Host "`nInstalled, but your agent doesn't answer yet: restart its gateway, then run  .venv\Scripts\python.exe -m jarvis --check-agent" -ForegroundColor Yellow }
Say "1. Double-click JARVIS on your desktop (the orb appears top right; the first start takes ~20 s)."
Say "2. Say 'Hey Jarvis' (or press Ctrl+Shift+J) and talk."
Say "3. Right-click the orb > Open panel > 'Personalize JARVIS' so he gets to know you,"
Say "   and 'Create a mode' to build your first mode with him."
if (Ask "Start JARVIS now?") { explorer.exe "$Root\Start JARVIS.cmd" }  # through Explorer: it outlives whoever ran this installer
