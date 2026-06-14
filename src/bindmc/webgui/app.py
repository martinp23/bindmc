from nicegui import ui

from .components import (
    BindMCHeader,
    Body
)
from .state.statemanager import StateManager

class BindMCServer:

    def __init__(self):

        self.state_manager: StateManager = StateManager(load_prior_state=False)  # Initialize state_manager attribute
        self.sm: StateManager =self.state_manager
        self.components = {}
        self.body_components={}
        self.tabs = {}
        self.setup_routes()


    def setup_routes(self):
        """Set up the application routes and UI components."""

        @ui.page("/")

        def index(): 
            self.state_manager = StateManager()
            self.sm = self.state_manager  # alias
            self._generate_header()
            self._generate_body()
            self.body_components = self.components["body"].components
            self._load_prior_state()
            
    

    def _load_prior_state(self):
        # if simulations have been run already, populate the graph
        if len(self.sm.simulations) > 0:
            self.body_components["simulation"].graph.load_simulations_data()
        if self.sm.active_expt_data_id is not None and self.sm.active_expt_data.data is not None and not self.sm.active_expt_data.data.empty:
            self.sm.notify_listeners("data_imported")
        if len(self.sm.fits) > 0:
            self.sm.notify_listeners("fits_loaded")
            # self.components["fit_results"].sync_graphs()
            # self.components["fit_results"].generate_delete_fit_dropdown()

        
    def _generate_header(self):
        ui.colors(primary='#000000', secondary='grey-5', accent='blue-grey-5')

        self.components["header"] = BindMCHeader(state_manager=self.state_manager)

    def _generate_body(self):
        self.components["body"]= Body(self.state_manager)
