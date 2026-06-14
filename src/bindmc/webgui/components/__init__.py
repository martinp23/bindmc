# webgui/components/__init__.py
from .base import BaseComponent
from .header import BindToolsHeader
from .data_gen import DataGenerationPanel
from .data_import import DataImportPanel
from .data_model import DataModelPanel
from .simulation import SimulationPanel
from .binding_model import BindingModelPanel
from .fitting import FittingPanel
from .bayes import BayesPanel
from .graph import Graph
from .body import Body

# from .data_generation import DataGenerationPanel
# from .data_import import DataImportPanel

__all__ = [
    "BaseComponent",
    "BindToolsHeader",
    "DataGenerationPanel",
    "DataModelPanel",
    "DataImportPanel",
    "SimulationPanel",
    "BindingModelPanel",
    "FittingPanel",
    "BayesPanel",
    "Graph",
    "Body",
]
