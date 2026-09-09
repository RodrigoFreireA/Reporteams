# ReportChart Desktop

Esta pasta contem a versao local/desktop do ReportChart.

Ela nao duplica o projeto web. O launcher, o spec e o script de build ficam aqui, mas o executavel sempre empacota os arquivos atuais da raiz do workspace:

- `app.py`
- `generate_dashboard.py`
- `index.html`
- `static/`

Com isso, quando a versao web for atualizada, basta rodar o build novamente nesta pasta para gerar um `.exe` com a versao atual.

## Requisitos do usuario final

O usuario final nao precisa ter Python, SQLite, pip ou dependencias Python instaladas. O `ReportChart.exe` gerado pelo PyInstaller ja inclui o interpretador Python, o driver SQLite usado pelo SQLAlchemy e as bibliotecas necessarias para processar os arquivos.

## Gerar o executavel

No PowerShell, a partir da raiz do projeto:

```powershell
powershell -ExecutionPolicy Bypass -File .\desktop\build-windows-exe.ps1
```

O arquivo final fica em:

```text
desktop\dist\ReportChart.exe
```

## Instalar no Windows com permissao administrativa

Depois de gerar o executavel, rode:

```powershell
powershell -ExecutionPolicy Bypass -File .\desktop\install-windows.ps1
```

O instalador solicita UAC/admin automaticamente se necessario, copia o app para:

```text
C:\Program Files\ReportChart\ReportChart.exe
```

E cria atalhos no Menu Iniciar e na area de trabalho publica.

Para validar o que seria feito sem instalar:

```powershell
powershell -ExecutionPolicy Bypass -File .\desktop\install-windows.ps1 -DryRun
```

## Como funciona

O executavel sobe o Flask localmente em `127.0.0.1`, escolhe uma porta livre entre `5001` e `5100` e abre o navegador padrao do Windows. O usuario nao precisa acessar o site publicado.

Os dados locais ficam em:

```text
%LOCALAPPDATA%\ReportChart
```

O SQLite fica em:

```text
%LOCALAPPDATA%\ReportChart\instance\reportchart.db
```

Para usar outra pasta de dados, defina `REPORTCHART_DATA_DIR` antes de abrir o executavel.
