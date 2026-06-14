
import uuid
from dataclasses import asdict, dataclass, field, InitVar
from typing import  Optional,Any
import unicodedata
from nicegui import binding
import numpy as np
import pandas as pd
from lmfit import Parameter as LMFitParameter

@dataclass
class ChemicalShiftParam():
    """Data class to represent a chemical shift parameter."""
    species: str = ""
    col: str | None = None  # raw_data column this resonance/shift belongs to (fast-exchange)
    value: float | None = None
    fixed: bool = False  # Whether the parameter is fixed or not
    _min: float |None = None  # Minimum value for the parameter
    _max: float |None = None  # Maximum value for the parameter

    init_min: InitVar[Optional[float]] = None  # Initial minimum value for the parameter
    init_max: InitVar[Optional[float]] = None  # Initial maximum value for

    def __post_init__(self, init_min: Optional[float] = None, init_max: Optional[float] = None) -> None:
        # if not self.fixed and not isinstance(init_min,float):
        #     raise ValueError("Variable parameters must have a valid initial minimum value.")
        # if not self.fixed and not isinstance(init_max,float):
        #     raise ValueError("Variable parameters must have a valid initial maximum value.")
        if init_min is not None and init_max is not None and self.value is not None:
            if init_min >= init_max or init_min>self.value or init_max<self.value:
                raise ValueError("Initial min and max values must be valid and lesser/greater than the value.")
        if init_min is None and self._min is not None:
            return  # No need to set if already defined
        if init_max is None and self._max is not None:
            return  # No need to set if already defined
        self._min = init_min 
        self._max = init_max 
        # else:
        #     raise ValueError("Initial min and max values must be provided for variable parameters.")

