import uuid
from dataclasses import asdict, dataclass, field, InitVar
from typing import  Optional,Any
import unicodedata
from nicegui import binding
import numpy as np
import pandas as pd
from lmfit import Parameter as LMFitParameter

@binding.bindable_dataclass
@dataclass
class UIBindings:
    """Helper class to hold UI bindings."""
    model_name: str = ""
    raw_data_name: str = ""
    data_model_name: str = ""
    fit_name: str = ""
    sim_name: str = ""
 