$ErrorActionPreference = "Stop"

$repo = if ($env:SIPI_KICAD_MCP_REPO) { $env:SIPI_KICAD_MCP_REPO } else { throw "Set SIPI_KICAD_MCP_REPO to the KiCad MCP server repository path." }
$node = if ($env:NODE_EXE) { $env:NODE_EXE } else { "node" }
$kicadBin = if ($env:KICAD_BIN) { $env:KICAD_BIN } else { throw "Set KICAD_BIN to the KiCad bin directory, for example the directory containing kicad-cli.exe and python.exe." }
$entry = Join-Path $repo "dist\index.js"
$mcpHome = if ($env:SIPI_KICAD_MCP_HOME) { $env:SIPI_KICAD_MCP_HOME } else { Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")) "outputs\kicad_mcp_home" }

if ($node -ne "node" -and -not (Test-Path -LiteralPath $node)) {
  throw "Node not found: $node"
}
if (-not (Test-Path -LiteralPath $entry)) {
  throw "KiCAD MCP entrypoint not found. Run npm run build in $repo"
}
if (-not (Test-Path -LiteralPath $kicadBin)) {
  throw "KiCad 9.0 bin not found: $kicadBin"
}

$env:NODE_ENV = "production"
$env:LOG_LEVEL = if ($env:LOG_LEVEL) { $env:LOG_LEVEL } else { "info" }
$env:KICAD_MCP_LOG_LEVEL = if ($env:KICAD_MCP_LOG_LEVEL) { $env:KICAD_MCP_LOG_LEVEL } else { "warn" }
$env:KICAD_AUTO_LAUNCH = if ($env:KICAD_AUTO_LAUNCH) { $env:KICAD_AUTO_LAUNCH } else { "false" }
$env:KICAD_MCP_DEV = if ($env:KICAD_MCP_DEV) { $env:KICAD_MCP_DEV } else { "0" }
$env:KICAD_PYTHON = Join-Path $kicadBin "python.exe"
$env:PYTHONPATH = "$repo\.python-deps;$repo\python;$(Join-Path $kicadBin "Lib\site-packages")"
$env:PATH = "$kicadBin;$env:PATH"
$env:USERPROFILE = $mcpHome
$env:HOME = $mcpHome
$env:APPDATA = Join-Path $mcpHome "AppData\Roaming"
$env:LOCALAPPDATA = Join-Path $mcpHome "AppData\Local"

New-Item -ItemType Directory -Force -Path $env:APPDATA, $env:LOCALAPPDATA, (Join-Path $mcpHome ".kicad-mcp\logs") | Out-Null
$userSite = Join-Path $mcpHome "Documents\KiCad\9.0\3rdparty\Python311\site-packages"
New-Item -ItemType Directory -Force -Path $userSite | Out-Null
Set-Content -LiteralPath (Join-Path $userSite "sipi_kicad_mcp.pth") -Value @("$repo\.python-deps", "$repo\python") -Encoding UTF8

Set-Location $repo
& $node $entry
