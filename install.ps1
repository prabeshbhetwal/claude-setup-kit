# claude-setup-kit installer for Windows (PowerShell 5.1+). Idempotent: a second run changes nothing already in place.
#
#   .\install.ps1                         explain every tool, then ask which to install (recommended)
#   .\install.ps1 -Yes                    no questions: core tier only (no keys, no paid services)
#   .\install.ps1 -Tiers core,memory,routing,judge,deliberation
#   .\install.ps1 -Only caveman,rtk       just these tools (dependencies are added)
#   .\install.ps1 -List                   print the catalogue and exit
# Other options: -Skip id,id  -CavemanMode lite|full|ultra  -ModelSelectorZip PATH
#
# If scripts are blocked: powershell -ExecutionPolicy Bypass -File .\install.ps1
# Needs Git for Windows: the kit's hooks run in Git Bash ("shell": "bash" is set on each hook).
# Never overwrites: settings.json is merged (backup first); your own CLAUDE.md, guides and agents are kept and
# the kit's version is written next to them as *.kit-new. Third-party tools come from their own sources.
[CmdletBinding()]
param(
  [switch]$Yes, [string[]]$Tiers, [string[]]$Only, [string[]]$Skip,
  [ValidateSet('', 'lite', 'full', 'ultra')][string]$CavemanMode = '',
  [string]$ModelSelectorZip = '', [switch]$List
)
$ErrorActionPreference = 'Continue'
$KIT = $PSScriptRoot
$H = $env:USERPROFILE
$CL = Join-Path $H '.claude'
$BIN = Join-Path $H '.local\bin'
$TS = Get-Date -Format 'yyyyMMdd-HHmmss'
$TIERS_ALL = @('core', 'memory', 'routing', 'judge', 'deliberation')
$DEPS = @(@('indexes', 'codegraph'), @('indexes', 'graphify'), @('mjudge', 'jev'), @('model-selector', 'routing'))
$script:Sel = New-Object System.Collections.Generic.List[string]
$script:Todo = New-Object System.Collections.Generic.List[string]
$script:Failed = New-Object System.Collections.Generic.List[string]

function Ok($m) { Write-Host "  ok    $m" }
function Info($m) { Write-Host "  ..    $m" }
function Warn($m) { Write-Host "  WARN  $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "  FAIL  $m" -ForegroundColor Red; $script:Failed.Add($m) }
function Todo($m) { $script:Todo.Add($m) }
function Has($id) { $script:Sel.Contains($id) }
function Add($id) { if (-not (Has $id)) { $script:Sel.Add($id) } }
function Drop($id) { [void]$script:Sel.Remove($id) }
function Short($p) { $p.Replace($H, '~') }
function Split-Ids($a) { @($a | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }

$Catalog = @(Get-Content (Join-Path $KIT 'lib\catalog.txt') -Encoding UTF8 | Where-Object { $_ -and -not $_.StartsWith('#') } | ForEach-Object {
    $f = $_ -split '\|'
    [pscustomobject]@{ Id = $f[0]; Tier = $f[1]; Name = $f[2]; Licence = $f[3]; What = $f[4]; Helps = $f[5]; Needs = $f[6] }
  })
function Item($id) { $Catalog | Where-Object { $_.Id -eq $id } | Select-Object -First 1 }
function TierIds($t) { @($Catalog | Where-Object { $_.Tier -eq $t } | ForEach-Object { $_.Id }) }

if ($List) { foreach ($c in $Catalog) { '{0,-15} {1,-13} {2}' -f $c.Id, $c.Tier, $c.Name; "    $($c.What)" }; exit 0 }

$Interactive = -not ($Yes -or $Tiers -or $Only) -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected
function Ask($q, $default) {
  if (-not $Interactive) { return ($default -eq 'y') }
  $hint = if ($default -eq 'y') { 'Y/n' } else { 'y/N' }
  $a = Read-Host "$q [$hint]"
  if (-not $a) { $a = $default }
  return ($a -match '^(y|yes)$')
}
function Describe($id, $n) {
  $c = Item $id
  Write-Host ""; Write-Host "  $n. $($c.Name)  ($($c.Licence))"
  Write-Host "    What:  $($c.What)"; Write-Host "    Helps: $($c.Helps)"; Write-Host "    Needs: $($c.Needs)"
}
$TierTitle = @{
  core = 'CORE: token savers + safety. No keys, no accounts, no paid services.'
  memory = 'MEMORY: remembers decisions across sessions. Some need an account or an API key.'
  routing = 'MODEL ROUTING: cheapest model and effort per task, lean helper agents.'
  judge = 'JUDGE TOOLS: fast external yes/no triage. Need paid or free API keys.'
  deliberation = 'DELIBERATION: second opinions from GPT, Gemini, Grok or OpenRouter. Needs at least one provider.'
}

# ---------------------------------------------------------------- selection (nothing changes until preflight passes)
if ($Only) {
  foreach ($id in (Split-Ids $Only)) { if (-not (Item $id)) { Write-Host "Unknown tool: $id (see -List)"; exit 2 }; Add $id }
} elseif (-not $Interactive) {
  $t = Split-Ids $Tiers; if (-not $t) { $t = @('core') }
  foreach ($x in $t) {
    if ($TIERS_ALL -notcontains $x) { Write-Host "Unknown tier: $x (tiers: $($TIERS_ALL -join ' '))"; exit 2 }
    foreach ($id in (TierIds $x)) { Add $id }
  }
} else {
  Write-Host "claude-setup-kit: each tool is explained below; you choose what to install."
  Write-Host "Nothing is changed until all questions are answered."
  foreach ($t in $TIERS_ALL) {
    Write-Host ""; Write-Host "=== $($TierTitle[$t])"
    $ids = @(TierIds $t); for ($i = 0; $i -lt $ids.Count; $i++) { Describe $ids[$i] ($i + 1) }
    # Checkbox menu: [x]/[ ] per tool, toggle by number until Enter. Core starts ticked.
    $on = New-Object System.Collections.Generic.HashSet[string]
    if ($t -eq 'core') { foreach ($id in $ids) { [void]$on.Add($id) } }
    while ($true) {
      Write-Host ""
      for ($i = 0; $i -lt $ids.Count; $i++) { $m = if ($on.Contains($ids[$i])) { 'x' } else { ' ' }; Write-Host "  [$m] $($i + 1). $((Item $ids[$i]).Name)" }
      $a = Read-Host '  Type numbers to tick/untick (e.g. 1 3), a = all, n = none, Enter = done'
      if (-not $a) { break }
      foreach ($w in ($a -split '[\s,]+' | Where-Object { $_ })) {
        if ($w -eq 'a') { foreach ($id in $ids) { [void]$on.Add($id) } }
        elseif ($w -eq 'n') { $on.Clear() }
        elseif ($w -match '^\d+$' -and [int]$w -ge 1 -and [int]$w -le $ids.Count) { $id = $ids[[int]$w - 1]; if (-not $on.Remove($id)) { [void]$on.Add($id) } }
        else { Write-Host "  no tool $w" }
      }
    }
    foreach ($id in $ids) { if ($on.Contains($id)) { Add $id } }
  }
}
# Your own copy of the kit may carry the pack in private\ (pack-private.sh; gitignored, never published).
if (-not $ModelSelectorZip -and (Test-Path (Join-Path $KIT 'private\claude-model-selector.zip'))) { $ModelSelectorZip = Join-Path $KIT 'private\claude-model-selector.zip' }
if ((Has 'model-selector') -and -not $ModelSelectorZip) {
  if ($Interactive) { $ModelSelectorZip = Read-Host '  Path to your Model Selector zip (Enter to skip)' }
  if (-not $ModelSelectorZip) { Drop 'model-selector'; Info 'Model Selector pack skipped (no zip given)' }
}
# Skips first: a skipped tool also removes whatever needs it, so dependencies never pull it back in.
$skipList = New-Object System.Collections.Generic.List[string]
foreach ($id in (Split-Ids $Skip)) { if (-not (Item $id)) { Write-Host "Unknown tool in -Skip: $id (see -List)"; exit 2 }; $skipList.Add($id) }
foreach ($id in @($skipList)) {
  Drop $id
  foreach ($p in $DEPS) { if ($p[1] -eq $id -and (Has $p[0])) { Drop $p[0]; $skipList.Add($p[0]); Info "$((Item $p[0]).Name) skipped too (needs $((Item $id).Name))" } }
}
foreach ($p in $DEPS) {
  if ((Has $p[0]) -and -not (Has $p[1]) -and -not $skipList.Contains($p[1])) { Add $p[1]; Info "$((Item $p[0]).Name) needs $((Item $p[1]).Name): added" }
}
if ($script:Sel.Count -eq 0) { Write-Host 'Nothing selected. Nothing changed.'; exit 0 }
if ((Has 'caveman') -and -not $CavemanMode) {
  $CavemanMode = 'ultra'
  if ($Interactive) { $a = Read-Host '  Caveman strength: lite, full, ultra [ultra]'; if ($a -in @('lite', 'full', 'ultra')) { $CavemanMode = $a } }
}
Write-Host ""; Write-Host "Installing: $($script:Sel -join ' ')"

# ---------------------------------------------------------------- preflight (before any change)
if (-not ($env:OS -eq 'Windows_NT' -or $env:KIT_ALLOW_NON_WINDOWS -eq '1')) {
  Write-Host 'install.ps1 is for Windows. On macOS run ./install.sh.'; exit 1
}
$missing = New-Object System.Collections.Generic.List[string]
function Cmd($n) { Get-Command $n -ErrorAction SilentlyContinue | Select-Object -First 1 }
# The Microsoft Store "python" alias exists without Python installed: actually run it.
$PY = $null
foreach ($n in @('python', 'py', 'python3')) { if ((Cmd $n) -and (& $n -c 'import sys; print(sys.version_info[0])' 2>$null) -eq '3') { $PY = $n; break } }
if (-not $PY) { $missing.Add('Python 3: winget install Python.Python.3.12 (tick "Add python.exe to PATH")') }
$GitBash = $null
foreach ($p in @("$env:ProgramFiles\Git\bin\bash.exe", "${env:ProgramFiles(x86)}\Git\bin\bash.exe", "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe", $env:CLAUDE_CODE_GIT_BASH_PATH)) {
  if ($p -and (Test-Path $p)) { $GitBash = $p; break }
}
if (-not $GitBash -or -not (Cmd 'git')) { $missing.Add('Git for Windows (hooks run in Git Bash): winget install Git.Git') }
$pluginIds = @('caveman', 'adhd', 'ponytail', 'context-mode', 'codegraph', 'supermemory', 'cognee', 'agentmemory', 'remember', 'model-selector', 'deliberation')
if (($pluginIds | Where-Object { Has $_ }) -and -not (Cmd 'claude')) { $missing.Add('Claude Code CLI: https://docs.claude.com/en/docs/claude-code/setup') }
if ((@('context-mode', 'codegraph', 'agentmemory') | Where-Object { Has $_ }) -and -not (Cmd 'node')) { $missing.Add('Node.js 20+: winget install OpenJS.NodeJS.LTS') }
if ((Has 'graphify') -and -not ((Cmd 'uv') -or (Cmd 'pipx'))) { $missing.Add('uv: winget install astral-sh.uv') }
if ((Has 'rtk') -and -not (Cmd 'rtk') -and -not (Cmd 'winget')) { $missing.Add('winget (App Installer from the Microsoft Store), used to install RTK') }
if ($missing.Count) {
  Write-Host 'Missing before anything can be installed:'; $missing | ForEach-Object { Write-Host "  - $_" }
  Write-Host 'Install these, open a new PowerShell window, then run .\install.ps1 again. Nothing was changed.'
  exit 1
}
foreach ($d in @($CL, "$CL\hooks", "$CL\agents", "$CL\guides", "$CL\rules", "$CL\kit", $BIN)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
$env:KIT_RTK = 'rtk'

# ---------------------------------------------------------------- helpers
# Copy-Kit SRC DST replace|keep: replace backs a differing DST up to DST.bak-kit-<time>; keep writes DST.kit-new.
function Copy-Kit($src, $dst, $pol) {
  if ((Test-Path $dst) -and ((Get-FileHash $src).Hash -eq (Get-FileHash $dst).Hash)) { Ok "unchanged $(Short $dst)"; return }
  if ((Test-Path $dst) -and $pol -eq 'keep') {
    Copy-Item $src "$dst.kit-new" -Force; Warn "kept your $(Short $dst); kit version at $(Short $dst).kit-new"
    Todo "Compare $(Short $dst) with $(Short $dst).kit-new and merge what you want."; return
  }
  if (Test-Path $dst) { Copy-Item $dst "$dst.bak-kit-$TS" -Force }
  Copy-Item $src $dst -Force; Ok "installed $(Short $dst)"
}
# Kit Python commands get a .cmd shim so they run by name from cmd and PowerShell.
function Install-Cmd($name) {
  Copy-Kit (Join-Path $KIT "files\bin\$name") (Join-Path $BIN $name) 'replace'
  $shim = Join-Path $BIN "$name.cmd"; $body = "@$PY `"%~dp0$name`" %*`r`n"
  if (-not (Test-Path $shim) -or (Get-Content $shim -Raw) -ne $body) { [IO.File]::WriteAllText($shim, $body); Ok "installed $(Short $shim)" }
}
function Claude-Json($argList) { try { (& claude @argList --json 2>$null | Out-String) | ConvertFrom-Json } catch { @() } }
function Plugin($src, $mp, $name) {
  $id = "$name@$mp"
  if (-not (@(Claude-Json @('plugin', 'marketplace', 'list')) | Where-Object { $_.name -eq $mp })) {
    Info "adding marketplace $src"
    & claude plugin marketplace add $src *> $null
    if ($LASTEXITCODE -ne 0) { Fail "marketplace add $src"; return $false }
  }
  $p = @(Claude-Json @('plugin', 'list')) | Where-Object { $_.id -eq $id } | Select-Object -First 1
  if ($p -and $p.enabled) { Ok "plugin $id already installed"; return $true }
  if ($p) { Warn "plugin $id is installed but disabled; left as you set it (claude plugin enable $id)"; return $true }
  & claude plugin install $id --scope user *> $null
  if ($LASTEXITCODE -eq 0) { Ok "plugin $id"; return $true }
  Fail "plugin install $id (run: claude plugin install $id)"; return $false
}
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User') }

# ---------------------------------------------------------------- rules + guides (first: later tools append to CLAUDE.md)
if (Has 'rules') {
  $rendered = Join-Path $env:TEMP "kit-claude-$TS.md"
  $prevSel = @(); if (Test-Path "$CL\kit\installed") { $prevSel = @(Get-Content "$CL\kit\installed") }
  $renderPy = @'
import re, sys
src, out, keep = sys.argv[1], sys.argv[2], set(sys.argv[3:])
text = open(src, encoding="utf-8").read()
text = re.sub(r"<!-- kit:([\w-]+) -->\n(.*?)<!-- /kit:\1 -->\n",
              lambda m: m.group(2) if m.group(1) in keep else "", text, flags=re.S)
open(out, "w", encoding="utf-8", newline="\n").write(text)
'@
  $rp = Join-Path $env:TEMP "kit-render-$TS.py"; [IO.File]::WriteAllText($rp, $renderPy)
  & $PY $rp (Join-Path $KIT 'files\CLAUDE.template.md') $rendered @($script:Sel) @prevSel
  $prev = "$CL\kit\CLAUDE.rendered.md"; $dst = "$CL\CLAUDE.md"
  $same = (Test-Path $prev) -and ((Get-FileHash $rendered).Hash -eq (Get-FileHash $prev).Hash)
  $prefix = $false
  if ((Test-Path $dst) -and -not $same) {
    $r = [IO.File]::ReadAllText($rendered); $d = [IO.File]::ReadAllText($dst)
    $prefix = $d.StartsWith($r)   # tools such as graphify append their own section
  }
  if ((Test-Path $dst) -and ($same -or $prefix)) { Ok "unchanged ~\.claude\CLAUDE.md" } else { Copy-Kit $rendered $dst 'keep' }
  Copy-Item $rendered $prev -Force
  if ((Test-Path $dst) -and (Select-String -Path $dst -Pattern '{{' -SimpleMatch -Quiet)) {
    Todo 'Fill the {{...}} placeholders in ~\.claude\CLAUDE.md (Identity section): your name, place and time zone, form of address, English variant.'
  }
  foreach ($g in @('coding', 'connectors-and-skills', 'knowledge-and-projects', 'token-tools')) { Copy-Kit (Join-Path $KIT "files\guides\$g.md") "$CL\guides\$g.md" 'keep' }
  if (Has 'routing') { Copy-Kit (Join-Path $KIT 'files\guides\agents-and-models.md') "$CL\guides\agents-and-models.md" 'keep' }
  Copy-Kit (Join-Path $KIT 'files\rules\coding-hard-rules.md') "$CL\rules\coding-hard-rules.md" 'keep'
}

# ---------------------------------------------------------------- core
if (Has 'caveman') {
  if (Plugin 'JuliusBrussee/caveman' 'caveman' 'caveman') {
    $cfg = Join-Path $H '.config\caveman\config.json'
    if (-not (Test-Path $cfg)) {
      New-Item -ItemType Directory -Force -Path (Split-Path $cfg) | Out-Null
      [IO.File]::WriteAllText($cfg, "{`n  `"defaultMode`": `"$CavemanMode`"`n}`n"); Ok "Caveman default mode: $CavemanMode"
    } else { Ok 'kept existing ~\.config\caveman\config.json' }
  }
}
if (Has 'adhd') {
  if (Plugin 'ayghri/i-have-adhd' 'i-have-adhd' 'i-have-adhd') {
    if (-not (Test-Path "$CL\.i-have-adhd-always")) { New-Item -ItemType File -Path "$CL\.i-have-adhd-always" | Out-Null }
    Ok 'i-have-adhd always on (delete ~\.claude\.i-have-adhd-always to turn off)'
  }
}
if (Has 'ponytail') { [void](Plugin 'DietrichGebert/ponytail' 'ponytail' 'ponytail') }
if (Has 'context-mode') { [void](Plugin 'mksglu/context-mode' 'context-mode' 'context-mode') }
if (Has 'rtk') {
  if (Cmd 'rtk') { Ok 'rtk already installed' }
  else {
    & winget install --id rtk-ai.rtk -e
    if ($LASTEXITCODE -eq 0) { Refresh-Path; Ok 'rtk (winget)' } else { Fail 'winget install rtk-ai.rtk (run it yourself to see why)' }
  }
  # The hook gets rtk's full path (forward slashes, for Git Bash): the hook PATH may not include it.
  $r = Cmd 'rtk'; if ($r) { $env:KIT_RTK = $r.Source.Replace('\', '/') }
}
if (Has 'codegraph') {
  if (Cmd 'codegraph') { Ok 'codegraph already installed' }
  else { & npm install -g '@colbymchenry/codegraph' *> $null; if ($LASTEXITCODE -eq 0) { Refresh-Path; Ok 'codegraph (npm)' } else { Fail 'npm install -g @colbymchenry/codegraph' } }
  & claude mcp get codegraph *> $null
  if ($LASTEXITCODE -eq 0) { Ok 'codegraph MCP server already registered' }
  else {
    # Windows: a .cmd launcher has to go through cmd /c for a stdio MCP server.
    & claude mcp add -s user codegraph -- cmd /c codegraph serve --mcp *> $null
    if ($LASTEXITCODE -eq 0) { Ok 'codegraph MCP server registered' } else { Fail 'claude mcp add codegraph' }
  }
}
if (Has 'graphify') {
  if (Cmd 'graphify') { Ok 'graphify already installed' }
  elseif (Cmd 'uv') { & uv tool install graphifyy *> $null; if ($LASTEXITCODE -eq 0) { Refresh-Path; Ok 'graphify (uv)' } else { Fail 'uv tool install graphifyy' } }
  else { & pipx install graphifyy *> $null; if ($LASTEXITCODE -eq 0) { Refresh-Path; Ok 'graphify (pipx)' } else { Fail 'pipx install graphifyy' } }
  if (Test-Path "$CL\skills\graphify\SKILL.md") { Ok 'graphify skill already installed' }
  elseif (Cmd 'graphify') { & graphify install --platform claude *> $null; if ($LASTEXITCODE -eq 0) { Ok 'graphify skill' } else { Fail 'graphify install --platform claude' } }
}
if (Has 'safety') { Install-Cmd 'trashmv'; Copy-Kit (Join-Path $KIT 'files\hooks\block-rm.py') "$CL\hooks\block-rm.py" 'replace' }
if (Has 'indexes') {
  foreach ($f in @('ensure-indexes.sh', 'codegraph-gate.py', 'kit-timeout')) { Copy-Kit (Join-Path $KIT "files\hooks\$f") "$CL\hooks\$f" 'replace' }
}
if (Has 'measure') {
  foreach ($f in @('token-scorecard.py', 'token-compare.py', 'token-daily.py', 'token-monthly.py')) { Copy-Kit (Join-Path $KIT "files\hooks\$f") "$CL\hooks\$f" 'replace' }
  New-Item -ItemType Directory -Force -Path "$CL\cache\token-compare\monthly" | Out-Null
  if (-not (Test-Path "$CL\cache\token-compare\change-date")) { [IO.File]::WriteAllText("$CL\cache\token-compare\change-date", (Get-Date -Format 'yyyy-MM-dd')) }
  # Freeze the week before install now, while those transcripts still exist.
  if (-not (Test-Path "$CL\cache\token-compare\before-week.json")) { & $PY "$CL\hooks\token-compare.py" *> $null; if ($LASTEXITCODE -eq 0) { Ok 'token baseline frozen (week before install)' } }
  # Monthly report: Task Scheduler runs token-monthly.py at 09:00 on the 1st. No Claude tokens. /F makes re-runs safe.
  $pyw = (Get-Command pythonw -ErrorAction SilentlyContinue | Select-Object -First 1).Source; if (-not $pyw) { $pyw = (Get-Command $PY).Source }
  schtasks /Create /F /SC MONTHLY /D 1 /ST 09:00 /TN 'claude-setup-kit token-monthly' /TR "`"$pyw`" `"$CL\hooks\token-monthly.py`"" *> $null
  if ($LASTEXITCODE -eq 0) { Ok 'monthly token report scheduled (1st of each month, 09:00; report in ~\.claude\cache\token-compare\monthly)' } else { Fail 'schtasks /Create claude-setup-kit token-monthly' }
}

# ---------------------------------------------------------------- memory
if (Has 'supermemory') { if (Plugin 'supermemoryai/claude-supermemory' 'supermemory-plugins' 'supermemory') { Todo 'Supermemory: start Claude Code and complete the Supermemory sign-in it opens (or set SUPERMEMORY_CC_API_KEY, see .env.example).' } }
if (Has 'cognee') { if (Plugin 'topoteretes/cognee-integrations' 'cognee' 'cognee-memory') { Todo 'Cognee: put LLM_PROVIDER, LLM_MODEL and LLM_API_KEY in ~\.cognee\.env (see .env.example). It builds its local server on the first session; that takes a few minutes.' } }
if (Has 'agentmemory') { if (Plugin 'rohitg00/agentmemory' 'agentmemory' 'agentmemory') { Todo 'agentmemory: start its server in a separate window: npx -y @agentmemory/agentmemory@latest (keep it running).' } }
if (Has 'remember') { [void](Plugin 'anthropics/claude-plugins-official' 'claude-plugins-official' 'remember') }

# ---------------------------------------------------------------- routing
if (Has 'routing') {
  Copy-Kit (Join-Path $KIT 'files\hooks\routing-card.sh') "$CL\hooks\routing-card.sh" 'replace'
  foreach ($f in (Get-ChildItem (Join-Path $KIT 'files\agents') -Filter *.md)) { Copy-Kit $f.FullName "$CL\agents\$($f.Name)" 'keep' }
}
if (Has 'model-selector') {
  $dest = "$CL\local-marketplaces"; New-Item -ItemType Directory -Force -Path $dest | Out-Null
  $tmp = Join-Path $env:TEMP "kit-ms-$TS"; Expand-Archive -Path $ModelSelectorZip -DestinationPath $tmp -Force
  $mj = Get-ChildItem $tmp -Recurse -Filter marketplace.json | Where-Object { $_.Directory.Name -eq '.claude-plugin' } | Select-Object -First 1
  if ($mj) {
    $m = Get-Content $mj.FullName -Raw | ConvertFrom-Json; $src = $mj.Directory.Parent.FullName
    if (-not (Test-Path "$dest\$($m.name)")) { Copy-Item $src "$dest\$($m.name)" -Recurse }
    foreach ($p in $m.plugins) { [void](Plugin "$dest\$($m.name)" $m.name $p.name) }
  } else { Fail "no .claude-plugin\marketplace.json in $ModelSelectorZip" }
}

# ---------------------------------------------------------------- judge
if (Has 'jev') {
  Install-Cmd 'jev'; Install-Cmd 'jev-gate'
  foreach ($f in @('jev_lib.py', 'jev-hooks.py', 'typesafe_key.py')) { Copy-Kit (Join-Path $KIT "files\hooks\$f") "$CL\hooks\$f" 'replace' }
  New-Item -ItemType Directory -Force -Path "$CL\jev" | Out-Null
  Copy-Kit (Join-Path $KIT 'files\jev\policy.json') "$CL\jev\policy.json" 'keep'
  Todo "Jev: set your TypeSafe key as a user environment variable (it is not echoed into history): `$k = Read-Host 'TypeSafe key'; [Environment]::SetEnvironmentVariable('TYPESAFE_API_KEY', `$k, 'User')   then restart Claude Code."
}
if (Has 'mjudge') {
  Install-Cmd 'mjudge'
  Todo 'mjudge: put GEMINI_API_KEY=... in ~\.config\watch\.env, or set it as a user environment variable. On Windows the Jev second opinion on images is skipped (it needs macOS sips); Gemini still answers.'
}

# ---------------------------------------------------------------- deliberation
if (Has 'deliberation') {
  if (Plugin 'antonbabenko/agent-plugins' 'antonbabenko' 'deliberation') {
    Todo 'Deliberation: set up at least one provider, then run /deliberation:setup in Claude Code. GPT: npm i -g @openai/codex; codex login. Grok: XAI_API_KEY. OpenRouter: OPENROUTER_API_KEY. Gemini: the agy CLI.'
  }
}

# ---------------------------------------------------------------- settings.json (merge, never overwrite)
Write-Host ""; Write-Host 'Merging hooks into ~\.claude\settings.json (backup written first if anything changes):'
& $PY (Join-Path $KIT 'lib\merge_settings.py') "$CL\settings.json" (Join-Path $KIT 'lib\hooks.windows.json') @($script:Sel)
if ($LASTEXITCODE -ne 0) { Fail 'settings merge' }
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ((@('safety', 'jev', 'mjudge') | Where-Object { Has $_ }) -and -not (($userPath -split ';') -contains $BIN)) {
  Todo "Add $(Short $BIN) to your user PATH: [Environment]::SetEnvironmentVariable('Path', `"`$([Environment]::GetEnvironmentVariable('Path','User'));$BIN`", 'User')   then open a new window. trashmv and jev live there."
}
$inst = @(); if (Test-Path "$CL\kit\installed") { $inst = @(Get-Content "$CL\kit\installed") }
[IO.File]::WriteAllLines("$CL\kit\installed", [string[]](@($inst + $script:Sel) | Where-Object { $_ } | Sort-Object -Unique))

# ---------------------------------------------------------------- report
Write-Host ""
if ($script:Failed.Count) { Write-Host 'Finished with problems:'; $script:Failed | ForEach-Object { Write-Host "  - $_" } } else { Write-Host 'Install finished with no errors.' }
Write-Host ""; Write-Host 'Still to do by hand:'
Todo 'Restart Claude Code (quit and reopen the desktop app, or start a new claude session) so plugins and hooks load.'
Todo "Check the install: $(Join-Path $KIT 'doctor.ps1')"
$n = 0; foreach ($t in $script:Todo) { $n++; Write-Host "  $n. $t" }
if ($script:Failed.Count) { exit 1 } else { exit 0 }
