import asyncio
import json
import urllib.request
from importlib.metadata import version, PackageNotFoundError
from packaging.version import Version, InvalidVersion
from nicegui import ui

from .components import BindMCHeader, Body
from .state.statemanager import StateManager


class BindMCServer:
    def __init__(self):

        self.state_manager: StateManager = StateManager(load_prior_state=False)  # Initialize state_manager attribute
        self.sm: StateManager = self.state_manager
        self.components = {}
        self.body_components = {}
        self.tabs = {}
        self._latest_version_cache = None  # Cache for version check to avoid redundant API hits
        self.setup_routes()

    def setup_routes(self):
        """Set up the application routes and UI components."""

        @ui.page("/")
        def index():
            self.state_manager = StateManager()
            self.sm = self.state_manager  # alias
            self._generate_header()
            warning_placeholder = ui.column().classes("w-full q-px-md q-pt-md gap-2")
            self._generate_body()
            self.body_components = self.components["body"].components
            self._load_prior_state()
            asyncio.create_task(self._check_version_async(warning_placeholder))

    def _load_prior_state(self):
        # if simulations have been run already, populate the graph
        if len(self.sm.simulations) > 0:
            self.body_components["simulation"].graph.load_simulations_data()
        if (
            self.sm.active_expt_data_id is not None
            and self.sm.active_expt_data.data is not None
            and not self.sm.active_expt_data.data.empty
        ):
            self.sm.notify_listeners("data_imported")
        if len(self.sm.fits) > 0:
            self.sm.notify_listeners("fits_loaded")
            # self.components["fit_results"].sync_graphs()
            # self.components["fit_results"].generate_delete_fit_dropdown()

    def _generate_header(self):
        ui.colors(primary="#000000", secondary="grey-5", accent="blue-grey-5")

        self.components["header"] = BindMCHeader(state_manager=self.state_manager)

    def _generate_body(self):
        self.components["body"] = Body(self.state_manager)

    async def _check_version_async(self, container):
        latest_version = await self._fetch_latest_version()
        if not latest_version:
            return

        current_version = self._get_current_version()
        if self._is_newer_version(latest_version, current_version):
            with container:
                with ui.card().classes(
                    "w-full bg-amber-50 border border-amber-200 text-amber-950 rounded-lg p-4 flex flex-row items-center justify-between shadow-sm"
                ) as warning_card:
                    with ui.row().classes("items-center gap-3"):
                        ui.icon("warning", color="amber-800").classes("text-2xl")
                        with ui.column().classes("gap-0"):
                            ui.label(
                                f"A new version of BindMC is available! ({latest_version})"
                            ).classes("font-semibold text-sm")
                            ui.label(
                                f"You are currently running version {current_version}. Please upgrade to get the latest features."
                            ).classes("text-xs opacity-80")
                    with ui.row().classes("items-center gap-4"):
                        ui.link(
                            "For more details, see the BindMC website",
                            "https://github.com/martinp23/bindmc",
                            new_tab=True
                        ).classes(
                            "text-sm font-semibold text-amber-900 hover:text-amber-700 underline"
                        )
                        ui.button(
                            "Dismiss",
                            on_click=warning_card.delete
                        ).props("flat dense").classes(
                            "text-amber-950 hover:text-amber-700 font-semibold text-sm"
                        )

    async def _fetch_latest_version(self) -> str | None:
        if self._latest_version_cache is not None:
            return self._latest_version_cache

        try:
            def query_pypi():
                url = "https://pypi.org/pypi/bindmc/json"
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "bindmc-gui-version-checker"}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    return data.get("info", {}).get("version")

            latest_version = await asyncio.to_thread(query_pypi)
            if latest_version:
                self._latest_version_cache = latest_version
            return latest_version
        except Exception:
            return None

    def _get_current_version(self) -> str:
        try:
            return version("bindmc")
        except PackageNotFoundError:
            return "0.1.11"

    def _is_newer_version(self, latest: str, current: str) -> bool:
        try:
            return Version(latest) > Version(current)
        except InvalidVersion:
            return False

