import uuid
from dataclasses import asdict, dataclass, field, InitVar
from typing import  Optional,Any
import unicodedata
from nicegui import binding
import numpy as np
import pandas as pd
from lmfit import Parameter as LMFitParameter
from .Model import Model
from .ExptData import ExptData
import bindtools.binding as bd

@dataclass 
class FitResult:
    """Data class to represent the results of a fit."""
    model_id: uuid.UUID   # The modelUID used for the fit
    expt_data_id: uuid.UUID   # The experimental data used for the fit, if any
    name: str  # Name of the fit result
    description: str  # Description of the fit result
    aic: float   # Akaike Information Criterion for the fit
    bic: float  # Bayesian Information Criterion for the fit
    chisqr: float  # Chi-squared value for the fit
    termination_message: str  # Message indicating the termination status of the fit
    fit_method: str = 'least_squares' # method used in the fit e.g. least_sq
    success: Any = False  # Whether the fit was successful
    fit_speciation: pd.DataFrame = field(default_factory=pd.DataFrame, compare=False)  # DataFrame to hold output species concentrations
    calc_obs: pd.DataFrame = field(default_factory=pd.DataFrame, compare=False)  # Calculated observations from the fit
    id: uuid.UUID = field(default_factory=lambda: (uuid.uuid4()))
    params: dict = field(default_factory=dict)   # List of binding constants and other parameters
    bd_model: Optional[bd.bindingModel] = None
    analytical_fast_exchange: bool = False
    analytical_topology: Optional[str] = None
    analytical_obs_columns: list[str] = field(default_factory=list)
    analytical_obs_components: list[int] = field(default_factory=list)
    analytical_complex_indices: list[int] = field(default_factory=list)
    
    init_model: InitVar[Optional[Model]] = None  # The model used for the fit, if any
    init_expt_data: InitVar[Optional[ExptData]] = None  # The

    _model: Optional[Model] = None  # The model used for the fit, if any
    _expt_data: Optional[ExptData] = None  # The experimental data used for the fit, if any



    def __post_init__(self,init_model,init_expt_data):
        """Ensure data are appropriate types."""
        if isinstance(init_model,Model):
            self._model = init_model
            self.model_id = init_model.id
        if isinstance(init_expt_data, ExptData):
            self._expt_data = init_expt_data
            self.expt_data_id = init_expt_data.id


        if not isinstance(self.expt_data_id, uuid.UUID):
            if isinstance(self.expt_data_id, str):
                self.expt_data_id = uuid.UUID(self.expt_data_id)
        
        if not isinstance(self.model_id, uuid.UUID):
            if isinstance(self.model_id, str):
                self.model_id = uuid.UUID(self.model_id)

        if not isinstance(self.id, uuid.UUID):
            if isinstance(self.id, str):
                self.id = uuid.UUID(self.id)

        if isinstance(self._expt_data,ExptData) and not self.expt_data_id:
            self.expt_data_id = self._expt_data.id

        if isinstance(self._model, Model) and not self.model_id:
            self.model_id = self._model.id

    def __eq__(self,other):
        if not isinstance(other, FitResult):
            return False
        
        return self.id == other.id

    def find_and_link_expt_data(self, expt_datas: dict[uuid.UUID,ExptData]) -> None:
        """Link the experimental data to this fit result."""
        if expt_datas is not None:
            if self.expt_data_id in expt_datas and self.expt_data_id is not None:
                self._expt_data = expt_datas[self.expt_data_id]
                return
        else:
            raise ValueError(f"Corresponding experimental data {self.expt_data_id} not found for FitResult.")

    def find_and_link_model(self, models: dict[uuid.UUID,Model]) -> None:
        """Link the experimental data to this fit result."""
        if models is not None:
            if self.model_id in models and self.model_id is not None:
                self._model = models[self.model_id]
                return
        else:
            raise ValueError(f"Corresponding model {self.model_id} not found for FitResult.")


    @property
    def comp_concs(self) -> pd.DataFrame:
        """Get the component concentrations for this fit."""
        if self._expt_data:
            return self._expt_data.comp_concs
        else:
            raise ValueError("ExptData is not set or does not have component concentrations.")
        
    @property
    def model(self) -> Model:
        """Get the model associated with this fit."""
        if hasattr(self, "_model") and isinstance(self._model, Model):
            return self._model
        else:
            raise ValueError("Model is not set for FitResult.")
       
    
    @model.setter
    def model(self, model: Model) -> None:
        """Set the model for this fit."""
        if model is not None:
            self.model_id = model.id
            self._model = model
        else:
            raise ValueError("Model cannot be None for FitResult.")
    
    @property
    def expt_data(self) -> ExptData:
        """Get the experimental data associated with this fit."""
        if hasattr(self, "_expt_data") and isinstance(self._expt_data, ExptData):
            return self._expt_data 
        else:
            raise ValueError("ExptData is not set for FitResult.")
    
    @expt_data.setter
    def expt_data(self, expt_data: ExptData) -> None:
        """Set the experimental data for this fit."""
        if expt_data is not None:
            self.expt_data_id = expt_data.id
            self._expt_data = expt_data
        else:
            raise ValueError("ExptData cannot be None for FitResult.")

    def to_dict(self) -> dict[str, str|dict|list|bool|float|None]:
        """Convert FitResult to a dictionary."""
        return {
            "model_id": str(self.model_id) if self.model_id else "",
            "expt_data_id": str(self.expt_data_id) if self.expt_data_id else None,
            "id": str(self.id) if self.id else "",
            "name": self.name,
            "description": self.description,
            "params": self.params if isinstance(self.params, dict) else {},
            "aic": self.aic,
            "bic": self.bic,
            "chisqr": self.chisqr,
            "fit_method": self.fit_method,
            "termination_message": self.termination_message,
            "success": self.success,
            "analytical_fast_exchange": self.analytical_fast_exchange,
            "analytical_topology": self.analytical_topology,
            "analytical_obs_columns": list(self.analytical_obs_columns),
            "analytical_obs_components": list(self.analytical_obs_components),
            "analytical_complex_indices": list(self.analytical_complex_indices),
            "fit_speciation": (
                self.fit_speciation.to_dict(orient="list")
                if isinstance(self.fit_speciation, pd.DataFrame)
                else {}
            ),
            "calc_obs": (
                self.calc_obs.to_dict(orient="list")
                if isinstance(self.calc_obs, pd.DataFrame)
                else {}
            ),
        }
    
  
