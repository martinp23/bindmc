# to build: rm -fr build && rm -fr dist && nicegui-pack --onefile --add-data "C:\Users\mpeeks\miniforge3\envs\binding-nicegui\Lib\site-packages\arviz\static;arviz/static" --add-data "C:\Users\mpeeks\miniforge3\envs\binding-nicegui\Lib\site-packages\arviz\data;arviz/data" --add-data "C:\Users\mpeeks\miniforge3\envs\binding-nicegui\Lib\site-packages\latex2mathml\unimathsymbols.txt;latex2mathml" main.py

# on windows:
# nicegui-pack main.py --no-build

# macOS packaging support
from multiprocessing import freeze_support  # noqa

freeze_support()  # noqa

# hidden import for pyinstaller
import matplotlib

matplotlib.use("module://matplotlib.backends.backend_svg")
import sys
import webview
from nicegui import native, ui, app
from bindmc.webgui.app import BindMCServer
import logging
import nicegui
from packaging.version import InvalidVersion, Version
from pathlib import Path
from platformdirs import user_data_dir
from importlib.metadata import version

__version__ = version("bindmc")

def is_webview_available() -> bool:
    """Check if pywebview GUI libraries can be initialized in-process."""
    try:
        from webview.guilib import initialize
        from webview.util import WebViewException
        
        # Temporarily suppress pywebview's internal logger to prevent 
        # missing backend errors from spamming your console output.
        logger = logging.getLogger('pywebview')
        old_level = logger.level
        logger.setLevel(logging.CRITICAL)
        
        try:
            # Attempts to load the default system GUI engine (e.g. Edge, Cocoa, GTK, QT)
            initialize()
            return True
        except (WebViewException, ImportError, Exception):
            return False
        finally:
            logger.setLevel(old_level)
            
    except ImportError:
        # pywebview itself isn't even installed
        return False


logger = logging.getLogger(__name__)

try:
    nicegui_version = Version(nicegui.__version__)
except InvalidVersion:
    logger.warning(
        "Could not parse NiceGUI version '%s'; continuing, but NiceGUI >= 3 is required.",
        nicegui.__version__,
    )
else:
    if nicegui_version.is_prerelease or nicegui_version.is_devrelease:
        logger.warning(
            "NiceGUI %s is a pre-release/dev build; recommended to install the latest stable 3.x.",
            nicegui.__version__,
        )
    elif nicegui_version.major < 3:
        raise RuntimeError(f"NiceGUI >= 3 is required; found {nicegui.__version__}")




app.native.settings["ALLOW_DOWNLOADS"] = True

# logging.basicConfig(level=logging.INFO, filename='BindMC.log')
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")

logger.info(f"Starting BindMC {__version__} NiceGUI server...")
BindMCServer()

# pyinstaller?
is_frozen = getattr(sys, "frozen", False)

is_module_run = bool(globals().get("__package__"))

DEV = not (is_frozen or is_module_run)

native_mode = False
if DEV:
    native_mode = False
    reload = True
else:
    native_mode = is_webview_available()
    if native_mode is False:
        logger.warning("Native mode is not available; running via browser.")
    reload = False




# make a sensible storage path for native mode
storage_path = Path(user_data_dir(appname="BindMC", appauthor=False))
storage_path.mkdir(parents=True, exist_ok=True)

# Redirect native window persistence data away from default paths
app.native.start_args["storage_path"] = str(storage_path)

# if __name__ == {"__main__", "__mp_main__"}:
ui.run(title="BindMC", reload=reload, native=native_mode, port=native.find_open_port(), storage_secret="bindmc_secret")


