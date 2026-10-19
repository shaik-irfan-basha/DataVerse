"""
desktop_app.py - DataVerse Lightweight Native Desktop Application

Shared WebView Desktop Wrapper:
- Embeds the production Web Studio interface inside a native Windows window using pywebview & WebView2.
- Automatically launches an in-process FastAPI backend on localhost.
- Performs port conflict resolution, active health-check readiness probing, and graceful lifecycle termination.
- Zero unnecessary native bridge exposure: maintains strict REST/WebSocket client isolation.
"""

import os
import sys
import time
import socket
import signal
import logging
import argparse
import threading
import urllib.request
import urllib.error
from typing import Optional, Callable

# Load environment configuration
from dotenv import load_dotenv
load_dotenv()

from logger import setup_logging
setup_logging()
logger = logging.getLogger("dataverse.desktop")

# Verify pywebview availability
try:
    import webview
except ImportError as err:
    logger.critical("pywebview is required for DataVerse Desktop. Install with: pip install pywebview")
    print(
        "\n[ERROR] pywebview is not installed.\n"
        "Please run: pip install pywebview\n"
        "Or use the CustomTkinter fallback interface: python main.py\n"
    )
    sys.exit(1)

import uvicorn
from backend.app import app
from paths import get_icon_path


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks if a network port is already bound on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def find_available_port(host: str = "127.0.0.1", start_port: int = 8000, max_attempts: int = 50) -> int:
    """
    Finds the first available port starting from start_port.
    If start_port is available, returns it immediately.
    """
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    # Fallback to system-assigned ephemeral port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def check_backend_health(url: str, timeout: float = 1.0) -> bool:
    """Pings the backend health endpoint and returns True if healthy."""
    try:
        req = urllib.request.Request(
            f"{url.rstrip('/')}/api/v1/health",
            headers={"User-Agent": "DataVerse-Desktop-HealthCheck/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def wait_for_backend_ready(url: str, max_wait_seconds: float = 15.0, poll_interval: float = 0.1) -> bool:
    """Polls backend health until it becomes responsive or timeout occurs."""
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        if check_backend_health(url, timeout=0.5):
            return True
        time.sleep(poll_interval)
    return False


class DataVerseDesktopApp:
    """
    Orchestrates the lifecycle of the in-process FastAPI backend
    and native WebView2 desktop window.
    """
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        debug: bool = False,
        title: str = "🔮 DataVerse — Enterprise Natural-Language Data Intelligence",
        width: int = 1280,
        height: int = 860,
        min_width: int = 960,
        min_height: int = 640
    ):
        # Strict local interface binding (never bind 0.0.0.0 for desktop app)
        if host not in ("127.0.0.1", "localhost"):
            logger.warning(f"Binding host '{host}' is non-standard for desktop; enforcing 127.0.0.1")
            host = "127.0.0.1"

        self.host = host
        self.port = port if port is not None else find_available_port(host=self.host, start_port=8000)
        self.debug = debug or os.getenv("DATAVERSE_DEBUG", "").lower() in ("true", "1", "yes")
        self.title = title
        self.width = width
        self.height = height
        self.min_size = (min_width, min_height)

        self.server: Optional[uvicorn.Server] = None
        self.server_thread: Optional[threading.Thread] = None
        self.window = None
        self._is_shutting_down = False
        self.app_url = f"http://{self.host}:{self.port}"

    def start_backend(self) -> bool:
        """Starts the FastAPI backend inside a background daemon thread."""
        logger.info(f"Starting in-process FastAPI server on {self.app_url}...")

        config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            log_level="warning" if not self.debug else "info",
            access_log=self.debug
        )
        self.server = uvicorn.Server(config)
        self.server_thread = threading.Thread(
            target=self.server.run,
            name="DataVerse-Uvicorn-Server",
            daemon=True
        )
        self.server_thread.start()

        # Wait for backend readiness before presenting the window
        logger.info("Waiting for backend health check...")
        if not wait_for_backend_ready(self.app_url, max_wait_seconds=15.0):
            logger.error("FastAPI backend failed to respond within 15 seconds.")
            self.stop_backend()
            return False

        logger.info(f"Backend is ready and verified at {self.app_url}/api/v1/health")
        return True

    def stop_backend(self, timeout: float = 5.0):
        """Signals uvicorn to exit and joins the server thread."""
        if not self._is_shutting_down:
            self._is_shutting_down = True
            logger.info("Stopping in-process backend server...")
            if self.server:
                self.server.should_exit = True

        if self.server_thread and self.server_thread.is_alive():
            # Wait for the uvicorn event loop to exit cleanly
            self.server_thread.join(timeout=timeout)
            if self.server_thread.is_alive():
                logger.warning(f"Backend server thread did not terminate within {timeout}s timeout.")
            else:
                logger.info("Backend server thread stopped cleanly.")

    def _on_window_closed(self):
        """Triggered when the native OS window is closed by the user."""
        logger.info("Native window closed by user. Initiating clean shutdown...")
        if self.server:
            self.server.should_exit = True


    def run(self, on_ready: Optional[Callable[[webview.Window], None]] = None):
        """
        Launches the desktop application:
        1. Starts backend
        2. Probes readiness
        3. Opens native WebView2 window
        4. Handles clean shutdown
        """
        # Register signal handlers for clean SIGINT / SIGTERM handling
        def _signal_handler(signum, frame):
            logger.info(f"Received signal {signum}. Closing application...")
            if self.window:
                try:
                    self.window.destroy()
                except Exception:
                    pass
            self.stop_backend()
            sys.exit(0)

        try:
            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)
        except (ValueError, AttributeError):
            # In some multithreaded or non-main thread contexts, signal handlers cannot be set
            pass

        # 1. Start backend server
        if not self.start_backend():
            print(
                f"\n[ERROR] Failed to start backend server at {self.app_url}.\n"
                "Please check logs or run the fallback CustomTkinter app: python main.py\n"
            )
            return 1

        # 2. Create native window
        logger.info(f"Creating native window ({self.width}x{self.height}) loading {self.app_url}...")
        self.window = webview.create_window(
            title=self.title,
            url=self.app_url,
            width=self.width,
            height=self.height,
            resizable=True,
            min_size=self.min_size,
            background_color="#0a0e17"
        )
        self.window.events.closed += self._on_window_closed

        # 3. Start WebView event loop
        try:
            def _start_callback():
                logger.info("Native desktop window successfully rendered.")
                if on_ready:
                    on_ready(self.window)

            icon_path = get_icon_path()
            icon_arg = str(icon_path) if icon_path else None
            if icon_arg:
                logger.info(f"Applying native window icon from: {icon_arg}")

            webview.start(_start_callback, gui="edgechromium", debug=self.debug, icon=icon_arg)
        except Exception as e:
            logger.exception(f"Unhandled exception in webview event loop: {e}")
            return 1
        finally:
            self.stop_backend()

        return 0


def parse_args():
    parser = argparse.ArgumentParser(description="DataVerse — Shared WebView Desktop Studio")
    parser.add_argument("--desktop", action="store_true", help="Launch in desktop mode (default)")
    parser.add_argument("--port", type=int, default=None, help="Explicit port to bind (default: auto-find starting at 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (enforced 127.0.0.1 for local security)")
    parser.add_argument("--debug", action="store_true", help="Enable WebView2 developer tools and verbose logging")
    parser.add_argument("--test-mode", action="store_true", help="Automated verification mode (launches, tests readiness, closes immediately)")
    return parser.parse_args()



def main():
    args = parse_args()

    app_instance = DataVerseDesktopApp(
        host=args.host,
        port=args.port,
        debug=args.debug
    )

    if args.test_mode:
        # Automated testing callback: verifies window, then cleanly destroys it after 2 seconds
        def test_callback(window):
            logger.info("[TEST-MODE] Window loaded. Verifying health check...")
            assert check_backend_health(app_instance.app_url), "Health check failed in test mode"
            logger.info("[TEST-MODE] Health check verified. Waiting 1.5s then destroying window...")
            time.sleep(1.5)
            window.destroy()

        return app_instance.run(on_ready=test_callback)

    return app_instance.run()


if __name__ == "__main__":
    sys.exit(main())
