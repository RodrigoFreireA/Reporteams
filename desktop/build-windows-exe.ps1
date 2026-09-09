$ErrorActionPreference = "Stop"

$DesktopDir = $PSScriptRoot
$Root = Split-Path -Parent $DesktopDir
Set-Location $Root

$Python = $env:PYTHON
if (-not $Python) {
  $Python = "python"
}

$Venv = Join-Path $DesktopDir ".venv-exe"
$VenvPython = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
  & $Python -m venv $Venv
  if ($LASTEXITCODE -ne 0) {
    throw "Falha ao criar o ambiente virtual."
  }
}

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
  throw "Falha ao atualizar o pip."
}

& $VenvPython -m pip install -r (Join-Path $DesktopDir "requirements.txt")
if ($LASTEXITCODE -ne 0) {
  throw "Falha ao instalar as dependencias desktop."
}

$PlotlyPath = Join-Path $Root "static\vendor\plotly-2.32.0.min.js"
if (-not (Test-Path $PlotlyPath)) {
  New-Item -ItemType Directory -Force -Path (Split-Path $PlotlyPath) | Out-Null
  Invoke-WebRequest -Uri "https://cdn.plot.ly/plotly-2.32.0.min.js" -OutFile $PlotlyPath
}

$DistDir = Join-Path $DesktopDir "dist"
$BuildDir = Join-Path $DesktopDir "build"
$SpecPath = Join-Path $DesktopDir "reportchart-desktop.spec"

& $VenvPython -m PyInstaller --clean --noconfirm --distpath $DistDir --workpath $BuildDir $SpecPath
if ($LASTEXITCODE -ne 0) {
  throw "Falha ao gerar o executavel com PyInstaller."
}

Write-Host ""
Write-Host "Executavel gerado em: $DesktopDir\dist\ReportChart.exe"
