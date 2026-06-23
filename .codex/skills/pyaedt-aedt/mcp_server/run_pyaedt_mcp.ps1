$ErrorActionPreference = "Stop"

$Server = Join-Path $PSScriptRoot "pyaedt_mcp_server.py"

$Candidates = @()

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($PythonCommand) {
    $Candidates += $PythonCommand.Source
}

$PyCommand = Get-Command py -ErrorAction SilentlyContinue
if ($PyCommand) {
    try {
        $Resolved = & $PyCommand.Source -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $Resolved) {
            $Candidates += $Resolved.Trim()
        }
    } catch {
    }
}

$CommonRoots = @(
    "$env:LOCALAPPDATA\Programs\Python",
    "C:\Program Files\Python*",
    "C:\Program Files\AnsysEM",
    "C:\Program Files\ANSYS Inc"
)

foreach ($Root in $CommonRoots) {
    if (-not $Root) {
        continue
    }
    Get-ChildItem -Path $Root -Recurse -Filter python.exe -ErrorAction SilentlyContinue |
        Select-Object -First 20 |
        ForEach-Object { $Candidates += $_.FullName }
}

$Candidates = $Candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

foreach ($Python in $Candidates) {
    try {
        & $Python $Server
        exit $LASTEXITCODE
    } catch {
    }
}

Write-Error "No usable Python executable found for PyAEDT MCP server. Install Python with PyAEDT or add python.exe to PATH."
exit 1
