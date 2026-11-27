# For Real J.A.R.V.I.S. - PC shortcuts for your agent. Every action answers in one line with what it CHECKED got done.
# Usage: pc.ps1 <action> [argument]
#   music status|play|pause|next|previous      (real state from Windows, no guessing)
#   volume up|down|mute [steps]                 (each step = 2 %)
#   open <app|folder|file|url>                  (Microsoft Store apps too, e.g. Spotify)
#   close <app>
#   youtube <search> / youtube-link <search>    (open the first video / only give the link)
#   apps <word>                                 (every app and shortcut whose name has it: what you can open)
#   click <text> [window]                       (presses a button/link/tab by its visible text, in any app)
#   keys <SendKeys>                             (keys to the window in front: ^l, {ENTER}, %{F4}...)
#   whatsapp-me <text>                          (to your own WhatsApp chat, through OpenClaw; "\n" = new line)
#   ytmusic <search or link>                    (a playlist, in your YouTube Music app if it's installed)
#   find <part of a file name>                  (Windows search index: ~1 s)
#   screenshot                                  (saves data\screen.jpg for your image tool)
#   pc-status / clipboard / copy <text> / type <text>
#   modes / mode <id>                           (your modes, from data\modes.json)
param([Parameter(Mandatory = $true)][string]$Action, [string]$Arg = "", [string]$Steps = "")
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8   # song titles and file names with accents arrive intact
$Root = (Resolve-Path "$PSScriptRoot\..\..").Path   # the For Real J.A.R.V.I.S. folder
$ModesFile = Join-Path $Root "data\modes.json"

Add-Type -MemberDefinition '[DllImport("user32.dll")] public static extern void keybd_event(byte b, byte s, uint f, UIntPtr e);' -Name K -Namespace FrjPc
function Key([byte]$vk, [int]$times = 1) { 1..$times | % { [FrjPc.K]::keybd_event($vk, 0, 0, [UIntPtr]::Zero); [FrjPc.K]::keybd_event($vk, 0, 2, [UIntPtr]::Zero) } }

function MediaSession {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $script:asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | select -First 1
    $null = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime]
    $m = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
    $m.GetCurrentSession()
}
function Await($op, $type) { $t = $script:asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
function MediaState($s) {
    $p = Await ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
    $st = @{ Playing = "playing"; Paused = "paused"; Stopped = "stopped" }[[string]$s.GetPlaybackInfo().PlaybackStatus]
    $app = ($s.SourceAppUserModelId -split '[_!.]')[0] -replace 'AB$', ''
    "$app ${st}: $($p.Artist) - $($p.Title)"
}

function Ours {
    # process ids never to close: our own parents (the agent may be a CLI named like the app, e.g. claude) and
    # what the orb's python started (JARVIS's light-house `claude`)
    $parent = @{}; $py = @()
    Get-CimInstance Win32_Process | % { $parent[[int]$_.ProcessId] = [int]$_.ParentProcessId; if ($_.Name -like 'python*') { $py += [int]$_.ProcessId } }
    $mine = @(); $id = $PID
    while ($id -and $mine -notcontains $id) { $mine += $id; $id = $parent[$id] }
    $mine + @($parent.Keys | ? { $py -contains $parent[$_] })
}

function CloseThese([string[]]$names, [datetime]$since = [datetime]::MinValue) {
    # closes the processes a mode lists. Steam exits cleanly through its URL: killing it makes it relaunch.
    $ours = Ours
    $p = @(Get-Process $names -ErrorAction SilentlyContinue | ? { $_.StartTime -gt $since -and $ours -notcontains $_.Id })
    if (-not $p) { return }
    if ($p | ? ProcessName -eq steam) { Start-Process "steam://exit" }
    $p | ? ProcessName -notmatch '^steam' | Stop-Process -Force -ErrorAction SilentlyContinue
    $p.ProcessName | select -Unique
}

function Launch([string]$target) {
    # explorer starts it, not us: agents (OpenClaw) run commands inside a Windows job that kills
    # whatever the command opened as soon as it ends. Started by explorer, the app outlives the command.
    Start-Process explorer.exe -ArgumentList "`"$target`""
}

function Settled([string]$name, [datetime]$t0, [string]$title = "") {
    # the honest answer: waits up to 8 s for the program to be running (and still running a second later)
    $skip = '^(explorer|conhost|powershell|pwsh|cmd|RuntimeBroker|backgroundTaskHost|dllhost|svchost|SearchHost|ApplicationFrameHost|WerFault|Update)$'
    $seen = $null
    for ($i = 0; $i -lt 16; $i++) {
        Start-Sleep -Milliseconds 500
        $new = @(Get-Process | ? { try { $_.StartTime -gt $t0 } catch { $false } } | ? ProcessName -notmatch $skip)
        $hit = @($new | ? ProcessName -like "*$name*")
        if (-not $hit) { $hit = @($new | ? MainWindowHandle -ne 0) }
        if (-not $hit -and $title) { $hit = @(Get-Process | ? MainWindowTitle -like "*$title*") }  # a web app: its window, inside chrome/msedge
        if ($hit -and $seen) { return ($hit.ProcessName | select -Unique) -join ', ' }
        $seen = [bool]$hit
    }
}

function OpenThing([string]$target) {
    # a path (.exe, .lnk, folder), a URL/URI, or the name of an app in the Start menu.
    # Apps answer "opened" only once they're really running; otherwise they say so.
    $name, $what = $null, $target
    if ($target -match '\.(exe|lnk)$' -and (Test-Path $target)) {
        $name = [IO.Path]::GetFileNameWithoutExtension($target)
    } elseif ((Test-Path $target) -or $target -match '^[a-z][a-z0-9+.-]*:') {
        Launch $target; return "$([IO.Path]::GetFileNameWithoutExtension($target)) sent to Windows to open"  # folder / URL: nothing to check
    } else {
        $app = Get-StartApps | ? Name -like "*$target*" | sort { $_.Name.Length } | select -First 1
        if (-not $app) { return "no app called '$target' in the Start menu" }
        $name, $what = $app.Name, "shell:AppsFolder\$($app.AppID)"
    }
    $short = ($name -split '\s')[0]
    if ((Get-Process "*$short*" -ErrorAction SilentlyContinue | ? MainWindowHandle -ne 0) -or (Get-Process | ? MainWindowTitle -like "*$name*")) {
        if ($what -like "shell:*") { Launch $what }   # brings it to the front (a Start menu app)
        return "$name was already open"
    }
    $t0 = (Get-Date).AddSeconds(-1)
    Launch $what
    if ($running = Settled $short $t0 $name) { return "$name opened (running: $running)" }
    "$name did NOT open: Windows got the order but no program stayed running. Don't tell him it's open."
}

function PlayPlaylist([string]$uri, [string]$name) {
    # Opening a playlist link only SHOWS it in Spotify: press its green play button through UI Automation.
    Start-Process $uri
    if (-not $name -and $uri -match 'playlist[:/]([A-Za-z0-9]{22})') {  # public playlist: its title is on its web page
        try { $name = [regex]::Match((Invoke-WebRequest "https://open.spotify.com/playlist/$($Matches[1])" -UseBasicParsing).Content, '<title>(.*?) - playlist').Groups[1].Value } catch { }
    }
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
    # Spotify (Chromium) hides its buttons from Windows until someone asks its inner window for accessibility
    Add-Type @'
using System; using System.Runtime.InteropServices; using System.Text;
public class FrjAcc {
  [DllImport("oleacc.dll")] static extern int AccessibleObjectFromWindow(IntPtr h, uint id, ref Guid g, [MarshalAs(UnmanagedType.IUnknown)] out object o);
  delegate bool CB(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr p, CB cb, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  public static void Wake(IntPtr top) { EnumChildWindows(top, (h,l) => { var s = new StringBuilder(256); GetClassName(h, s, 256);
    if (s.ToString().StartsWith("Chrome_RenderWidgetHostHWND")) { Guid g = new Guid("618736E0-3C3D-11CF-810C-00AA00389B71"); object o; AccessibleObjectFromWindow(h, 0xFFFFFFFC, ref g, out o); }
    return true; }, IntPtr.Zero); }
}
'@
    $pressed = $false
    if ($name) {
        foreach ($i in 1..16) {
            Start-Sleep -Milliseconds 500
            $w = Get-Process Spotify -ErrorAction SilentlyContinue | ? MainWindowHandle -ne 0 | select -First 1
            if (-not $w) { continue }
            try {
                [FrjAcc]::Wake($w.MainWindowHandle)
                $top = [Windows.Automation.AutomationElement]::FromHandle($w.MainWindowHandle)
                foreach ($label in "Play $name", "Reproducir $name") {  # Spotify in English or Spanish
                    $b = $top.FindFirst([Windows.Automation.TreeScope]::Descendants, (New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::NameProperty, $label)))
                    if ($b) { $b.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke(); $pressed = $true; break }
                }
            } catch { }  # Spotify still loading: retry
            if ($pressed) { break }
        }
    }
    if (-not $pressed) { $s = MediaSession; if ($s) { $null = Await ($s.TryPlayAsync()) ([bool]) } }
    Start-Sleep -Milliseconds 1200
    $s = MediaSession
    if ($s) { "music: $(MediaState $s)" + $(if (-not $pressed) { " (couldn't find the playlist's play button: resumed the last thing)" }) } else { "Spotify didn't start the music" }
}

function Modes { if (Test-Path $ModesFile) { @((Get-Content $ModesFile -Raw -Encoding UTF8 | ConvertFrom-Json).modes) } else { @() } }

switch ($Action.ToLower()) {
    "music" {
        $s = MediaSession
        if (-not $s) { "Nothing is playing music. Open Spotify first (pc.ps1 open spotify)."; break }
        $op = @{ play = "TryPlayAsync"; pause = "TryPauseAsync"; next = "TrySkipNextAsync"; previous = "TrySkipPreviousAsync" }[$Arg.ToLower()]
        if ($op) { $null = Await ($s.$op()) ([bool]); Start-Sleep -Milliseconds 1200 }
        MediaState $s
    }
    "volume" {
        $n = if ($Steps) { [int]$Steps } else { 5 }
        switch ($Arg.ToLower()) { "up" { Key 0xAF $n } "down" { Key 0xAE $n } "mute" { Key 0xAD } default { throw "volume up|down|mute" } }
        "Volume: $Arg" + $(if ($Arg -ne "mute") { " $($n * 2) %" })
    }
    "modes" {
        $m = Modes
        if (-not $m) { "No modes yet. Create one with the jarvis-modes skill (file: $ModesFile)."; break }
        $m | % { "$($_.id): $($_.title) - $($_.description)" + $(if ($_.tell_agent) { " [has instructions for you]" }) }
    }
    "mode" {
        $mode = Modes | ? id -eq $Arg | select -First 1
        if (-not $mode) { "Unknown mode '$Arg'. Modes: $((Modes | % id) -join ', '). Create new ones with the jarvis-modes skill."; break }
        $done = @(); $start = Get-Date
        if ($mode.close) { $c = CloseThese $mode.close; $done += $(if ($c) { "closed: $($c -join ', ')" } else { "nothing to close" }) }
        foreach ($o in @($mode.open)) { if ($o) { $done += OpenThing $o } }
        if ($mode.playlist) { $done += PlayPlaylist $mode.playlist $mode.playlist_name }
        if ($mode.close) {
            $back = CloseThese $mode.close $start  # some apps (Steam, Xbox) relaunch themselves: second pass
            if ($back) { $done += "they reopened and I closed them again: $($back -join ', ')" }
        }
        if ($mode.tell_agent) { $done += "INSTRUCTION FOR THE AGENT: $($mode.tell_agent)" }
        $done -join " | "
    }
    "pc-status" {
        # no admin needed: CPU, RAM, disks, what eats memory, and crashes / blue screens
        $os = Get-CimInstance Win32_OperatingSystem
        $cpu = [math]::Round((Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average)
        $total = $os.TotalVisibleMemorySize / 1MB; $used = $total - $os.FreePhysicalMemory / 1MB
        "CPU $cpu % | RAM $([math]::Round($used, 1)) of $([math]::Round($total, 1)) GB ($([math]::Round(100 * $used / $total)) %) | on since $($os.LastBootUpTime.ToString('dd/MM HH:mm'))"
        "Disks: " + ((Get-PSDrive -PSProvider FileSystem | ? Used | % { "$($_.Name): $([math]::Round($_.Free / 1GB)) GB free" }) -join ", ")
        "Most memory: " + ((Get-Process | sort WorkingSet64 -Descending | select -First 3 | % { "$($_.ProcessName) $([math]::Round($_.WorkingSet64 / 1MB)) MB" }) -join ", ")
        # 1001 = blue screen (with its code), 41 = shut down without closing properly, 19 WHEA = corrected hardware error
        $bad = Get-WinEvent -FilterHashtable @{ LogName = 'System'; Id = 41, 1001, 19; StartTime = (Get-Date).AddDays(-30) } -ErrorAction SilentlyContinue |
            ? { $_.Id -ne 1001 -or $_.ProviderName -match 'WER' } | ? { $_.Id -ne 19 -or $_.ProviderName -match 'WHEA' }
        if (-not $bad) { "Last 30 days: no blue screens or hard shutdowns." }
        else {
            "Last 30 days: $(@($bad | ? Id -eq 1001).Count) blue screens, $(@($bad | ? Id -eq 41).Count) hard shutdowns, $(@($bad | ? Id -eq 19).Count) corrected hardware errors."
            $bad | ? Id -eq 1001 | select -First 3 | % { "  blue screen $($_.TimeCreated.ToString('dd/MM HH:mm')): " + ([regex]::Match($_.Message, '0x[0-9a-fA-F]{8,}').Value) }
        }
    }
    "clipboard" { $t = Get-Clipboard -Raw; if ($t) { $t } else { "The clipboard has no text." } }
    "copy" { Set-Clipboard -Value $Arg; "Copied to the clipboard ($($Arg.Length) characters)." }
    "type" {
        # types where the cursor is: pastes through the clipboard (keeps accents and line breaks) and restores it
        $before = Get-Clipboard -Raw
        Set-Clipboard -Value $Arg
        [FrjPc.K]::keybd_event(0x11, 0, 0, [UIntPtr]::Zero); Key 0x56; [FrjPc.K]::keybd_event(0x11, 0, 2, [UIntPtr]::Zero)  # Ctrl+V
        Start-Sleep -Milliseconds 400
        if ($before) { Set-Clipboard -Value $before }
        $v = Add-Type -MemberDefinition '[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);' -Name V -Namespace FrjPc -PassThru
        $s = New-Object Text.StringBuilder 200; $null = $v::GetWindowText($v::GetForegroundWindow(), $s, 200)
        "Typed into: $s"
    }
    { $_ -in "youtube", "youtube-link" } {
        $html = (Invoke-WebRequest "https://www.youtube.com/results?search_query=$([uri]::EscapeDataString($Arg))" -UseBasicParsing).Content
        $m = [regex]::Match($html, '"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"\}')
        if (-not $m.Success) { "No YouTube videos for '$Arg'."; break }
        $url = "https://www.youtube.com/watch?v=$($m.Groups[1].Value)"
        $title = [regex]::Unescape($m.Groups[2].Value)
        if ($Action -eq "youtube") { Start-Process $url; "Opened on YouTube: $title ($url)" } else { "$title | $url" }
    }
    "apps" {
        $w = "*$Arg*"
        $start = @(Get-StartApps | ? Name -like $w | % { "app: $($_.Name)" })
        $links = @(Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu\Programs", "$env:ProgramData\Microsoft\Windows\Start Menu\Programs",
                   "$HOME\Desktop", "$env:PUBLIC\Desktop" -Recurse -Include *.lnk, *.url -EA 0 | ? BaseName -like $w | % { "shortcut: $($_.FullName)" })
        $all = $start + $links | Select-Object -Unique -First 25
        if ($all) { $all -join "`n" } else { "Nothing called '$Arg' in the Start menu or on the desktop. Try another word, or find '$Arg'." }
    }
    "click" {
        Add-Type -AssemblyName UIAutomationClient
        $A = [Windows.Automation.AutomationElement]
        $wins = $A::RootElement.FindAll("Children", [Windows.Automation.Condition]::TrueCondition) | ? { $_.Current.Name -and (-not $Steps -or $_.Current.Name -like "*$Steps*") }
        $hit = $null
        foreach ($w in $wins) {
            $hit = $w.FindAll("Descendants", [Windows.Automation.Condition]::TrueCondition) | ? { $_.Current.Name -like "*$Arg*" -and -not $_.Current.IsOffscreen } |
                   Sort-Object { if ($_.Current.Name -eq $Arg) { 0 } elseif ($_.Current.Name -like "$Arg*") { 1 } else { 2 } }, { $_.Current.ControlType.ProgrammaticName -notmatch 'Button|Hyperlink|TabItem|MenuItem' }, { $_.Current.Name.Length } |
                   Select-Object -First 1  # the exact text first: "Play" must not hit "Play my playlist"
            if ($hit) { break }
        }
        if (-not $hit) { "Nothing that says '$Arg' on screen$(if ($Steps) { " in '$Steps'" }). Take a screenshot and look."; break }
        $p = $null
        if ($hit.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern, [ref]$p)) { $p.Invoke() }
        else {  # no button pattern (a web element): a real click in its middle
            $r = $hit.Current.BoundingRectangle
            Add-Type -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y); [DllImport("user32.dll")] public static extern void mouse_event(uint f, int x, int y, uint d, UIntPtr e);' -Name M -Namespace FrjPc
            [FrjPc.M]::SetCursorPos([int]($r.X + $r.Width / 2), [int]($r.Y + $r.Height / 2)); [FrjPc.M]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero); [FrjPc.M]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero)
        }
        "Clicked '$($hit.Current.Name)' ($($hit.Current.ControlType.ProgrammaticName -replace 'ControlType\.')) in '$($w.Current.Name)'."
    }
    "keys" { (New-Object -ComObject WScript.Shell).SendKeys($Arg); "Sent keys: $Arg" }
    "whatsapp-me" {
        # node straight away: openclaw.cmd (a batch file) drops everything after the first line break
        $me = (Get-Content (Join-Path $Root "data\settings.json") -Raw -Encoding UTF8 | ConvertFrom-Json).whatsapp_me
        if (-not $me) { 'Set your number first: "whatsapp_me": "+591..." in data\settings.json.'; break }
        $js = Join-Path $env:APPDATA "npm\node_modules\openclaw\dist\index.js"
        if (-not (Test-Path $js)) { "OpenClaw isn't installed here: no WhatsApp."; break }
        $text = $Arg -replace '\\n', "`n"
        $ErrorActionPreference = "Continue"  # node's deprecation warnings on stderr aren't failures
        $out = & node $js message send --channel whatsapp --target $me -m $text 2>&1 | Out-String
        if ($out -match 'Sent') { "Sent to your WhatsApp ($($text.Split("`n").Count) lines)." } else { "NOT sent: " + ($out.Trim() -split "`n" | Select-Object -Last 2) -join " " }
    }
    "ytmusic" {
        $url = if ($Arg -match '^https?://') { $Arg -replace '://(www\.)?youtube\.com', '://music.youtube.com' } else {
            $html = (Invoke-WebRequest "https://www.youtube.com/results?search_query=$([uri]::EscapeDataString($Arg))&sp=EgIQAw%253D%253D" -UseBasicParsing).Content
            $m = [regex]::Match($html, '"lockupViewModel":\{"contentImage".*?"contentId":"([\w-]+)".*?"title":\{"content":"(.*?)"')
            if (-not $m.Success) { "No playlists for '$Arg'."; break }
            $title = [regex]::Unescape($m.Groups[2].Value)
            "https://music.youtube.com/watch?list=$($m.Groups[1].Value)"   # watch?list= starts playing; /playlist would only show it
        }
        # the installed app (a Chrome/Edge web app): its Start menu shortcut, opened straight at this playlist
        $lnk = Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu\Programs" -Recurse -Filter "YouTube Music*.lnk" -EA 0 | Select-Object -First 1
        $sc = if ($lnk) { (New-Object -ComObject WScript.Shell).CreateShortcut($lnk.FullName) }
        Add-Type -AssemblyName UIAutomationClient  # one window: close the app's old one, or two playlists end up playing at once
        [Windows.Automation.AutomationElement]::RootElement.FindAll("Children", [Windows.Automation.Condition]::TrueCondition) |
            Where-Object { $_.Current.Name -match '^YouTube Music' -or $_.Current.Name -match '\| YouTube Music$' } |
            ForEach-Object { try { $_.GetCurrentPattern([Windows.Automation.WindowPattern]::Pattern).Close() } catch {} }
        Start-Sleep -Milliseconds 800
        if ($sc -and $sc.Arguments -match '--app-id=') { Start-Process $sc.TargetPath "$($sc.Arguments) --app-launch-url-for-shortcuts-menu-item=$url"; $where = "the YouTube Music app" }
        else { Start-Process $url; $where = "the browser (no YouTube Music app installed)" }
        Start-Sleep 6
        $s = MediaSession
        "Opened in $where" + $(if ($title) { ": $title" }) + " ($url). " + $(if ($s) { "music: $(MediaState $s)" } else { "Nothing reports playing yet: it may need a click on play." })
    }
    "open" {
        $known = @{ downloads = "$HOME\Downloads"; documents = "$HOME\Documents"; desktop = "$HOME\Desktop"; pictures = "$HOME\Pictures"
            music = "$HOME\Music"; videos = "$HOME\Videos"; youtube = "https://www.youtube.com"; instagram = "https://www.instagram.com"
            tiktok = "https://www.tiktok.com"; facebook = "https://www.facebook.com"; x = "https://x.com"; gmail = "https://mail.google.com"
            panel = "http://127.0.0.1:18790" }
        $target = $known[$Arg.ToLower()]
        if ($target) { Start-Process $target; "Opened: $target"; break }
        OpenThing $Arg
    }
    "close" {
        $ours = Ours
        $ps = Get-Process | ? { $ours -notcontains $_.Id } | ? { $_.ProcessName -like "*$Arg*" -or ($_.MainWindowTitle -and $_.Product -like "*$Arg*") }
        if (-not $ps) { "No open program called '$Arg'."; break }
        $ps | % { $null = $_.CloseMainWindow() }; Start-Sleep 2
        $ps | ? { -not $_.HasExited } | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep 1
        $left = @($ps | ? { -not $_.HasExited })
        if ($left) { "NOT closed (still running): $(($left.ProcessName | select -Unique) -join ', ')"; break }
        "Closed: $(($ps.ProcessName | select -Unique) -join ', ')"
    }
    "find" {
        $c = New-Object -ComObject ADODB.Connection
        $c.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
        $q = $Arg.Replace("'", "''")
        $r = $c.Execute("SELECT TOP 10 System.ItemUrl FROM SYSTEMINDEX WHERE System.FileName LIKE '%$q%' ORDER BY System.DateModified DESC")
        $any = $false
        while (-not $r.EOF) { $any = $true; ([uri]$r.Fields.Item(0).Value).LocalPath; $r.MoveNext() }
        if (-not $any) { "Nothing in the Windows index for '$Arg'. Code folders are often not indexed: try Get-ChildItem <folder> -Recurse -Depth 4 -Filter '*$Arg*'" }
    }
    "screenshot" {
        Add-Type -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();' -Name D -Namespace FrjPc
        [FrjPc.D]::SetProcessDPIAware() | Out-Null
        Add-Type -AssemblyName System.Windows.Forms, System.Drawing
        $b = [Windows.Forms.SystemInformation]::VirtualScreen
        $bmp = New-Object Drawing.Bitmap $b.Width, $b.Height
        [Drawing.Graphics]::FromImage($bmp).CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
        $out = Join-Path $Root "data\screen.jpg"; $bmp.Save($out, [Drawing.Imaging.ImageFormat]::Jpeg); $out
    }
    default { "Actions: music, volume, open, close, apps, click, keys, whatsapp-me, find, screenshot, youtube, youtube-link, ytmusic, pc-status, clipboard, copy, type, modes, mode" }
}
