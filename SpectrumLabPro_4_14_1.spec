# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('banco_materiais.json', '.'), ('assets/brands', 'assets/brands')],
    hiddenimports=['version', 'serial', 'serial.tools.list_ports', 'chemometrics', 'serial_worker', 'connection_worker', 'database', 'splash_screen', 'animated_chart', 'database_manager', 'pdf_generator', 'manual_control_dialog', 'auth_manager', 'auth_dialogs'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='SpectrumLabPro_4_14_1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
