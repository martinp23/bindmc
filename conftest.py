def pytest_addoption(parser):
    parser.addoption(
        "--disable-jit",
        action="store_true",
        default=False,
        help="Disable Numba JIT compilation for debugging/coverage",
    )


def pytest_configure(config):
    if config.getoption("--disable-jit"):
        import os
        os.environ["NUMBA_DISABLE_JIT"] = "1"
