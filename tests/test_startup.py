from nicegui.testing import User
import sys
import subprocess
import time

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


