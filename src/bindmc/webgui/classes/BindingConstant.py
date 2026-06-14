import uuid
from dataclasses import asdict, dataclass, field, InitVar
from typing import  Optional,Any
import unicodedata
from nicegui import binding
import numpy as np
import pandas as pd
from lmfit import Parameter as LMFitParameter

@dataclass
class BindingConstant:
    species: str = ""
    logK: Optional[float] = None
    vary: bool = False
    isComp: bool = False
    min: Optional[float] = None
    max: Optional[float] = None

    @property
    def name(self) -> str:
        return self.species


