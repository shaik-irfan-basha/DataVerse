# -*- mode: python ; coding: utf-8 -*-
"""
dataverse.spec - PyInstaller Build Specification for DataVerse Desktop Studio
"""

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None
PROJECT_ROOT = os.path.abspath(SPECPATH)

# Explicit hidden imports for FastAPI, Uvicorn, and WebView2/pythonnet
hidden_imports = [
    # Uvicorn & ASGI runtime
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',

    # Web framework & validation
    'fastapi',
    'starlette',
    'pydantic',
    'pydantic_core',
    'multipart',

    # WebView2 & pythonnet runtime
    'webview',
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
    'pythonnet',
    'clr_loader',

    # Data analytics & plotting
    'pandas',
    'openpyxl',
    'matplotlib',
    'matplotlib.backends.backend_agg',
    'sqlite3',
    'requests',

    # Application core & routers
    'paths',
    'backend',
    'backend.app',
    'backend.config',
    'backend.session_manager',
    'backend.schemas',
    'cleaning_engine',
    'schema_engine',
    'metadata_manager',
    'query_service',
    'data_connector',
    'data_profiler',
    'chart_engine',
    'export_engine',
    'sql_validator',
    'sql_executor',
    'sql_recovery',
    'prompt_builder',
    'clarification_engine',
    'suggested_questions',
    'logger'
]

# Collect submodules
hidden_imports += collect_submodules('backend.routers')
hidden_imports += collect_submodules('uvicorn')
hidden_imports += collect_submodules('fastapi')

# Bundled data files (static assets only - NO user databases or secrets)
datas = [
    (os.path.join(PROJECT_ROOT, 'frontend'), 'frontend'),
    (os.path.join(PROJECT_ROOT, 'sample_data'), 'sample_data'),
    (os.path.join(PROJECT_ROOT, 'dataverse.ico'), '.'),
    (os.path.join(PROJECT_ROOT, 'LICENSE'), '.'),
]

# Collect pywebview runtime data
try:
    datas += collect_data_files('webview')
except Exception:
    pass

a = Analysis(
    ['desktop_app.py'],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=list(set(hidden_imports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'customtkinter',
        'tests',
        'eval',
        'logs',
        'temp_sessions'
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
    [],
    exclude_binaries=True,
    name='DataVerse',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # Keep console enabled initially for diagnosable logging & error reporting
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJECT_ROOT, 'dataverse.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DataVerse',
)
