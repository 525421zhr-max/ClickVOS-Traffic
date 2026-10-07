param([switch]$Stop, [switch]$LocalOnly, [switch]$Open)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtime = Join-Path $repo 'outputs/tasks/unified-site-v1/runtime'
$cloudflare = Join-Path $runtime 'cloudflared.exe'
$pidFile = Join-Path $runtime 'tunnel-pid.txt'
Push-Location $repo
try {
    if ($Stop) {
        if (Test-Path -LiteralPath $pidFile) {
            $tunnelProcess = Get-Process -Id ([int](Get-Content -LiteralPath $pidFile)) -ErrorAction SilentlyContinue
            if ($tunnelProcess -and $tunnelProcess.Path -eq $cloudflare) { Stop-Process -InputObject $tunnelProcess }
            Remove-Item -LiteralPath $pidFile
        }
        wsl -d Ubuntu-24.04 -- /home/clickvos/.venvs/clickvos/bin/python scripts/manage_unified_site.py stop
        return
    }
    wsl -d Ubuntu-24.04 -- /home/clickvos/.venvs/clickvos/bin/python scripts/manage_unified_site.py start
    if ($LASTEXITCODE -ne 0) { throw 'Cannot start local workbench.' }
    if ($LocalOnly) {
        if ($Open) { Start-Process 'http://127.0.0.1:7882/' }
        return
    }
    if (Test-Path -LiteralPath $pidFile) {
        $existingTunnel = Get-Process -Id ([int](Get-Content -LiteralPath $pidFile)) -ErrorAction SilentlyContinue
        if ($existingTunnel -and $existingTunnel.Path -eq $cloudflare) {
            Write-Output 'Temporary connection is already running. Open http://127.0.0.1:7882/.'
            if ($Open) { Start-Process 'http://127.0.0.1:7882/' }
            return
        }
    }
    if (!(Test-Path -LiteralPath $cloudflare)) { throw 'cloudflared.exe missing. See docs/operations/unified-site.md for the official download and hash.' }
    $expectedHash = '86aee4017b26625cee8484c113558f48effa4cd47f7aa05fcf425604e5d2b23c'
    if ((Get-FileHash -LiteralPath $cloudflare -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) { throw 'cloudflared executable hash mismatch.' }
    $tunnelLog = Join-Path $runtime 'tunnel.log'
    $stdoutLog = Join-Path $runtime 'tunnel-stdout.log'
    $tunnelProcess = Start-Process -FilePath $cloudflare -ArgumentList @('tunnel','--url','http://127.0.0.1:7880','--protocol','http2','--no-autoupdate') -WindowStyle Hidden -RedirectStandardError $tunnelLog -RedirectStandardOutput $stdoutLog -PassThru
    [IO.File]::WriteAllText($pidFile,[string]$tunnelProcess.Id)
    for ($i=0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        $log = Get-Content -LiteralPath $tunnelLog -Raw -ErrorAction SilentlyContinue
        $match = [regex]::Match([string]$log,'https://[a-z0-9-]+\.trycloudflare\.com')
        if ($match.Success) {
            [IO.File]::WriteAllText((Join-Path $runtime 'tunnel-url.txt'),$match.Value)
            Write-Output 'Temporary HTTPS connection started. Open http://127.0.0.1:7882/.'
            if ($Open) { Start-Process 'http://127.0.0.1:7882/' }
            return
        }
        if ($tunnelProcess.HasExited) { break }
    }
    Write-Output 'HTTPS connection not ready. Local workbench is available at http://127.0.0.1:7882/.'
    if ($Open) { Start-Process 'http://127.0.0.1:7882/' }
} finally { Pop-Location }
