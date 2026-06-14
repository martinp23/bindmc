import uuid
from dataclasses import asdict, dataclass, field, InitVar
from typing import  Optional,Any
import unicodedata
from nicegui import binding
import numpy as np
import pandas as pd
from lmfit import Parameter as LMFitParameter
from .Component import Component
from .BindingConstant import BindingConstant

@dataclass
class Model:
    """Data class to represent a model."""

    name: str = ""
    eq_str: str = ""
    eq_mat_str: str = ""
    eq_mat: np.ndarray = field(
        default_factory=lambda: np.array([])
    )  # List of numpy arrays for the equilibrium matrix # TODO this should just be an array
    nComp: int = 2
    nStep: int = 20
    components: list[Component] = field(default_factory=list)
    binding_constants: list[BindingConstant] = field(default_factory=list)
    results: np.ndarray = field(default_factory=lambda: np.array([]))
    species: list[str] = field(default_factory=list)
    component_names: list[str] = field(default_factory=list)
    component_concs: pd.DataFrame = field(
        default_factory=pd.DataFrame, compare=False
    )  # compare=False means that __eq__ does not try to do a dataframe comparison, which tends to fail
    id: uuid.UUID = field(
        default_factory=lambda: (uuid.uuid4()))

    def __post_init__(self):
        """Ensure data are appropriate types."""
        if not isinstance(self.id, uuid.UUID):
            if isinstance(self.id, str):
                self.id = uuid.UUID(self.id)

    def to_dict(self):
        """Convert Model to a dictionary."""
        return {
            "name": self.name,
            "eq_str": self.eq_str,
            "eq_mat_str": str(self.eq_mat_str) if self.eq_mat_str else "",
            "eq_mat": (
                self.eq_mat.tolist() if isinstance(self.eq_mat, np.ndarray) else []
            ),  # Convert numpy arrays to lists
            "nComp": int(self.nComp),
            "nStep": int(self.nStep),
            "components": (
                [asdict(comp) for comp in self.components]
                if len(self.components) > 0
                else []
            ),
            "binding_constants": (
                [asdict(k) for k in self.binding_constants]
                if len(self.binding_constants) > 0
                else []
            ),
            "results": self.results.tolist() if hasattr(self,'results') and len(self.results)>0 else [],
            "species": self.species if self.species else [],
            "component_names": self.component_names if self.component_names else [],
            "component_concs": (
                self.component_concs.to_dict()
                if isinstance(self.component_concs, pd.DataFrame)
                else {}
            ),
            "id": str(self.id),
        }

    @property
    def fullCompSpecList(self) -> list[str]:
        """Get the full list of component and species names."""
        return [s + "_tot" for s in self.component_names] + [
            s + "_free" for s in self.species
        ]
    

    def __eq__(self,other):
        if not isinstance(other, Model):
            return False
        
        return self.id == other.id

