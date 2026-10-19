"""
tests/test_paths.py - Tests for Centralized Path Management & Safe Database Migration
"""

import os
import sys
import sqlite3
from pathlib import Path
import pytest
from paths import (
    is_frozen,
    get_bundle_dir,
    get_frontend_dir,
    get_sample_data_dir,
    get_default_local_appdata_dir,
    get_user_data_dir,
    get_temp_session_dir,
    get_log_dir,
    get_log_file_path,
    get_metadata_db_path,
    get_history_db_path,
    safe_migrate_database
)


def test_is_frozen_in_test_environment():
    """In standard pytest execution, is_frozen() must be False."""
    assert is_frozen() is False


def test_bundle_dir_and_assets_existence():
    """Verifies that bundle dir contains the required frontend and sample data assets."""
    bundle_dir = get_bundle_dir()
    assert bundle_dir.exists()

    frontend_dir = get_frontend_dir()
    assert frontend_dir.exists()
    assert (frontend_dir / "index.html").exists()

    sample_dir = get_sample_data_dir()
    assert sample_dir.exists()
    assert (sample_dir / "retail_demo.sqlite").exists()


def test_custom_data_dir_override(tmp_path, monkeypatch):
    """
    Verifies that setting DATAVERSE_DATA_DIR routes all writable paths
    (metadata, history, temp sessions, logs) into the specified directory.
    """
    custom_dir = tmp_path / "custom_dataverse_data"
    monkeypatch.setenv("DATAVERSE_DATA_DIR", str(custom_dir))

    user_dir = get_user_data_dir()
    assert user_dir == custom_dir
    assert user_dir.exists()

    meta_db = get_metadata_db_path()
    assert meta_db == custom_dir / "dataverse_meta.db"

    history_db = get_history_db_path()
    assert history_db == custom_dir / "dataverse_history.db"

    temp_dir = get_temp_session_dir()
    assert temp_dir == custom_dir / "temp_sessions"
    assert temp_dir.exists()

    log_dir = get_log_dir()
    assert log_dir == custom_dir / "logs"
    assert log_dir.exists()

    log_file = get_log_file_path()
    assert log_file == custom_dir / "logs" / "dataverse.log"


def test_simulated_frozen_mode(tmp_path, monkeypatch):
    """
    Simulates a PyInstaller frozen application environment.
    Verifies that bundle assets are read from _MEIPASS and writable data
    is routed to %LOCALAPPDATA%\\DataVerse rather than the bundle directory.
    """
    mock_bundle = tmp_path / "mock_meipass_bundle"
    mock_bundle.mkdir()
    (mock_bundle / "frontend").mkdir()
    (mock_bundle / "frontend" / "index.html").write_text("<!DOCTYPE html>")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mock_bundle), raising=False)
    monkeypatch.delenv("DATAVERSE_DATA_DIR", raising=False)

    assert is_frozen() is True
    assert get_bundle_dir() == mock_bundle
    assert get_frontend_dir() == mock_bundle / "frontend"

    # Writable user directory must NOT be inside the frozen bundle
    user_data = get_user_data_dir()
    assert user_data != mock_bundle
    if sys.platform == "win32":
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            assert str(Path(local_app_data)) in str(user_data)


def test_safe_database_migration(tmp_path):
    """
    Verifies that safe_migrate_database:
    1. Copies legacy database without deleting the original
    2. Creates a timestamped pre-migration backup
    3. Copies WAL journal files if present
    4. Refuses to overwrite an existing target database
    """
    source_dir = tmp_path / "legacy_source"
    source_dir.mkdir()
    source_db = source_dir / "legacy.db"

    # Create dummy SQLite database with data
    conn = sqlite3.connect(str(source_db))
    conn.execute("CREATE TABLE test_tab (id INT, val TEXT);")
    conn.execute("INSERT INTO test_tab VALUES (1, 'revanth');")
    conn.commit()
    conn.close()

    # Create dummy WAL file
    source_wal = Path(f"{source_db}-wal")
    source_wal.write_text("wal-content")

    target_dir = tmp_path / "migrated_target"
    target_db = target_dir / "dataverse_meta.db"

    # 1. First migration
    success, msg = safe_migrate_database(source_db, target_db)
    assert success is True
    assert target_db.exists()
    assert (Path(f"{target_db}-wal")).exists()

    # Verify data in target
    target_conn = sqlite3.connect(str(target_db))
    cur = target_conn.cursor()
    cur.execute("SELECT val FROM test_tab WHERE id = 1;")
    row = cur.fetchone()
    assert row[0] == "revanth"
    target_conn.close()

    # Verify source was NOT deleted
    assert source_db.exists()

    # Verify backup was created next to source
    backups = list(source_dir.glob("legacy.db.bak_*"))
    assert len(backups) == 1

    # 2. Second migration attempt: must safely skip because target already exists
    success_second, msg_second = safe_migrate_database(source_db, target_db)
    assert success_second is False
    assert "already exists" in msg_second
