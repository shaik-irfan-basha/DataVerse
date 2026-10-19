"""
paths.py - Centralized Cross-Platform Application Paths & User Data Manager

Architectural Separation:
1. Bundle Directory (Read-Only):
   - In frozen mode (PyInstaller): sys._MEIPASS (contains frontend/, sample_data/)
   - In source mode: repository root
2. User Data Directory (Writable):
   - In frozen/installed mode: %LOCALAPPDATA%\\DataVerse (Windows) or ~/.local/share/dataverse
   - In source mode: repository root (or DATAVERSE_DATA_DIR / %LOCALAPPDATA%\\DataVerse if configured)
3. Safe Migration:
   - Non-destructive copy with timestamped backup; never deletes user databases.
"""

import os
import sys
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("dataverse.paths")


def is_frozen() -> bool:
    """Returns True if running inside a PyInstaller frozen bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_bundle_dir() -> Path:
    """
    Returns the root directory of the application bundle.
    In frozen mode: sys._MEIPASS
    In source mode: repository root
    """
    if is_frozen():
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent


def get_frontend_dir() -> Path:
    """Returns the path to the Web Studio frontend assets."""
    return get_bundle_dir() / "frontend"


def get_sample_data_dir() -> Path:
    """Returns the path to the sample demo data assets."""
    return get_bundle_dir() / "sample_data"


def get_default_local_appdata_dir() -> Path:
    """Returns the OS standard per-user local application data directory."""
    if sys.platform == "win32":
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "DataVerse"
        app_data = os.getenv("APPDATA")
        if app_data:
            return Path(app_data) / "DataVerse"
        return Path.home() / "AppData" / "Local" / "DataVerse"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "DataVerse"
    else:
        xdg_data = os.getenv("XDG_DATA_HOME")
        if xdg_data:
            return Path(xdg_data) / "dataverse"
        return Path.home() / ".local" / "share" / "dataverse"


def get_user_data_dir() -> Path:
    """
    Returns the writable user data directory.
    Priority:
    1. DATAVERSE_DATA_DIR environment variable
    2. If frozen (installed): standard OS local app data (%LOCALAPPDATA%\\DataVerse)
    3. If DATAVERSE_USE_USER_DATA_DIR=true: standard OS local app data
    4. Source development mode default: repository root
    """
    custom_dir = os.getenv("DATAVERSE_DATA_DIR")
    if custom_dir:
        p = Path(custom_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    if is_frozen() or os.getenv("DATAVERSE_USE_USER_DATA_DIR", "").lower() in ("true", "1", "yes"):
        p = get_default_local_appdata_dir()
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Source development mode default: repository root
    return Path(__file__).resolve().parent


def get_temp_session_dir() -> Path:
    """
    Returns the writable directory for temporary session databases and uploads.
    In frozen/installed mode: %LOCALAPPDATA%\\DataVerse\\temp_sessions
    In source mode: <user_data_dir>\\temp_sessions (or DATAVERSE_TEMP_DIR override)
    """
    custom_temp = os.getenv("DATAVERSE_TEMP_DIR")
    if custom_temp:
        p = Path(custom_temp).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    p = get_user_data_dir() / "temp_sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_log_dir() -> Path:
    """Returns the writable directory for rotating application logs."""
    custom_log_dir = os.getenv("DATAVERSE_LOG_DIR")
    if custom_log_dir:
        p = Path(custom_log_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    p = get_user_data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_log_file_path() -> Path:
    """Returns the complete file path for the primary application log."""
    return get_log_dir() / "dataverse.log"


def get_metadata_db_path() -> Path:
    """
    Returns the path to the persistent metadata database (dataverse_meta.db).
    Automatically triggers non-destructive migration if migrating from legacy path.
    """
    custom_path = os.getenv("DATAVERSE_META_DB")
    if custom_path:
        return Path(custom_path).resolve()

    target_dir = get_user_data_dir()
    target_path = target_dir / "dataverse_meta.db"

    # In frozen mode, check if we need to migrate an existing database
    if is_frozen():
        legacy_path = get_bundle_dir() / "dataverse_meta.db"
        if legacy_path.exists() and not target_path.exists():
            safe_migrate_database(legacy_path, target_path)

    return target_path


def get_history_db_path() -> Path:
    """
    Returns the path to the persistent query history database (dataverse_history.db).
    Automatically triggers non-destructive migration if migrating from legacy path.
    """
    custom_path = os.getenv("DATAVERSE_HISTORY_DB")
    if custom_path:
        return Path(custom_path).resolve()

    target_dir = get_user_data_dir()
    target_path = target_dir / "dataverse_history.db"

    # In frozen mode, check if we need to migrate an existing database
    if is_frozen():
        legacy_path = get_bundle_dir() / "dataverse_history.db"
        if legacy_path.exists() and not target_path.exists():
            safe_migrate_database(legacy_path, target_path)

    return target_path


def safe_migrate_database(source_path: Path, target_path: Path) -> Tuple[bool, str]:
    """
    Safely copies a legacy SQLite database to a new target path without deleting source.
    Creates a backup copy with a timestamp to guard against data loss.
    """
    if not source_path.exists():
        return False, f"Source database '{source_path}' does not exist."

    if target_path.exists():
        return False, f"Target database '{target_path}' already exists; skipping migration."

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Create timestamped backup of the source before copying
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = source_path.with_name(f"{source_path.name}.bak_{ts}")
        shutil.copy2(source_path, backup_path)
        logger.info(f"Created pre-migration backup at '{backup_path}'")

        # Copy main database file
        shutil.copy2(source_path, target_path)

        # Copy WAL and SHM journal files if present
        for suffix in ("-wal", "-shm", "-journal"):
            src_aux = Path(f"{source_path}{suffix}")
            if src_aux.exists():
                dst_aux = Path(f"{target_path}{suffix}")
                shutil.copy2(src_aux, dst_aux)

        logger.info(f"Successfully migrated database from '{source_path}' to '{target_path}'")
        return True, f"Successfully migrated database to '{target_path}'"

    except PermissionError as pe:
        err_msg = f"Permission denied during database migration to '{target_path}': {pe}"
        logger.error(err_msg)
        return False, err_msg
    except Exception as e:
        err_msg = f"Unexpected failure during database migration: {e}"
        logger.error(err_msg)
        return False, err_msg


def get_icon_path() -> Optional[Path]:
    """
    Returns the path to the primary Windows .ico application icon if present.
    Checks bundle root and frontend/icons directory.
    """
    candidates = [
        get_bundle_dir() / "dataverse.ico",
        get_frontend_dir() / "icons" / "dataverse.ico",
        Path(__file__).resolve().parent / "dataverse.ico",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None
