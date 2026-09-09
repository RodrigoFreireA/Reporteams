param(
  [string]$InstallDir = (Join-Path $env:ProgramFiles "ReportChart"),
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Test-IsAdmin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

$InstallExe = Join-Path $InstallDir "ReportChart.exe"
$StartMenuDir = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\ReportChart"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "ReportChart.lnk"

if (-not $DryRun -and -not (Test-IsAdmin)) {
  $arguments = @(
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$PSCommandPath`"",
    "-InstallDir", "`"$InstallDir`""
  )
  Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Verb RunAs
  exit
}

if ($DryRun) {
  Write-Host "Desinstalador ReportChart Desktop"
  Write-Host "Removeria: $InstallDir"
  Write-Host "Removeria: $StartMenuDir"
  Write-Host "Removeria: $DesktopShortcut"
  exit
}

Get-Process ReportChart -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -eq $InstallExe } |
  Stop-Process -Force

Remove-Item -LiteralPath $DesktopShortcut -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $StartMenuDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "ReportChart Desktop removido."
