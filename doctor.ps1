# claude-setup-kit doctor for Windows: checks every tool install.ps1 recorded in ~\.claude\kit\installed.
# Uses no Claude tokens. Exit 0 = no FAIL (WARN lines are steps still waiting on you, e.g. a key).
#   .\doctor.ps1          all checks, including `claude mcp list` (starts MCP servers, up to ~2 min)
#   .\doctor.ps1 -Quick   skip the MCP connection check
param([switch]$Quick)
$H = $env:USERPROFILE; $CL = Join-Path $H '.claude'; $BIN = Join-Path $H '.local\bin'
$script:nfail = 0; $script:nwarn = 0
function Pass($m) { Write-Host "  PASS  $m" }
function Warn($m) { Write-Host "  WARN  $m" -ForegroundColor Yellow; $script:nwarn++ }
function Fail($m) { Write-Host "  FAIL  $m" -ForegroundColor Red; $script:nfail++ }
function Cmd($n) { Get-Command $n -ErrorAction SilentlyContinue | Select-Object -First 1 }

if (-not (Test-Path "$CL\kit\installed")) { Write-Host 'No ~\.claude\kit\installed: run install.ps1 first.'; exit 1 }
$Inst = @(Get-Content "$CL\kit\installed")
function Has($id) { $Inst -contains $id }
Write-Host "Checking: $($Inst -join ' ')"

$PY = $null; foreach ($n in @('python', 'py', 'python3')) { if ((Cmd $n) -and (& $n -c 'print(3)' 2>$null) -eq '3') { $PY = $n; break } }
if ($PY) { Pass "python ($PY)" } else { Fail 'Python 3 not found (hooks call python)' }
$GitBash = $null
foreach ($p in @("$env:ProgramFiles\Git\bin\bash.exe", "${env:ProgramFiles(x86)}\Git\bin\bash.exe", "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe", $env:CLAUDE_CODE_GIT_BASH_PATH)) { if ($p -and (Test-Path $p)) { $GitBash = $p; break } }
if ($GitBash) { Pass "Git Bash ($GitBash)" } else { Fail 'Git Bash not found: kit hooks run in it (winget install Git.Git)' }
# python inside Git Bash is what the hooks actually call
if ($GitBash) { $o = & $GitBash -lc 'python -c "print(3)"' 2>$null; if ($o -eq '3') { Pass 'python runs inside Git Bash' } else { Fail 'python is not on Git Bash PATH (hooks will fail): reinstall Python with "Add python.exe to PATH"' } }

$S = "$CL\settings.json"
try { $St = Get-Content $S -Raw | ConvertFrom-Json; Pass 'settings.json is valid JSON' } catch { Fail 'settings.json unreadable'; $St = $null }
function Plugin-On($id) {
  $on = $St -and $St.enabledPlugins -and ($St.enabledPlugins.PSObject.Properties | Where-Object { $_.Name -eq $id -and $_.Value -eq $true })
  if ($on) { Pass "plugin $id enabled" } else { Fail "plugin $id not enabled (claude plugin enable $id)" }
}
function Hook-Cmds($ev) { if ($St -and $St.hooks -and $St.hooks.$ev) { @($St.hooks.$ev | ForEach-Object { $_.hooks } | ForEach-Object { $_.command }) } else { @() } }
function Hook-On($ev, $needle, $what) {
  if ((Hook-Cmds $ev) | Where-Object { $_ -like "*$needle*" }) { Pass "hook ${ev}: $what" } else { Fail "hook $ev missing: $what ($needle) - re-run install.ps1" }
}
function Selftest($label, [scriptblock]$sb) { $o = & $sb 2>&1 | Out-String; if ($LASTEXITCODE -eq 0) { Pass "self-test: $label" } else { Fail "self-test failed: $label -> $($o.Trim().Split("`n")[-1])" } }

if (Has 'caveman') {
  Plugin-On 'caveman@caveman'
  $cfg = Join-Path $H '.config\caveman\config.json'
  if (Test-Path $cfg) { Pass "Caveman mode: $((Get-Content $cfg -Raw | ConvertFrom-Json).defaultMode)" } else { Warn 'no ~\.config\caveman\config.json (plugin default mode applies)' }
}
if (Has 'adhd') { Plugin-On 'i-have-adhd@i-have-adhd'; if (Test-Path "$CL\.i-have-adhd-always") { Pass 'i-have-adhd always on' } else { Warn 'i-have-adhd always-on flag missing' } }
if (Has 'ponytail') { Plugin-On 'ponytail@ponytail' }
if (Has 'context-mode') { Plugin-On 'context-mode@context-mode' }
if (Has 'rtk') {
  $hc = (Hook-Cmds 'PreToolUse') | Where-Object { $_ -like '*hook claude*' } | Select-Object -First 1
  if (-not $hc) { Fail 'hook PreToolUse missing: RTK - re-run install.ps1' }
  elseif ($GitBash) {
    # Run the hook exactly as settings.json has it, in Git Bash with a bare PATH, as Claude Code might.
    $out = '{"tool_name":"Bash","tool_input":{"command":"git status"}}' | & $GitBash -c "PATH=/usr/bin:/bin; $hc" 2>$null | Out-String
    if ($out -match 'rtk git status') { Pass "RTK hook rewrites commands ($hc)" } else { Fail "RTK hook is not rewriting commands ($hc)" }
  }
}
if (Has 'codegraph') { if (Cmd 'codegraph') { Pass 'codegraph' } else { Fail 'codegraph not on PATH' } }
if (Has 'graphify') {
  if (Cmd 'graphify') { Pass 'graphify CLI' } else { Fail 'graphify not on PATH' }
  if (Test-Path "$CL\skills\graphify\SKILL.md") { Pass 'graphify skill' } else { Fail 'graphify skill missing (graphify install --platform claude)' }
}
if (Has 'safety') {
  Selftest 'trashmv' { & $PY "$BIN\trashmv" --test }
  Selftest 'block-rm.py' { & $PY "$CL\hooks\block-rm.py" --test }
  Hook-On 'PreToolUse' 'block-rm.py' 'rm blocker (Bash tool only; the PowerShell tool is not covered)'
}
if (Has 'indexes') {
  Selftest 'codegraph-gate.py' { & $PY "$CL\hooks\codegraph-gate.py" --test }
  Hook-On 'SessionStart' 'ensure-indexes.sh' 'index build/refresh'
  Hook-On 'Stop' 'ensure-indexes.sh' 'index refresh after each turn'
  Hook-On 'UserPromptSubmit' 'codegraph-gate.py' 'CodeGraph context'
}
if (Has 'measure') {
  Selftest 'token-compare.py' { & $PY "$CL\hooks\token-compare.py" selftest }; Selftest 'token-daily.py' { & $PY "$CL\hooks\token-daily.py" selftest }
  Selftest 'token-monthly.py' { & $PY "$CL\hooks\token-monthly.py" selftest }
  schtasks /Query /TN 'claude-setup-kit token-monthly' *> $null
  if (Test-Path "$CL\kit\no-monthly-schedule") { Pass 'monthly report not scheduled (your choice at install)' }
  elseif ($LASTEXITCODE -eq 0) { Pass 'monthly token report scheduled (1st, 09:00)' } else { Fail 'monthly token report not scheduled: re-run install.ps1' }
}
if (Has 'rules') {
  if (Test-Path "$CL\CLAUDE.md") { Pass '~\.claude\CLAUDE.md present' } else { Fail '~\.claude\CLAUDE.md missing' }
  if ((Test-Path "$CL\CLAUDE.md") -and (Select-String -Path "$CL\CLAUDE.md" -Pattern '{{' -SimpleMatch -Quiet)) { Warn '~\.claude\CLAUDE.md still has {{...}} placeholders' }
}
if (Has 'supermemory') { Plugin-On 'supermemory@supermemory-plugins' }
if (Has 'cognee') {
  Plugin-On 'cognee-memory@cognee'
  if ($St.env.COGNEE_BACKEND -eq 'local') { Pass 'COGNEE_BACKEND=local' } else { Fail 'COGNEE_BACKEND is not local in settings.json env' }
  if ((Test-Path "$H\.cognee\.env") -and (Select-String -Path "$H\.cognee\.env" -Pattern '^LLM_API_KEY=.' -Quiet)) { Pass 'Cognee LLM_API_KEY set' } else { Warn 'Cognee: no LLM_API_KEY in ~\.cognee\.env yet' }
}
if (Has 'agentmemory') {
  Plugin-On 'agentmemory@agentmemory'
  try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://127.0.0.1:3111/agentmemory/livez | Out-Null; Pass 'agentmemory server answers' } catch { Warn 'agentmemory server not running (npx -y @agentmemory/agentmemory@latest)' }
}
if (Has 'remember') { Plugin-On 'remember@claude-plugins-official' }
if (Has 'routing') {
  if ($GitBash -and ((& $GitBash "$CL/hooks/routing-card.sh" 2>$null | Out-String) -match 'MODEL ROUTING ACTIVE')) { Pass 'routing card prints' } else { Fail 'routing-card.sh does not print the card' }
  Hook-On 'SessionStart' 'routing-card.sh' 'routing card'
}
if (Has 'model-selector') { foreach ($p in @('model-selector', 'model-router', 'handoff', 'cache-clock')) { Plugin-On "$p@claude-model-selector" } }
if (Has 'jev') {
  foreach ($c in @('jev', 'jev-gate')) { if (Test-Path "$BIN\$c.cmd") { Pass $c } else { Fail "$c missing" } }
  Hook-On 'PostToolUse' 'jev-hooks.py' 'Jev tool-output triage (shadow)'
  if ([Environment]::GetEnvironmentVariable('TYPESAFE_API_KEY', 'User') -or $env:TYPESAFE_API_KEY) { Pass 'TypeSafe key found' } else { Warn 'no TYPESAFE_API_KEY yet; jev exits 2 until then' }
}
if (Has 'mjudge') {
  if (Test-Path "$BIN\mjudge.cmd") { Pass 'mjudge' } else { Fail 'mjudge missing' }
  if ($env:GEMINI_API_KEY -or [Environment]::GetEnvironmentVariable('GEMINI_API_KEY', 'User') -or ((Test-Path "$H\.config\watch\.env") -and (Select-String -Path "$H\.config\watch\.env" -Pattern '^GEMINI_API_KEY=.' -Quiet))) { Pass 'GEMINI_API_KEY found' } else { Warn 'no GEMINI_API_KEY yet' }
}
if (Has 'deliberation') {
  Plugin-On 'deliberation@antonbabenko'
  if (Test-Path "$H\.config\deliberation\config.json") { Pass 'deliberation configured' } else { Warn 'deliberation not configured yet (run /deliberation:setup in Claude Code)' }
}
if (-not $Quick -and ((Has 'codegraph') -or (Has 'context-mode'))) {
  $job = Start-Job { claude mcp list 2>$null | Out-String }
  if (Wait-Job $job -Timeout 150) { $out = Receive-Job $job } else { Stop-Job $job; $out = '' }
  Remove-Job $job -Force
  foreach ($s in @(@('codegraph', 'codegraph'), @('context-mode', 'plugin:context-mode:context-mode'))) {
    if (-not (Has $s[0])) { continue }
    if ($out -match "(?m)^$([regex]::Escape($s[1])): .*Connected") { Pass "MCP $($s[1]) connected" } else { Fail "MCP $($s[1]) not connected (claude mcp list)" }
  }
}
Get-ChildItem $CL -Recurse -Depth 1 -Filter '*.kit-new' -ErrorAction SilentlyContinue | ForEach-Object { Warn "kit version not applied: $($_.FullName -replace '\.kit-new$','') (yours kept)" }
Write-Host ""; Write-Host "doctor: $($script:nfail) fail, $($script:nwarn) warn"
if ($script:nfail) { exit 1 } else { exit 0 }
