# Enables Windows features required by Docker Desktop's WSL 2 backend.
# Run as Administrator. This script never restarts the computer.
$ErrorActionPreference = 'Stop'
$log = Join-Path (Split-Path -Parent $PSScriptRoot) 'runtime_setup.log'
"Started: $(Get-Date -Format o)" | Set-Content -LiteralPath $log
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    'ERROR: Administrator rights are required.' | Add-Content -LiteralPath $log
    exit 5
}
foreach ($feature in @('Microsoft-Windows-Subsystem-Linux', 'VirtualMachinePlatform')) {
    "Enabling: $feature" | Add-Content -LiteralPath $log
    & dism.exe /Online /Enable-Feature "/FeatureName:$feature" /All /NoRestart 2>&1 |
        Out-String | Add-Content -LiteralPath $log
    if ($LASTEXITCODE -notin @(0, 3010)) {
        "ERROR: DISM exit code $LASTEXITCODE for $feature" | Add-Content -LiteralPath $log
        exit $LASTEXITCODE
    }
}
"Completed Windows feature enablement: $(Get-Date -Format o). A restart may be required; this script did not restart." |
    Add-Content -LiteralPath $log
exit 0
