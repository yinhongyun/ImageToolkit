# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for ImageToolkit (one-folder build)

a = Analysis(
    ['src\\app.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src\\resources\\styles\\app.qss', 'resources\\styles'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebChannel',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DRender',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtQuick',
        'PySide6.QtQuick3D',
        'PySide6.QtQml',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtSql',
        'PySide6.QtTest',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtPositioning',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtWebSockets',
        'tkinter',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ImageToolkit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='ImageToolkit',
)
