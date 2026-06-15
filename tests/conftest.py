"""Pytest fixtures for NiceGUI integration tests.

NiceGUI's `nicegui.testing.plugin` (v3+) depends on a `chrome_options` fixture
which is usually provided by `pytest-selenium`. Our test env doesn't always
include that plugin, so we provide a minimal, compatible fixture here.

We also ensure the BindMC app is constructed before a `User`/`Screen` opens
`/`.
"""

import os
import importlib.util
import pytest

_HAS_NICEGUI = importlib.util.find_spec("nicegui") is not None

if _HAS_NICEGUI:
    pytest_plugins = ["nicegui.testing.plugin"]
else:
    pytest_plugins: list[str] = []


@pytest.fixture
def chrome_options():
    """Fallback for NiceGUI v3 tests.

    NiceGUI's screen plugin requests this fixture and then wraps it via
    `nicegui_chrome_options`.
    """
    try:
        from selenium import webdriver

        opts = webdriver.ChromeOptions()
        # Prefer the new headless flag but gracefully fallback.
        try:
            opts.add_argument("--headless=new")
        except Exception:
            opts.add_argument("--headless")

        # More stable in CI/headless.
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--disable-gpu")

        # Configure default download directory so `Download Simulation Data`
        # can be verified in `tests/test_simulation_workflow_screen.py`.
        download_dir = os.path.join(os.getcwd(), "tests", "downloads")
        os.makedirs(download_dir, exist_ok=True)
        opts.add_experimental_option(
            "prefs",
            {
                "download.default_directory": download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
            },
        )
        return opts
    except Exception:
        # If selenium isn't installed, returning None avoids fixture-not-found
        # and lets pytest surface the real dependency error.
        return None


@pytest.fixture(autouse=True)
def _bindmc_server() -> None:
    """Ensure the NiceGUI page routes are registered for each test."""
    if not _HAS_NICEGUI:
        return None
    from bindmc.webgui.app import BindMCServer

    BindMCServer()
    return None


# import os
# import pytest
# from nicegui.testing import User, Screen
# from bindmc.webgui.app import BindMCServer


# pytest_plugins = ['nicegui.testing.user_plugin', 'nicegui.testing.screen_plugin']

# def pytest_addoption(parser):
#     parser.addoption("--driver", action="store", default="Chrome")

# @pytest.fixture
# def user(user: User) -> User:
#     BindMCServer()
#     return user

# @pytest.fixture
# def screen(screen: Screen) -> Screen:
#     BindMCServer()
#     # Configure browser window and download behavior for Selenium-driven Screen
#     driver = getattr(screen, 'selenium', None)
#     if driver is not None:
#         try:
#             driver.set_window_size(1920, 1080)
#         except Exception:
#             pass
#         download_dir = os.path.join(os.getcwd(), 'tests', 'downloads')
#         os.makedirs(download_dir, exist_ok=True)
#         # Allow downloads to a fixed directory in headless Chrome via CDP
#         try:
#             driver.execute_cdp_cmd(
#                 "Page.setDownloadBehavior",
#                 {"behavior": "allow", "downloadPath": download_dir},
#             )
#         except Exception:
#             # Some drivers may not support CDP; ignore and proceed
#             pass
#     return screen


@pytest.fixture
def screen(screen):
    """Extend the NiceGUI Screen fixture to ignore transient unmounted element updates."""
    screen.allowed_js_errors.append("Cannot read properties of undefined (reading 'update')")
    return screen
