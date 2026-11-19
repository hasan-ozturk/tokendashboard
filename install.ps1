<#
.SYNOPSIS
  Installs the Token Dashboard skill for Claude Code and starts the dashboard (Windows).

.EXAMPLE
  .\install.ps1                                  # skill + start on http://localhost:8765
  .\install.ps1 -HostName tdb.local -AutoStart   # nicer URL (asks for admin once) + start at Windows logon
#>
param(
  [int]$Port = 8765,
  [string]$HostName = "",   # e.g. tdb.local; adds "127.0.0.1 <name>" to the hosts file (admin prompt)
  [switch]$AutoStart        # start the dashboard hidden at every Windows logon
)
$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot

# 1. Python 3 (stdlib only, nothing to pip install)
$python = $null
foreach ($cand in @("py -3", "python", "python3")) {
  $exe, $arg = $cand.Split(" ", 2)
  if (Get-Command $exe -ErrorAction SilentlyContinue) {
    $v = & $exe $(if ($arg) { $arg }) -c "import sys; print(sys.version_info[0])" 2>$null
    if ($v -eq "3") { $python = $cand; break }
  }
}
if (-not $python) { throw "Python 3 not found. Install it from https://www.python.org/downloads/ and run this script again." }
Write-Host "Python: $python"

# 2. Hosts entry for a short name (optional)
$hostLabel = "localhost"
if ($HostName) {
  $hosts = "$env:windir\System32\drivers\etc\hosts"
  if (-not (Select-String -Path $hosts -Pattern "\s$([regex]::Escape($HostName))\s*$" -Quiet)) {
    $tmp = Join-Path $env:TEMP "tdb-add-hosts.ps1"
    Set-Content -Path $tmp -Encoding ASCII -Value @"
Add-Content -Path '$hosts' -Value "`r`n127.0.0.1`t$HostName" -Encoding ascii
ipconfig /flushdns | Out-Null
"@
    Write-Host "Adding '127.0.0.1 $HostName' to the hosts file. Windows asks for admin rights."
    Start-Process powershell -Verb RunAs -Wait -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $tmp
    Remove-Item $tmp -ErrorAction SilentlyContinue
  }
  $hostLabel = $HostName
}
$baseUrl = "http://${hostLabel}:$Port"

# 3. Skill for Claude Code
$skillDir = Join-Path $env:USERPROFILE ".claude\skills\token-dashboard"
New-Item -ItemType Directory -Force $skillDir | Out-Null
$skill = [IO.File]::ReadAllText((Join-Path $repo "skill\token-dashboard\SKILL.md"), [Text.Encoding]::UTF8)
$skill = $skill.Replace("{{REPO_DIR}}", $repo).Replace("{{BASE_URL}}", $baseUrl).Replace("{{PORT}}", "$Port").Replace("{{PYTHON}}", $python)
[IO.File]::WriteAllText((Join-Path $skillDir "SKILL.md"), $skill, (New-Object Text.UTF8Encoding $false))
Write-Host "Skill installed: $skillDir"

# 4. Start at logon (optional): a hidden launcher in the Startup folder
$exe, $arg = $python.Split(" ", 2)
$exePath = (Get-Command $exe).Source
$cmdLine = "cmd /c cd /d ""$repo"" && set PORT=$Port && ""$exePath"" $arg cli.py dashboard --no-open"
if ($AutoStart) {
  $vbs = Join-Path ([Environment]::GetFolderPath("Startup")) "token-dashboard.vbs"
  Set-Content -Path $vbs -Encoding ASCII -Value "CreateObject(""WScript.Shell"").Run ""$($cmdLine.Replace('"', '""'))"", 0, False"
  Write-Host "Starts at logon: $vbs (delete this file to stop that)"
}

# 5. Start now unless it already runs
$running = $false
try { $running = (Invoke-WebRequest "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch {}
if (-not $running) {
  Start-Process cmd -ArgumentList "/c", $cmdLine.Substring(7) -WindowStyle Hidden
  Write-Host "Dashboard starting. The first scan of your transcripts can take a minute."
}
Write-Host ""
Write-Host "Open: $baseUrl"
Write-Host "In Claude Code, ask for the 'token dashboard' or 'what did this session cost' to get a link to the current session."
