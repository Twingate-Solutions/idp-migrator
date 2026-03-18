# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for twingate-idp-migrator
# Build with: pyinstaller migrator.spec

block_cipher = None

a = Analysis(
    ["src/main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("src/ui/icons", "src/ui/icons"),
    ],
    hiddenimports=[
        # PySide6 modules used at runtime via dynamic import
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtSvg",
        "PySide6.QtNetwork",
        # structlog internals not always auto-detected
        "structlog._config",
        "structlog.contextvars",
        "structlog.stdlib",
        # pydantic v2 validator plugin
        "pydantic.v1.validators",
        # httpx transport
        "httpx._transports.default",
        "httpx._transports.asgi",
        # All src sub-packages (ensure they're included)
        "src",
        "src.api",
        "src.core",
        "src.ui",
        "src.utils",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "xmlrpc",
        "test",
        "distutils",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="twingate-idp-migrator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # --windowed: no terminal on Windows/macOS
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,    # None = host arch; overridden per-platform in CI
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
