# Build from Windows using scripts/Build-Desktop.ps1.
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / 'desktop.py')],
    pathex=[str(root / 'backend')],
    binaries=[],
    datas=[(str(root / 'frontend'), 'frontend'),
           (str(root / '.build-assets/test-laps'), 'test-laps'),
           (str(root / '.build-assets/build-info.json'), '.')],
    hiddenimports=['webview.platforms.winforms', 'webview.platforms.edgechromium'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['pytest', 'tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='F1 Telemetry',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, icon=str(root / 'frontend/static/icons/app.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='F1 Telemetry')
