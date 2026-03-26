param(
    [Parameter(Position = 0)]
    [string]$Command = ""
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

$VenvDir = if ($env:VENV_DIR) { $env:VENV_DIR } else { Join-Path $RootDir ".venv" }
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { Join-Path $VenvDir "Scripts\python.exe" }
$PipBin = if ($env:PIP_BIN) { $env:PIP_BIN } else { Join-Path $VenvDir "Scripts\pip.exe" }

$RunDir = if ($env:RUN_DIR) { $env:RUN_DIR } else { Join-Path $RootDir ".run" }
$LogDir = if ($env:LOG_DIR) { $env:LOG_DIR } else { Join-Path $RootDir "logs" }
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$CbcHost = if ($env:CBC_HOST) { $env:CBC_HOST } else { "0.0.0.0" }
$CbcPort = if ($env:CBC_PORT) { $env:CBC_PORT } else { "8101" }
$HighsHost = if ($env:HIGHS_HOST) { $env:HIGHS_HOST } else { "0.0.0.0" }
$HighsPort = if ($env:HIGHS_PORT) { $env:HIGHS_PORT } else { "8102" }
$PulpApiHost = if ($env:PULP_API_HOST) { $env:PULP_API_HOST } else { "0.0.0.0" }
$PulpApiPort = if ($env:PULP_API_PORT) { $env:PULP_API_PORT } else { "8000" }

$PulpLogDir = if ($env:PULP_LOG_DIR) { $env:PULP_LOG_DIR } else { $LogDir }
$SolverRequestTimeout = if ($env:SOLVER_REQUEST_TIMEOUT) { $env:SOLVER_REQUEST_TIMEOUT } else { "30" }
$HighsThreads = if ($env:HIGHS_THREADS) { $env:HIGHS_THREADS } else { "4" }
$DatabaseUrl = if ($env:DATABASE_URL) { $env:DATABASE_URL } else { "" }

$CbcPidFile = Join-Path $RunDir "pulp-solver-cbc.pid"
$HighsPidFile = Join-Path $RunDir "pulp-solver-highs.pid"
$ApiPidFile = Join-Path $RunDir "pulp-api.pid"

$CbcStdoutLog = Join-Path $LogDir "pulp-solver-cbc.out.log"
$HighsStdoutLog = Join-Path $LogDir "pulp-solver-highs.out.log"
$ApiStdoutLog = Join-Path $LogDir "pulp-api.out.log"
$CbcStderrLog = Join-Path $LogDir "pulp-solver-cbc.err.log"
$HighsStderrLog = Join-Path $LogDir "pulp-solver-highs.err.log"
$ApiStderrLog = Join-Path $LogDir "pulp-api.err.log"

function Show-Usage {
    @"
Usage:
  .\install.windows.ps1 install
  .\install.windows.ps1 deploy
  .\install.windows.ps1 start-solvers
  .\install.windows.ps1 start-api
  .\install.windows.ps1 start-all
  .\install.windows.ps1 restart-all
  .\install.windows.ps1 stop-solvers
  .\install.windows.ps1 stop-api
  .\install.windows.ps1 stop-all
  .\install.windows.ps1 status

Environment overrides (examples):
  `$env:CBC_PORT='8101'; `$env:HIGHS_PORT='8102'; .\install.windows.ps1 start-all
  `$env:DATABASE_URL='postgresql://...'; .\install.windows.ps1 start-api
  `$env:DATABASE_URL='postgresql://...'; .\install.windows.ps1 deploy
"@
}

function Get-TrackedProcess {
    param(
        [string]$PidFile
    )

    if (-not (Test-Path -LiteralPath $PidFile)) {
        return $null
    }

    $pidLine = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $pidLine) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return $null
    }

    $pidText = $pidLine.ToString().Trim()
    if ([string]::IsNullOrWhiteSpace($pidText)) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return $null
    }

    try {
        return Get-Process -Id ([int]$pidText) -ErrorAction Stop
    } catch {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return $null
    }
}

function Require-Runtime {
    if (-not (Test-Path -LiteralPath $PythonBin)) {
        Write-Host "[error] Python runtime not found: $PythonBin"
        Write-Host "Run: .\install.windows.ps1 install"
        exit 1
    }
}

function Install-Deps {
    if (-not (Test-Path -LiteralPath $VenvDir)) {
        py -3 -m venv $VenvDir
    }

    & $PythonBin -m pip install --upgrade pip
    & $PythonBin -m pip install -r (Join-Path $RootDir "requirements.txt")
    Write-Host "[ok] Installed dependencies into $VenvDir"
}

function Start-BackgroundProcess {
    param(
        [string]$Name,
        [string]$PidFile,
        [string]$StdoutLog,
        [string]$StderrLog,
        [string]$ModulePath,
        [string]$BindHost,
        [string]$Port,
        [hashtable]$EnvironmentOverrides
    )

    $existing = Get-TrackedProcess -PidFile $PidFile
    if ($null -ne $existing) {
        Write-Host "[skip] $Name already running (pid=$($existing.Id))"
        return
    }

    if (-not (Test-Path -LiteralPath $StdoutLog)) {
        New-Item -ItemType File -Path $StdoutLog | Out-Null
    }
    if (-not (Test-Path -LiteralPath $StderrLog)) {
        New-Item -ItemType File -Path $StderrLog | Out-Null
    }

    $wrapperPath = Join-Path $RunDir "$Name.cmd"
    $wrapperLines = @(
        "@echo off",
        "setlocal",
        "cd /d `"$RootDir`"",
        "set `"PYTHONPATH=$RootDir`""
    )

    foreach ($entry in $EnvironmentOverrides.GetEnumerator()) {
        $wrapperLines += "set `"$($entry.Key)=$($entry.Value)`""
    }

    $wrapperLines += "`"$PythonBin`" -m uvicorn $ModulePath --host $BindHost --port $Port 1>> `"$StdoutLog`" 2>> `"$StderrLog`""
    Set-Content -LiteralPath $wrapperPath -Value $wrapperLines -Encoding ASCII

    $process = $null

    try {
        $process = Start-Process `
            -FilePath "cmd.exe" `
            -ArgumentList @("/c", $wrapperPath) `
            -WorkingDirectory $RootDir `
            -PassThru

        Set-Content -LiteralPath $PidFile -Value $process.Id
        Start-Sleep -Seconds 1

        if ($process.HasExited) {
            Write-Host "[error] Failed to start $Name. Check log: $StdoutLog"
            Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
            throw "Process exited immediately."
        }

        Write-Host "[ok] Started $Name (pid=$($process.Id))"
    } catch {
        if ($null -ne $process -and -not $process.HasExited) {
            taskkill /PID $process.Id /T /F | Out-Null
        }
        throw
    }
}

function Stop-BackgroundProcess {
    param(
        [string]$Name,
        [string]$PidFile
    )

    $process = Get-TrackedProcess -PidFile $PidFile
    if ($null -eq $process) {
        Write-Host "[skip] $Name is not running"
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    try {
        taskkill /PID $process.Id /T | Out-Null
    } catch {
    }

    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if ($null -eq (Get-TrackedProcess -PidFile $PidFile)) {
            Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
            Write-Host "[ok] Stopped $Name"
            return
        }
    }

    try {
        taskkill /PID $process.Id /T /F | Out-Null
    } catch {
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "[ok] Force-stopped $Name"
}

function Get-HealthCode {
    param(
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -Method Get -UseBasicParsing -TimeoutSec 3
        return [string]$response.StatusCode
    } catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [string][int]$_.Exception.Response.StatusCode
        }
        return "n/a"
    }
}

function Show-StatusProcess {
    param(
        [string]$Name,
        [string]$PidFile,
        [string]$Url = ""
    )

    $process = Get-TrackedProcess -PidFile $PidFile
    if ($null -eq $process) {
        Write-Host "[stopped] $Name"
        return
    }

    $message = "[running] {0,-18} pid={1}" -f $Name, $process.Id
    if ($Url) {
        $message = "$message health=$(Get-HealthCode -Url $Url)"
    }
    Write-Host $message
}

function Start-Solvers {
    Require-Runtime

    Start-BackgroundProcess `
        -Name "pulp-solver-cbc" `
        -PidFile $CbcPidFile `
        -StdoutLog $CbcStdoutLog `
        -StderrLog $CbcStderrLog `
        -ModulePath "app.connector_api.main:app" `
        -BindHost $CbcHost `
        -Port $CbcPort `
        -EnvironmentOverrides @{
            SOLVER_NAME = "CBC"
            PULP_LOG_DIR = $PulpLogDir
        }

    Start-BackgroundProcess `
        -Name "pulp-solver-highs" `
        -PidFile $HighsPidFile `
        -StdoutLog $HighsStdoutLog `
        -StderrLog $HighsStderrLog `
        -ModulePath "app.connector_api.main:app" `
        -BindHost $HighsHost `
        -Port $HighsPort `
        -EnvironmentOverrides @{
            SOLVER_NAME = "HIGHS"
            HIGHS_THREADS = $HighsThreads
            PULP_LOG_DIR = $PulpLogDir
        }
}

function Start-Api {
    Require-Runtime

    Start-BackgroundProcess `
        -Name "pulp-api" `
        -PidFile $ApiPidFile `
        -StdoutLog $ApiStdoutLog `
        -StderrLog $ApiStderrLog `
        -ModulePath "app.api.main:app" `
        -BindHost $PulpApiHost `
        -Port $PulpApiPort `
        -EnvironmentOverrides @{
            CBC_SOLVER_URL = "http://127.0.0.1:$CbcPort/solve"
            HIGHS_SOLVER_URL = "http://127.0.0.1:$HighsPort/solve"
            CPLEX_SOLVER_URL = ""
            SOLVER_REQUEST_TIMEOUT = $SolverRequestTimeout
            DATABASE_URL = $DatabaseUrl
            PULP_LOG_DIR = $PulpLogDir
        }
}

function Stop-Solvers {
    Stop-BackgroundProcess -Name "pulp-solver-cbc" -PidFile $CbcPidFile
    Stop-BackgroundProcess -Name "pulp-solver-highs" -PidFile $HighsPidFile
}

function Stop-Api {
    Stop-BackgroundProcess -Name "pulp-api" -PidFile $ApiPidFile
}

function Show-StatusAll {
    Show-StatusProcess -Name "pulp-solver-cbc" -PidFile $CbcPidFile -Url "http://127.0.0.1:$CbcPort/healthz"
    Show-StatusProcess -Name "pulp-solver-highs" -PidFile $HighsPidFile -Url "http://127.0.0.1:$HighsPort/healthz"
    Show-StatusProcess -Name "pulp-api" -PidFile $ApiPidFile -Url "http://127.0.0.1:$PulpApiPort/healthz"
    Write-Host "logs: $LogDir"
}

function Deploy-All {
    Write-Host "[info] Deploying current Python source from: $RootDir"
    Install-Deps
    Stop-Api
    Stop-Solvers
    Start-Solvers
    Start-Api
    Show-StatusAll
}

function Restart-All {
    Stop-Api
    Stop-Solvers
    Start-Solvers
    Start-Api
    Show-StatusAll
}

switch ($Command) {
    "install" { Install-Deps }
    "deploy" { Deploy-All }
    "start-solvers" { Start-Solvers }
    "start-api" { Start-Api }
    "start-all" {
        Start-Solvers
        Start-Api
    }
    "stop-solvers" { Stop-Solvers }
    "stop-api" { Stop-Api }
    "stop-all" {
        Stop-Api
        Stop-Solvers
    }
    "restart-all" { Restart-All }
    "status" { Show-StatusAll }
    { $_ -in @("", "-h", "--help", "help") } { Show-Usage }
    default {
        Write-Host "[error] Unknown command: $Command"
        Show-Usage
        exit 1
    }
}
