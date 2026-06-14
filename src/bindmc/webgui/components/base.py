from abc import ABC, abstractmethod
from ..state import StateManager

class BaseComponent(ABC):
    """Base class for all UI components."""

    def __init__(self, state_manager: StateManager):
        self.sm: StateManager = state_manager
        self.container = None
        self.setup_nicegui()
        self.setup_bindings()

    @abstractmethod
    def setup_nicegui(self):
        """Set up the UI elements."""
        pass

    def setup_bindings(self):
        """Set up data bindings and listeners. Override if needed."""
        pass

    def refresh(self):
        """Refresh the component. Override if needed."""
        pass
