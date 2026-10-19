"""
tests/test_desktop_app.py - Automated Unit & Integration Tests for Shared WebView Desktop Wrapper
"""

import socket
import time
import urllib.request
import pytest
from desktop_app import (
    DataVerseDesktopApp,
    find_available_port,
    is_port_in_use,
    check_backend_health,
    wait_for_backend_ready
)


def test_is_port_in_use_detection():
    """Verifies port detection logic against active and inactive sockets."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.listen(1)
    try:
        assert is_port_in_use(port) is True
    finally:
        s.close()

    # Wait briefly for OS socket cleanup
    time.sleep(0.05)
    assert is_port_in_use(port) is False


def test_find_available_port_skips_occupied():
    """Verifies that find_available_port skips an occupied port and returns an open one."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    occupied_port = s.getsockname()[1]
    s.listen(1)
    try:
        chosen_port = find_available_port(start_port=occupied_port, max_attempts=10)
        assert chosen_port != occupied_port
        assert chosen_port > occupied_port
    finally:
        s.close()


def test_check_backend_health_offline():
    """Verifies that health check returns False when connecting to an inactive port."""
    unused_port = find_available_port(start_port=9500)
    assert check_backend_health(f"http://127.0.0.1:{unused_port}") is False


def test_desktop_app_lifecycle_and_frontend_serving():
    """
    Tests the complete lifecycle of DataVerseDesktopApp:
    1. Background server startup
    2. Health endpoint check
    3. Serving index.html and frontend assets
    4. Clean shutdown and thread join
    """
    port = find_available_port(start_port=8200)
    desktop_app = DataVerseDesktopApp(port=port)

    started = desktop_app.start_backend()
    assert started is True
    assert desktop_app.server_thread is not None
    assert desktop_app.server_thread.is_alive()

    try:
        # 1. Health check verification
        assert check_backend_health(desktop_app.app_url) is True

        # 2. Root HTML verification (App Shell)
        req_root = urllib.request.Request(
            desktop_app.app_url,
            headers={"Accept": "text/html"}
        )
        with urllib.request.urlopen(req_root, timeout=3.0) as res:
            assert res.status == 200
            html_content = res.read().decode("utf-8")
            assert "<!DOCTYPE html>" in html_content or "<html" in html_content
            assert "DataVerse" in html_content

        # 3. CSS stylesheet serving
        req_css = urllib.request.Request(f"{desktop_app.app_url}/css/style.css")
        with urllib.request.urlopen(req_css, timeout=3.0) as res:
            assert res.status == 200
            css_content = res.read().decode("utf-8")
            assert len(css_content) > 100

        # 4. JS module serving
        req_js = urllib.request.Request(f"{desktop_app.app_url}/js/app.js")
        with urllib.request.urlopen(req_js, timeout=3.0) as res:
            assert res.status == 200
            js_content = res.read().decode("utf-8")
            assert len(js_content) > 100

    finally:
        # 5. Clean shutdown verification
        desktop_app.stop_backend()
        assert not desktop_app.server_thread.is_alive()
        # Verify port is freed
        time.sleep(0.2)
        assert is_port_in_use(port) is False


def test_desktop_app_window_lifecycle_headless():
    """
    Tests webview window creation, callback execution, and clean destruction
    without leaving background processes.
    """
    port = find_available_port(start_port=8300)
    desktop_app = DataVerseDesktopApp(port=port)
    callback_executed = False

    def test_callback(window):
        nonlocal callback_executed
        callback_executed = True
        assert window is not None
        # Give WebView2 controller time to finish async initialization before destroying
        time.sleep(1.5)
        window.destroy()

    exit_code = desktop_app.run(on_ready=test_callback)
    assert exit_code == 0
    assert callback_executed is True
    # Ensure background server thread has fully joined
    desktop_app.stop_backend(timeout=5.0)
    assert not desktop_app.server_thread.is_alive()



def test_main_customtkinter_fallback_intact():
    """
    Verifies that the original CustomTkinter desktop interface (main.py)
    remains completely functional and instantiable as a fallback.
    """
    import main
    assert hasattr(main, "DataVerseApp")
    assert hasattr(main, "DataConnector")
    assert hasattr(main, "QueryService")


def test_run_bat_parsing_and_modes():
    """
    Regression test: Verifies that run.bat does not trigger Windows batch parser errors
    ('... was unexpected at this time.') and correctly dispatches supported flags.
    """
    import subprocess
    from pathlib import Path

    repo_dir = Path(__file__).resolve().parent.parent
    bat_path = repo_dir / "run.bat"
    assert bat_path.exists(), "run.bat must exist in repository root"

    # 1. Test --check flag
    res_check = subprocess.run(
        ["cmd.exe", "/c", str(bat_path), "--check"],
        capture_output=True,
        text=True,
        cwd=str(repo_dir)
    )
    assert res_check.returncode == 0
    assert "was unexpected at this time" not in res_check.stderr
    assert "was unexpected at this time" not in res_check.stdout
    assert "[OK] Environment check passed." in res_check.stdout

    # 2. Test --help flag
    res_help = subprocess.run(
        ["cmd.exe", "/c", str(bat_path), "--help"],
        capture_output=True,
        text=True,
        cwd=str(repo_dir)
    )
    assert res_help.returncode == 0
    assert "was unexpected at this time" not in res_help.stderr
    assert "was unexpected at this time" not in res_help.stdout
    assert "DataVerse Launcher Usage:" in res_help.stdout

    # 3. Test unknown argument handling
    res_unknown = subprocess.run(
        ["cmd.exe", "/c", str(bat_path), "--invalid-option-xyz"],
        capture_output=True,
        text=True,
        cwd=str(repo_dir)
    )
    assert "was unexpected at this time" not in res_unknown.stderr
    assert "was unexpected at this time" not in res_unknown.stdout
    assert "[WARNING] Unrecognized argument: --invalid-option-xyz" in res_unknown.stdout


def test_run_bat_desktop_test_mode_dispatch():
    """
    Verifies that run.bat --desktop passes through flags (like --test-mode)
    and exits cleanly with code 0 without hanging or parser errors.
    """
    import subprocess
    from pathlib import Path

    repo_dir = Path(__file__).resolve().parent.parent
    bat_path = repo_dir / "run.bat"

    res_desktop = subprocess.run(
        ["cmd.exe", "/c", str(bat_path), "--desktop", "--test-mode"],
        capture_output=True,
        text=True,
        cwd=str(repo_dir),
        timeout=30
    )
    assert res_desktop.returncode == 0
    assert "was unexpected at this time" not in res_desktop.stderr
    assert "was unexpected at this time" not in res_desktop.stdout
    assert "Launching DataVerse Desktop Studio [WebView2]" in res_desktop.stdout
