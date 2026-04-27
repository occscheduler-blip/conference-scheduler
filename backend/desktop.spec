# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the desktop FastAPI sidecar."""
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# Collect packages with C extensions or dynamic imports.
ortools_datas, ortools_binaries, ortools_hiddenimports = collect_all("ortools")
supabase_datas, supabase_binaries, supabase_hiddenimports = collect_all("supabase")
gotrue_datas, gotrue_binaries, gotrue_hiddenimports = collect_all("gotrue")
postgrest_datas, postgrest_binaries, postgrest_hiddenimports = collect_all("postgrest")
realtime_datas, realtime_binaries, realtime_hiddenimports = collect_all("realtime")
storage3_datas, storage3_binaries, storage3_hiddenimports = collect_all("storage3")
psycopg_datas, psycopg_binaries, psycopg_hiddenimports = collect_all("psycopg")

extra_hidden = [
    *collect_submodules("uvicorn"),
    *collect_submodules("fastapi"),
    *collect_submodules("pydantic"),
    *collect_submodules("pydantic_settings"),
    *collect_submodules("jose"),
    *collect_submodules("passlib"),
    "bcrypt",
    "email_validator",
    "dotenv",
    "resend",
    "h11",
    "httpx",
    "httpcore",
    "anyio",
]

a = Analysis(
    ["desktop_main.py"],
    pathex=["."],
    binaries=[
        *ortools_binaries,
        *supabase_binaries,
        *gotrue_binaries,
        *postgrest_binaries,
        *realtime_binaries,
        *storage3_binaries,
        *psycopg_binaries,
    ],
    datas=[
        (".env", "."),
        *ortools_datas,
        *supabase_datas,
        *gotrue_datas,
        *postgrest_datas,
        *realtime_datas,
        *storage3_datas,
        *psycopg_datas,
    ],
    hiddenimports=[
        *ortools_hiddenimports,
        *supabase_hiddenimports,
        *gotrue_hiddenimports,
        *postgrest_hiddenimports,
        *realtime_hiddenimports,
        *storage3_hiddenimports,
        *psycopg_hiddenimports,
        *extra_hidden,
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "mypy", "tests"],
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
    name="conference-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="conference-backend",
)
