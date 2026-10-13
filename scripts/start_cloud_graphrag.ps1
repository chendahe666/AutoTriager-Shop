# Run the local project UI against the privately configured Aura database.
$ErrorActionPreference = 'Stop'
$ragProject = Split-Path -Parent $PSScriptRoot
$ragPython = Join-Path $ragProject '.venv-rag\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ragPython)) {
    throw 'Create .venv-rag and install requirements-rag.txt first.'
}
if (-not (Test-Path -LiteralPath (Join-Path $ragProject '.local-demo\neo4j-aura\credentials.json'))) {
    throw 'Configure Aura from your private credential file first; do not paste credentials into source files.'
}
if (Get-NetTCPConnection -LocalPort 8788 -State Listen -ErrorAction SilentlyContinue) {
    Write-Output 'Port 8788 is already in use. Check http://127.0.0.1:8788/ before starting another server.'
    exit 0
}
Push-Location $ragProject
try {
    & $ragPython -m autotriager_shop.workbench --port 8788 --enable-graph-rag
} finally {
    Pop-Location
}
