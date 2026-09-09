# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


DESKTOP_DIR = Path(SPECPATH)
ROOT_DIR = DESKTOP_DIR.parent

datas = [(str(ROOT_DIR / "index.html"), ".")]
for asset_root in (ROOT_DIR / "static", ROOT_DIR / "views"):
    for path in asset_root.rglob("*"):
        if path.is_file():
            datas.append((str(path), str(path.parent.relative_to(ROOT_DIR))))

a = Analysis(
    [str(DESKTOP_DIR / "launcher.py")],
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=["sqlite3"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["gunicorn"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ReportChart",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
