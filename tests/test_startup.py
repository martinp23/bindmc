from nicegui.testing import User
import sys
import subprocess
import time
import asyncio

pytest_plugins = ["nicegui.testing.user_plugin"]


async def test_startup(user: User) -> None:
    # Set up test data

    await user.open("/")
    await user.should_see("BindMC")
    user.find("Simulate").click()
    user.find("Define model").click()


def test_module_execution_startup() -> None:
    # Run the module in a subprocess to check if it exits prematurely (the bug)
    # or remains running as a server (the correct behavior).
    import os
    import threading

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("PYTEST_CURRENT_TEST", None)

    proc = subprocess.Popen(

        [sys.executable, "-m", "bindmc"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    stdout_lines = []
    stderr_lines = []

    def read_stream(stream, lines_list):
        for line in iter(stream.readline, ""):
            lines_list.append(line)

    t_out = threading.Thread(target=read_stream, args=(proc.stdout, stdout_lines))
    t_err = threading.Thread(target=read_stream, args=(proc.stderr, stderr_lines))
    t_out.daemon = True
    t_err.daemon = True
    t_out.start()
    t_err.start()

    success = False
    start_time = time.time()
    timeout = 30.0

    try:
        while time.time() - start_time < timeout:
            exit_code = proc.poll()
            if exit_code is not None:
                break

            full_stdout = "".join(stdout_lines)
            if "Uvicorn running on" in full_stdout or "NiceGUI ready to go" in full_stdout:
                success = True
                break

            time.sleep(0.2)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

    full_stdout = "".join(stdout_lines)
    full_stderr = "".join(stderr_lines)

    assert success, (
        f"Server failed to start or exited prematurely.\n"
        f"Exit code: {proc.poll()}\n"
        f"Stdout:\n{full_stdout}\n"
        f"Stderr:\n{full_stderr}"
    )


async def test_version_check_warning_new_version_available(user: User, monkeypatch) -> None:
    # 1. Mock PyPI returning a newer version than current version
    import urllib.request
    from io import BytesIO
    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.read.return_value = b'{"info": {"version": "99.9.9"}}'
    mock_response.__enter__.return_value = mock_response

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: mock_response)

    # 2. Mock current version to be a fixed low version
    import importlib.metadata
    from importlib.metadata import PackageNotFoundError

    def mock_version(package_name):
        if package_name == "bindmc":
            return "0.1.0"
        raise PackageNotFoundError

    monkeypatch.setattr(importlib.metadata, "version", mock_version)

    # 3. Load the index page and verify warning is visible
    await user.open("/")
    await user.should_see("A new version of BindMC is available!")
    await user.should_see("For more details, see the BindMC website")

    # 4. Dismiss warning and verify it disappears
    user.find("Dismiss").click()
    # Give a tiny sleep for UI update if needed, though user.find is reactive
    await asyncio.sleep(0.1)
    try:
        user.find("A new version of BindMC is available!")
        assert False, "Alert should have been dismissed and not found on the page."
    except AssertionError:
        pass


async def test_version_check_warning_no_new_version(user: User, monkeypatch) -> None:
    # 1. Mock PyPI returning the same version
    import urllib.request
    from io import BytesIO
    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.read.return_value = b'{"info": {"version": "0.1.0"}}'
    mock_response.__enter__.return_value = mock_response

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: mock_response)

    # 2. Mock current version to be the same version
    import importlib.metadata
    from importlib.metadata import PackageNotFoundError

    def mock_version(package_name):
        if package_name == "bindmc":
            return "0.1.0"
        raise PackageNotFoundError

    monkeypatch.setattr(importlib.metadata, "version", mock_version)

    # 3. Load the index page and verify no warning is visible
    await user.open("/")
    await user.should_see("BindMC")
    try:
        user.find("A new version of BindMC is available!")
        assert False, "Alert should not have been displayed."
    except AssertionError:
        pass




