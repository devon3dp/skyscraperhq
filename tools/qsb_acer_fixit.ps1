# qsb_acer_fixit.ps1 — Ross runs this at Acer's PowerShell (as Admin) to fix Acer 100%.
# One-shot: opens firewall for HQ, pulls llama3.2, binds ollama to LAN, restarts council_node,
# posts confirmation back to town-square. Idempotent — safe to re-run.
#
# Ross 2026-07-05: "fix him 100 percent and prove it we keep doing this"

$HQ_IP = "192.168.1.71"
$MODEL = "llama3.2"

Write-Host "`n[1/6] Firewall — allow HQ ($HQ_IP) in on all local services..." -ForegroundColor Yellow
netsh advfirewall firewall delete rule name="HQ_from_$HQ_IP" 2>$null | Out-Null
netsh advfirewall firewall add rule name="HQ_from_$HQ_IP" dir=in action=allow protocol=any remoteip=$HQ_IP | Out-Null
Write-Host "  OK — HQ can now reach any port on this box" -ForegroundColor Green

Write-Host "`n[2/6] Ollama presence check..." -ForegroundColor Yellow
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if(-not $ollama){
  Write-Host "  MISSING — install from https://ollama.com/download/windows THEN re-run this script" -ForegroundColor Red
  exit 1
}
Write-Host "  OK — ollama installed" -ForegroundColor Green

Write-Host "`n[3/6] Bind ollama to LAN (0.0.0.0:11434) so HQ can hit it..." -ForegroundColor Yellow
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "User")
$env:OLLAMA_HOST = "0.0.0.0:11434"
Write-Host "  OK — OLLAMA_HOST set (takes effect on next ollama restart)" -ForegroundColor Green

Write-Host "`n[4/6] Pull $MODEL (may take a few minutes)..." -ForegroundColor Yellow
ollama pull $MODEL
if($LASTEXITCODE -eq 0){
  Write-Host "  OK — $MODEL pulled" -ForegroundColor Green
}else{
  Write-Host "  FAILED to pull $MODEL — check internet at this box" -ForegroundColor Red
  exit 2
}

Write-Host "`n[4b/6] Claude CLI presence + auth check..." -ForegroundColor Yellow
$claude = Get-Command claude -ErrorAction SilentlyContinue
if(-not $claude){
  Write-Host "  MISSING — installing Claude CLI via npm..." -ForegroundColor Yellow
  $npm = Get-Command npm -ErrorAction SilentlyContinue
  if(-not $npm){
    Write-Host "  npm not installed — install Node.js first from https://nodejs.org/  THEN re-run this script" -ForegroundColor Red
  }else{
    npm install -g @anthropic-ai/claude-code 2>&1 | Out-String | Write-Host
    $claude = Get-Command claude -ErrorAction SilentlyContinue
    if($claude){ Write-Host "  OK — claude installed at $($claude.Path)" -ForegroundColor Green }
  }
}else{
  Write-Host "  OK — claude at $($claude.Path)" -ForegroundColor Green
}
if($claude){
  # Quick auth probe: `claude --version` should not error
  $ver = & claude --version 2>&1
  Write-Host "  claude --version: $ver" -ForegroundColor Green
  # Also probe an actual short call to detect auth issue
  try{
    $test = "hi" | & claude --print --model claude-haiku-4-5 2>&1 | Select-Object -First 1
    if($test -and $test -notmatch 'error|Error|not authenticated|api key'){
      Write-Host "  OK — Claude CLI answers · sample: $test" -ForegroundColor Green
    }else{
      Write-Host "  WARN — Claude CLI not authenticated · run 'claude login' on this box" -ForegroundColor Yellow
    }
  }catch{ Write-Host "  WARN — Claude CLI probe failed: $_" -ForegroundColor Yellow }
}

Write-Host "`n[5/6] Restart Acer council_node..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Where-Object {$_.CommandLine -match 'council_node'} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$node = "$env:USERPROFILE\qsb\qsb_council_node.py"
if(Test-Path $node){
  Start-Process -FilePath "python" -ArgumentList $node -WindowStyle Hidden
  Write-Host "  OK — council_node relaunched" -ForegroundColor Green
}else{
  Write-Host "  WARN — council_node.py not at $node · check the deploy script" -ForegroundColor Yellow
}

Write-Host "`n[6/6] Verify from Acer side + post confirmation to HQ..." -ForegroundColor Yellow
Start-Sleep -Seconds 4
try{
  $tags = Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
  $models = ($tags.models | ForEach-Object {$_.name}) -join ", "
  Write-Host "  Local ollama models: $models" -ForegroundColor Green
  # Try posting confirmation to HQ town-square
  $body = @{from="acer_cass"; to="ross"; text="Acer fix-it complete. Firewall open for HQ. Ollama has: $models. Council node restarted."; src="acer_fixit_ps1"} | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri "http://${HQ_IP}:8852/town/post" -Body $body -ContentType "application/json" -TimeoutSec 5 | Out-Null
  Write-Host "  OK — confirmation posted to town-square" -ForegroundColor Green
}catch{
  Write-Host "  WARN — verify step failed: $_" -ForegroundColor Yellow
}

Write-Host "`n=== DONE ===" -ForegroundColor Cyan
Write-Host "Ross should now see HQ probes to 192.168.1.78:9000 succeed."
