param(
  [string]$InstallDir = (Join-Path $env:ProgramFiles "ReportChart"),
  [switch]$NoDesktopShortcut,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Test-IsAdmin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function New-ReportChartShortcut {
  param(
    [string]$ShortcutPath,
    [string]$TargetPath,
    [string]$Arguments = "",
    [string]$Description = "ReportChart Desktop"
  )

  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($ShortcutPath)
  $shortcut.TargetPath = $TargetPath
  $shortcut.Arguments = $Arguments
  $shortcut.WorkingDirectory = Split-Path -Parent $TargetPath
  $shortcut.IconLocation = "$TargetPath,0"
  $shortcut.Description = $Description
  $shortcut.Save()
}

$DesktopDir = Split-Path -Parent $PSCommandPath
$ExePath = Join-Path $DesktopDir "dist\ReportChart.exe"
$UninstallSource = Join-Path $DesktopDir "uninstall-windows.ps1"
$InstallExe = Join-Path $InstallDir "ReportChart.exe"
$InstallUninstaller = Join-Path $InstallDir "uninstall-windows.ps1"
$StartMenuDir = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\ReportChart"
$StartMenuShortcut = Join-Path $StartMenuDir "ReportChart.lnk"
$UninstallShortcut = Join-Path $StartMenuDir "Desinstalar ReportChart.lnk"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "ReportChart.lnk"

if (-not (Test-Path -LiteralPath $ExePath)) {
  throw "Executavel nao encontrado em $ExePath. Gere primeiro com .\desktop\build-windows-exe.ps1."
}

if (-not $DryRun -and -not (Test-IsAdmin)) {
  $arguments = @(
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$PSCommandPath`"",
    "-InstallDir", "`"$InstallDir`""
  )
  if ($NoDesktopShortcut) {
    $arguments += "-NoDesktopShortcut"
  }
  Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Verb RunAs
  exit
}

if ($DryRun) {
  Write-Host "Instalador ReportChart Desktop"
  Write-Host "Origem: $ExePath"
  Write-Host "Destino: $InstallExe"
  Write-Host "Menu iniciar: $StartMenuShortcut"
  if (-not $NoDesktopShortcut) {
    Write-Host "Area de trabalho: $DesktopShortcut"
  }
  Write-Host "O usuario final nao precisa instalar Python nem SQLite; eles estao no executavel."
  exit
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null

Copy-Item -LiteralPath $ExePath -Destination $InstallExe -Force
if (Test-Path -LiteralPath $UninstallSource) {
  Copy-Item -LiteralPath $UninstallSource -Destination $InstallUninstaller -Force
}

New-ReportChartShortcut -ShortcutPath $StartMenuShortcut -TargetPath $InstallExe

if (Test-Path -LiteralPath $InstallUninstaller) {
  New-ReportChartShortcut `
    -ShortcutPath $UninstallShortcut `
    -TargetPath "powershell.exe" `
    -Arguments "-ExecutionPolicy Bypass -File `"$InstallUninstaller`"" `
    -Description "Desinstalar ReportChart Desktop"
}

if (-not $NoDesktopShortcut) {
  New-ReportChartShortcut -ShortcutPath $DesktopShortcut -TargetPath $InstallExe
}

Write-Host ""
Write-Host "ReportChart Desktop instalado em: $InstallDir"
Write-Host "Python e SQLite nao precisam ser instalados no computador do usuario."
