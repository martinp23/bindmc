#to build: rm -fr build && rm -fr dist && nicegui-pack --onefile --add-data "C:\Users\mpeeks\miniforge3\envs\binding-nicegui\Lib\site-packages\arviz\static;arviz/static" --add-data "C:\Users\mpeeks\miniforge3\envs\binding-nicegui\Lib\site-packages\arviz\data;arviz/data" --add-data "C:\Users\mpeeks\miniforge3\envs\binding-nicegui\Lib\site-packages\latex2mathml\unimathsymbols.txt;latex2mathml" main.py

# on windows:
# nicegui-pack main.py --no-build

# macOS packaging support
from multiprocessing import freeze_support  # noqa
freeze_support()  # noqa

# hidden import for pyinstaller
import matplotlib
matplotlib.use('module://matplotlib.backends.backend_svg')
import sys
from nicegui import native,ui,app
from webgui.app import BindToolsServer
import logging
import nicegui
from packaging.version import InvalidVersion, Version
from pathlib import Path
from platformdirs import user_data_dir

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


app.native.settings['ALLOW_DOWNLOADS'] = True

#logging.basicConfig(level=logging.INFO, filename='bindtools.log')
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')

logger.info("Starting BindTools NiceGUI server...")
BindToolsServer()

# Set DEV based on whether running from PyInstaller bundle
DEV = not getattr(sys, 'frozen', False)

if DEV:
    native_mode=False
    reload=True
else:
    native_mode=True
    reload=False


# make a sensible storage path for native mode
storage_path = Path(user_data_dir(appname="BindTools", appauthor=False))
storage_path.mkdir(parents=True, exist_ok=True)

# Redirect native window persistence data away from default paths
app.native.start_args['storage_path'] = str(storage_path)

ui.run(title='BindTools', reload=reload, native=native_mode, port=native.find_open_port(), storage_secret='bindtools_secret')
