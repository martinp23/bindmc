from dataclasses import dataclass
from nicegui import binding


@binding.bindable_dataclass
@dataclass
class UIBindings:
    """Helper class to hold UI bindings."""

    model_name: str = ""
    raw_data_name: str = ""
    data_model_name: str = ""
    fit_name: str = ""
    sim_name: str = ""
