# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：backend/run.py → dist/merch-backend/

产物是「一个目录」，Electron 作为 extraResources 塞进 resources/backend/：
  merch-backend        服务 / --harness / --fetch 三合一入口
构建：cd backend && pyinstaller --noconfirm --clean merch-backend.spec
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

BACKEND = Path(SPECPATH)

datas = collect_data_files("browserforge") + collect_data_files("scrapling")

hiddenimports = collect_submodules("uvicorn") + collect_submodules("scrapling")

a = Analysis(
    [str(BACKEND / "run.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="merch-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="merch-backend",
)
