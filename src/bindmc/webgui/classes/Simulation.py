import uuid
from dataclasses import asdict, dataclass, field
from typing import  Optional
import pandas as pd
from .BindingConstant import BindingConstant
from .Model import Model


@dataclass
class Simulation:
    """Data class to represent a simulation, which comprises:
    - input data (component concentrations or analogous generators)
    - a model (consider separating into a binding model and a data model,
                where the former has parameters of binding constants only, the latter of datafile<=>concentration
                conversions etc.)
    - params (comprising at minimum a list of binding constants)
    - output data (speies concentrations)"""

    comp_concs: pd.DataFrame = field(
        default_factory=pd.DataFrame, compare=False
    )  # compare=False means that __eq__ does not try to do a dataframe comparison, which tends to fail
    model_id: uuid.UUID | None = None  # The modelUID used for the simulation
    params: list[BindingConstant] = field(
        default_factory=list
    )  # List of binding constants and other parameters
    results: pd.DataFrame = field(
        default_factory=pd.DataFrame
    )  # DataFrame to hold output species concentrations
    id: uuid.UUID = field(
        default_factory=lambda: (uuid.uuid4())
    )  # unique ID for the instance
    comment: str = ""  # Optional comment for the simulation
    name: str = ""

    def __post_init__(self):
        """Ensure data are appropriate types."""
        if not isinstance(self.id, uuid.UUID):
            if isinstance(self.id, str):
                self.id = uuid.UUID(self.id)
        
        if not isinstance(self.model_id,uuid.UUID):
            if isinstance(self.model_id, str):
                self.model_id = uuid.UUID(self.model_id)

        # deep copy dataframes to avoid issues with mutability
        if isinstance(self.comp_concs, pd.DataFrame):
            self.comp_concs = self.comp_concs.copy()
        if isinstance(self.results, pd.DataFrame):
            self.results = self.results.copy()

    def to_dict(self) -> dict[str, str|dict|list]:
        return {
            "comp_concs": (
                self.comp_concs.to_dict()
                if isinstance(self.comp_concs, pd.DataFrame)
                else {}
            ),
            "model_id": str(self.model_id) if self.model_id else "",
            "params": [asdict(k) for k in self.params] if len(self.params) > 0 else [],
            "results": (
                self.results.to_dict(orient="list")
                if isinstance(self.results, pd.DataFrame)
                else {}
            ),
            "id": str(self.id),
            "comment": self.comment,
            "name": self.name,
        }

    @property
    def model(self) -> Optional[Model]:
        """Get the model associated with this simulation."""
        return self._model if hasattr(self, "_model") else None

    @model.setter
    def model(self, model: Model) -> None:
        """Set the model for this simulation."""
        if model is not None:
            self.model_id = model.id
            self._model = model
        else:
            self.model_id = None
            self._model = None

    def find_and_link_model(self, models: Optional[dict[uuid.UUID,Model]] = None) -> None:
        """Set the model for this simulation."""
        if models is not None:
            if self.model_id in models and self.model_id is not None:
                self._model = models[self.model_id]
            else:
                raise ValueError(f"Corresponding model {self.model_id} not found for Simulation.")



    def __eq__(self,other):
        if not isinstance(other, Simulation):
            return False
        
        return self.id == other.id

